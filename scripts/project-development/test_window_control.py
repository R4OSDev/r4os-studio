"""Original requests, native response loss and view-bound input protection."""
import datetime
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock, patch
from contracts import DevelopmentFault, UnconfirmedGuestEffect
from deskrun import command, launch_budget, NotSubmitted
from frame_binding import window, current
from window_control import validate, perform


class BoundsTest(unittest.TestCase):
    def test_no_foreign_target_position_or_unbounded_dimensions(self):
        for fields in ({'action':'resize','width':True,'height':200}, {'action':'resize','width':2000,'height':200},
                       {'action':'restore','instanceId':4}, {'action':'minimize','x':0}, {'action':'restore','nativeRequest':'free'},
                       {'action':'status','operationId':'18446744073709551616'}):
            with self.subTest(fields=fields), self.assertRaises(DevelopmentFault):validate(fields)
        self.assertEqual(validate({'action':'status','operationId':'18446744073709551615'}),'status')

    def test_native_controller_uses_actual_full_command_budget_without_truncation(self):
        deployment={'guestDirectory':r'C:\Build\P0000001\D0000001'}
        controller={'watchdogInstanceId':4294967295,'watchdogGeneration':'18446744073709551615'}
        budget=launch_budget(deployment,'',5000,controller)
        args='x'*max(0,budget['argumentCapacityBytes'])
        if budget['withinLimit']:
            self.assertIn('/CONTROLLER:4294967295:18446744073709551615',command(deployment,args,5000,controller))
        with self.assertRaises(NotSubmitted):command(deployment,'x'*100,5000,controller)
        self.assertNotIn('/CONTROLLER:',command(deployment,'',5000))

    def test_applied_view_invalidates_old_image_even_after_same_geometry_restore(self):
        state={'instanceId':4,'generation':'9','windowId':1,'windowWidth':640,'windowHeight':480,
            'windowVisible':True,'windowFocused':True,'state':'running','windowViewRevision':'10','windowActionPending':False}
        job={'process':{'instanceId':4,'generation':'9'},'target':{'bootId':'boot'}}
        image={'kind':'screenshot','bootId':'boot','process':{**job['process'],'windowId':1},
            'captureObservation':{'version':1,'mode':'observed-interval','completedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()},
            'windowObservation':window(state)}
        self.assertTrue(current(image,job,state,focused=True))
        self.assertFalse(current(image,job,{**state,'windowViewRevision':'11'},focused=True))
        pending={**state,'windowActionPending':True};image['windowObservation']=window(pending)
        self.assertFalse(current(image,job,pending,focused=True))


class ReceiptTest(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, pending=False, foreign=False):
        with tempfile.TemporaryDirectory() as folder:
            work=Path(folder);request_id=str(uuid.uuid4());operation=str(int(uuid.UUID(request_id).hex[:16],16) or 1)
            job={'id':'job','executionId':'execution','target':{'bootId':'original'},'process':{'instanceId':4,'generation':'9'},
                'windowControl':{'available':True}}
            updates=[];calls=[]
            store=SimpleNamespace(update=lambda *args,**kw:updates.append(kw),get=lambda _:job)
            execution=SimpleNamespace(work=work,store=store,output=lambda _:None)
            message={'requestId':request_id,'owner':{'sessionId':'session','agentRunId':'run'},'peerPid':1,
                'input':{'action':'resize','width':640,'height':480}}
            native={'result':-7 if pending else 0,'phase':2 if pending else 3,'frameReady':not pending,
                'operationId':str(int(operation)+1) if foreign else operation,'applied':{},'current':{}}
            async def call(name,**args):
                calls.append(name)
                if name=='window_prepare':return {'nativeRequest':'original-opaque-native-request'}
                if name=='window_command':
                    intent=json.loads((work/('window-'+request_id+'.intent.json')).read_text())
                    self.assertEqual(intent['nativeRequest'],args['nativeRequest'])
                    self.assertEqual(intent['target'],job['target']);self.assertEqual(intent['operationId'],operation)
                    return {'transportError':-10}
                if name=='window_status':return native
                if name=='poll':return {'state':'running'}
                raise AssertionError(name)
            control=SimpleNamespace(call=AsyncMock(side_effect=call))
            with patch('vm_worker.guard'),patch('authorization.authorize'),patch('actions.finish') as finish,patch('window_control.asyncio.sleep',AsyncMock()):
                if pending or foreign:
                    with self.assertRaises(UnconfirmedGuestEffect):
                        await perform(execution,job,message,{'state':'running'},control,object(),{'engine':{'profile':'studio-tools-v16'}})
                    finish.assert_not_called()
                else:
                    _,receipt=await perform(execution,job,message,{'state':'running'},control,object(),{'engine':{'profile':'studio-tools-v16'}})
                    self.assertTrue(receipt['confirmed']);self.assertTrue(receipt['appliedConfirmed'])
                    finish.assert_called_once()
            self.assertEqual(calls.count('window_command'),1)
            self.assertEqual(calls[:3],['window_prepare','window_command','window_status'])
            if pending:self.assertEqual(updates[-1]['windowControl']['operationId'],operation)

    async def test_lost_native_reply_uses_status_of_persisted_request(self):await self.exercise()
    async def test_unknown_pending_effect_stays_protected(self):await self.exercise(pending=True)
    async def test_different_original_operation_never_becomes_success(self):await self.exercise(foreign=True)
