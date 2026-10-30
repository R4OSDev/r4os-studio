"""Bound public live intents, delayed echoes, one worker and passive recovery."""
import asyncio
import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,Mock
import uuid

from claude_goal import freeze
from claude_live_control import ClaudeLiveGoalControl
from claude_live_store import live_plays,open_source
from goal_control import live_control
from goal_store import Goals
from run_store import admit,get_run,transition
from store import ProjectFault
import test_claude_messages as fixtures


def uid():return str(uuid.uuid4())


class ClaudeLiveGoal(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.f=fixtures.ClaudeMessages();self.f.setUp();self.addCleanup(self.f.doCleanups)

    async def source(self):
        f=self.f;store=self.enterContext(f.open());request=uid()
        run,_=admit(store,f.sid,{'requestId':request,'revision':1,'text':'Own ordinary source.','liveGoalPreparation':1},f.providers)
        config,meta,_=f.opening(store,run)
        w=SimpleNamespace(store=store,session_id=f.sid,run_id=run['id'],row=get_run(store,run['id']),config=config,
            credential_worker=meta,sent=True,stopping=False,uncertain_effect=False,input_receipt=asyncio.Event(),
            done=asyncio.Event(),claude_goal=None,command=AsyncMock(),current=AsyncMock(return_value=True),
            broker=SimpleNamespace(binding={'original':'binding'},stop_admission=Mock()),outcome='completed',error=None,
            native_receipt=None,native_result=None,admission_denial=None)
        def stop():w.stopping=True
        w.defer_stop=Mock(side_effect=stop)
        control=ClaudeLiveGoalControl(w);await control.start();self.addAsyncCleanup(control.close)
        open_source(w);return w,control

    def command(self,w,action,**more):
        goals=Goals(w.store);data={'requestId':uid(),'revision':goals.snapshot(w.session_id)['revision'],
            'action':action,'sessionRevision':1,'targetRunId':w.run_id,**more}
        result,fresh=goals.accept(w.session_id,data);self.assertTrue(fresh)
        return data,result

    async def saved(self,w):
        data,_=self.command(w,'save',objective='Complete this own bounded objective and check it.')
        result=await live_control(w.store,w.session_id,data['requestId']);self.assertEqual(result['state'],'confirmed')
        return data,result

    async def play(self,w,control):
        await self.saved(w);data,_=self.command(w,'play')
        result=await live_control(w.store,w.session_id,data['requestId']);self.assertEqual(result['state'],'pending')
        await asyncio.sleep(0)
        self.assertEqual(w.command.await_args.args,('arm_goal',))
        return data,w.claude_goal

    def armed(self,w,control,request,refused=False):
        control.native_arm({'event':'goal_arm_refused' if refused else 'goal_armed','requestId':w.row['request_id'],
            'nativeSessionId':self.f.native,'executionId':request,'sourceInputRequestId':w.row['request_id'],'state':'waiting'})

    def result(self,w):
        w.native_result={'type':'result','uuid':uid(),'session_id':self.f.native,'subtype':'success','is_error':False}
        return w.native_result

    def echo(self,w,runtime):
        step=runtime.journal.read()['steps'][-1]
        return {'native':{'type':'user','isReplay':True,'session_id':self.f.native},
            'identity':{'nativeType':'user','studioRequestId':w.row['request_id'],'studioGoalStepId':step['inputId'],
                'nativeSessionId':self.f.native,'nativeInputRequestIds':[step['inputId']],'nativeMessageId':step['inputId'],
                'nativeInputReceiptKind':'stdinEcho','nativeInputTextSha256':step['textSha256']}}

    async def test_delayed_original_echo_arm_and_goal_echo_have_distinct_authority_and_time(self):
        w,control=await self.source();original=copy.deepcopy(w.config);data,runtime=await self.play(w,control)
        self.assertFalse(w.input_receipt.is_set());self.assertIsNone(runtime.journal.read()['startedNs'])
        self.assertEqual(live_plays(w.store,w.run_id),{data['requestId']})
        self.armed(w,control,data['requestId']);await asyncio.sleep(0)
        self.assertFalse(runtime.begun);w.command.assert_awaited_once()
        w.input_receipt.set();self.assertTrue(await runtime.result(self.result(w)));await asyncio.sleep(.02)
        self.assertTrue(runtime.begun);self.assertFalse(w.input_receipt.is_set())
        self.assertEqual(w.command.await_args.args,('begin_goal',))
        self.assertIsNone(runtime.journal.read()['startedNs'])
        runtime.admitted({'allowed':True,'admissionId':uid()});runtime.submitted({'inputRequestId':data['requestId']})
        runtime.acknowledge(self.echo(w,runtime));runtime.acknowledge(self.echo(w,runtime))
        self.assertTrue(w.input_receipt.is_set());self.assertIsNotNone(runtime.journal.read()['startedNs'])
        self.assertEqual(Goals(w.store).receipt(w.session_id,data['requestId'])['state'],'confirmed')
        self.assertEqual(w.store.db.execute('SELECT count(*) FROM goal_clocks').fetchone()[0],1)
        self.assertEqual(w.store.db.execute("SELECT count(*) FROM items WHERE item_id=?",('user-'+data['requestId'],)).fetchone()[0],1)
        runtime.journal.report({'status':'complete','reason':'Owned objective checked.'},'owned-live-report')
        self.assertFalse(await runtime.result(self.result(w)));w.done.set();await runtime.finish(True)
        self.assertEqual(runtime.journal.read()['state'],'complete');self.assertEqual(w.config,original)
        self.assertEqual(json.loads(get_run(w.store,w.run_id)['config']),original)
        self.assertEqual(w.store.db.execute('SELECT count(*) FROM runs').fetchone()[0],1)
        self.assertIsNone(w.store.row(w.session_id)['thread_id'])

    async def test_stale_target_or_worker_cannot_receive_save_and_duplicate_intent_does_not_arm(self):
        w,control=await self.source();goals=Goals(w.store)
        with self.assertRaises(ProjectFault):self.command(w,'save',objective='Own text',targetRunId=uid())
        data,result=await self.saved(w)
        self.assertEqual(goals.accept(w.session_id,data),(result,False));self.assertEqual(await live_control(w.store,w.session_id,data['requestId']),result)
        w.command.assert_not_awaited()
        altered=json.loads(get_run(w.store,w.run_id)['worker']);altered['birth']='foreign-generation'
        with w.store.db:w.store.db.execute('UPDATE runs SET worker=? WHERE id=?',(json.dumps(altered),w.run_id))
        with self.assertRaises(ProjectFault):self.command(w,'play')

    async def test_late_native_refusal_preserves_original_result_without_goal_input_or_clock(self):
        w,control=await self.source();data,runtime=await self.play(w,control)
        w.input_receipt.set();source=self.result(w);await runtime.result(source)
        self.armed(w,control,data['requestId'],refused=True);await asyncio.sleep(.02)
        self.assertTrue(w.done.is_set());self.assertFalse(runtime.begun);w.command.assert_awaited_once()
        w.native_receipt={'nativeSessionId':self.f.native,'studioRequestId':w.row['request_id'],'resultId':source['uuid'],'promptSubmitted':True}
        await runtime.finish(True)
        self.assertEqual(runtime.journal.read()['state'],'blocked');self.assertEqual(w.outcome,'completed')
        self.assertEqual(Goals(w.store).receipt(w.session_id,data['requestId'])['state'],'failed')
        self.assertFalse(w.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='goal_clocks'").fetchone())

    async def test_direct_stop_before_boundary_cancels_play_without_source_replay(self):
        w,control=await self.source();data,runtime=await self.play(w,control)
        self.armed(w,control,data['requestId']);w.stopping=True;transition(w.store,w.run_id,'stopping');runtime.stop()
        w.input_receipt.set();source=self.result(w);await runtime.result(source);await asyncio.sleep(.02)
        self.assertFalse(runtime.begun);w.command.assert_awaited_once()
        w.native_receipt={'nativeSessionId':self.f.native,'studioRequestId':w.row['request_id'],'resultId':source['uuid'],
            'liveGoal':{'executionId':data['requestId'],'sourceInputRequestId':w.row['request_id'],'sourceResultId':source['uuid'],'inputSubmitted':False}}
        await runtime.finish(True);self.assertEqual(runtime.journal.read()['state'],'paused')
        self.assertEqual(Goals(w.store).receipt(w.session_id,data['requestId'])['state'],'failed')

    async def test_restore_and_undelivered_play_only_reconcile_original_receipts(self):
        w,control=await self.source();await self.saved(w);data,_=self.command(w,'play');goals=Goals(w.store)
        goals.recover(live_plays(w.store,w.run_id))
        self.assertEqual(goals.receipt(w.session_id,data['requestId'])['state'],'failed');w.command.assert_not_awaited()
        data,_=self.command(w,'play');control.close_intent()
        self.assertEqual(goals.receipt(w.session_id,data['requestId'])['state'],'failed');w.command.assert_not_awaited()
        with self.assertRaises(ProjectFault):freeze(w.store,w.session_id,goals.command(w.session_id,data['requestId']))

    async def test_live_pause_targets_the_attached_execution_on_the_original_socket(self):
        w,control=await self.source();data,runtime=await self.play(w,control)
        self.armed(w,control,data['requestId']);w.input_receipt.set()
        await runtime.result(self.result(w));await asyncio.sleep(.02)
        runtime.admitted({'allowed':True,'admissionId':uid()});runtime.submitted({'inputRequestId':data['requestId']})
        runtime.acknowledge(self.echo(w,runtime))
        pause,_=self.command(w,'pause');goals=Goals(w.store)
        result=await live_control(w.store,w.session_id,pause['requestId'])
        self.assertEqual(result['state'],'confirmed');self.assertEqual(result['snapshot']['phase'],'pausing')
        self.assertFalse(w.stopping);self.assertFalse(await runtime.result(self.result(w)))
        w.done.set();await runtime.finish(True)
        self.assertEqual(runtime.journal.read()['state'],'paused')
        self.assertEqual(goals.snapshot(w.session_id)['goal']['executionId'],data['requestId'])
        self.assertEqual(w.command.await_count,2)  # Original arm and begin only.

    async def test_new_queue_wins_before_waiting_goal_begin_and_keeps_original_input(self):
        from message_store import Messages
        w,control=await self.source();data,runtime=await self.play(w,control)
        self.armed(w,control,data['requestId']);queued=self.f.message_input()
        Messages(w.store).accept(w.session_id,queued,self.f.providers)
        frozen=Messages(w.store).row(w.session_id,queued['requestId'])['frozen']
        w.input_receipt.set();source=self.result(w);await runtime.result(source);await asyncio.sleep(.02)
        self.assertTrue(w.done.is_set());self.assertFalse(runtime.begun);w.command.assert_awaited_once()
        w.native_receipt={'nativeSessionId':self.f.native,'studioRequestId':w.row['request_id'],'resultId':source['uuid'],
            'liveGoal':{'executionId':data['requestId'],'sourceInputRequestId':w.row['request_id'],'sourceResultId':source['uuid'],'inputSubmitted':False}}
        await runtime.finish(True)
        self.assertEqual(runtime.journal.read()['state'],'paused')
        self.assertEqual(Messages(w.store).receipt(w.session_id,queued['requestId'])['state'],'queued')
        self.assertEqual(Messages(w.store).row(w.session_id,queued['requestId'])['frozen'],frozen)
        self.assertFalse(Messages(w.store).snapshot(w.session_id)['held'])
