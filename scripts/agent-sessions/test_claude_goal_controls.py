"""Local public intents, bound worker transport, queue priority and lost control."""
import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,Mock
import uuid

from claude_goal_control import ClaudeGoalControl
from claude_goal_store import idle,stopping
from claude_goal_worker import ClaudeGoalRuntime
from goal_control import live_control
from goal_readback import readback
from goal_store import Goals
from message_store import Messages
from run_store import transition
from session_store import encode
from store import ProjectFault
import test_claude_goal as fixtures


class ClaudeGoalControls(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.base=fixtures.ClaudeGoal();self.base.setUp();self.addCleanup(self.base.doCleanups)
        self.f=self.base.fixture;self.sid=self.f.sid

    async def active(self):
        w,journal=self.base.prepare();w.input_receipt=asyncio.Event();w.done=asyncio.Event();w.sent=True
        w.outcome='completed';w.error=None;w.native_receipt={'promptSubmitted':True,'inputSubmitted':True};w.command=AsyncMock()
        w.broker=SimpleNamespace(stop_admission=Mock())
        def stopping():w.stopping=True
        w.defer_stop=Mock(side_effect=stopping)
        runtime=ClaudeGoalRuntime(w);runtime.journal=journal;runtime.started=True
        runtime.control=ClaudeGoalControl(runtime);await runtime.control.start()
        self.addAsyncCleanup(self.cleanup_runtime,runtime)
        journal.admitted({'admissionId':str(uuid.uuid4())});journal.submitted(w.row['request_id'])
        runtime.acknowledge(self.base.frame(journal))
        return w,runtime

    async def cleanup_runtime(self,runtime):
        if runtime.deadline_task:
            runtime.deadline_task.cancel();await asyncio.gather(runtime.deadline_task,return_exceptions=True)
        try:await runtime.control.close()
        except ProjectFault:pass
        await runtime.clock.close()

    def command(self,store,action):
        goals=Goals(store);data={'requestId':str(uuid.uuid4()),'revision':goals.snapshot(self.sid)['revision'],'action':action}
        result,fresh=goals.accept(self.sid,data);self.assertTrue(fresh)
        return data,result

    async def test_save_and_readback_are_local_idempotent_and_keep_unknown_tokens(self):
        with self.f.open() as store:
            goals=Goals(store);data={'requestId':str(uuid.uuid4()),'revision':0,'action':'save','objective':' Own local goal '}
            receipt,fresh=goals.accept(self.sid,data);self.assertTrue(fresh);self.assertEqual(receipt['state'],'pending')
            saved=idle(goals,self.sid,data['requestId']);self.assertEqual(saved['state'],'confirmed')
            value=saved['snapshot']['goal'];self.assertEqual(value['source'],'studio-claude');self.assertIsNone(value['tokensUsed'])
            self.assertEqual(value['objective'],'Own local goal');self.assertIsNone(store.row(self.sid)['thread_id'])
            self.assertEqual(goals.accept(self.sid,data),(saved,False))
            with self.assertRaises(ProjectFault):goals.accept(self.sid,data|{'objective':'Other goal'})
            result=await readback(store,self.sid,rpc_factory=Mock(side_effect=AssertionError('No native RPC allowed')))
            self.assertFalse(result['nativeRead']);self.assertTrue(result['studioRead'])
            self.assertFalse(store.db.execute('SELECT 1 FROM runs').fetchone())
            clear={'requestId':str(uuid.uuid4()),'revision':goals.snapshot(self.sid)['revision'],'action':'save','objective':''}
            goals.accept(self.sid,clear);self.assertIsNone(idle(goals,self.sid,clear['requestId'])['snapshot']['goal'])

    async def test_pause_uses_original_worker_socket_and_waits_for_step_closure(self):
        w,runtime=await self.active();goals=Goals(w.store);play=goals.receipt(self.sid,w.row['request_id'])
        self.assertEqual(play['state'],'confirmed');self.assertEqual(play['snapshot']['goal']['status'],'active')
        data,_=self.command(w.store,'pause');result=await live_control(w.store,self.sid,data['requestId'])
        self.assertEqual(result['state'],'confirmed');self.assertEqual(result['snapshot']['phase'],'pausing')
        self.assertFalse(w.stopping);self.assertEqual(runtime.journal.read()['state'],'stopping')
        duplicate=await live_control(w.store,self.sid,data['requestId']);self.assertEqual(duplicate,result)
        self.assertFalse(await runtime.result(self.base.native_result()));w.command.assert_not_awaited()
        await runtime.finish(True)
        final=goals.snapshot(self.sid);self.assertEqual(final['phase'],'idle');self.assertEqual(final['goal']['status'],'paused')
        self.assertIsNone(final['goal']['tokensUsed']);self.assertEqual(final['lastIntent'],'pause')

    async def test_queued_input_wins_at_boundary_without_another_goal_prompt(self):
        w,runtime=await self.active();data=self.f.message_input()
        message,fresh=Messages(w.store).accept(self.sid,data,self.f.providers);self.assertTrue(fresh)
        runtime.journal.report({'status':'continue','reason':'Own work remains.'},'own-priority-report')
        self.assertFalse(await runtime.result(self.base.native_result()));w.command.assert_not_awaited()
        await runtime.finish(True)
        self.assertEqual(Goals(w.store).snapshot(self.sid)['goal']['status'],'paused')
        self.assertEqual(Messages(w.store).receipt(self.sid,data['requestId'])['state'],'queued')
        self.assertFalse(Messages(w.store).snapshot(self.sid)['held'])
        self.assertEqual(len(runtime.journal.read()['steps']),1)

    async def test_explicit_pause_holds_a_bound_followup_instead_of_dispatching_it(self):
        from claude_waiting import public_target
        from run_store import get_run
        w,runtime=await self.active();target=public_target(w.store,get_run(w.store,w.run_id))
        self.assertIsNotNone(target)
        message=self.f.message_input()|{'afterRun':target}
        Messages(w.store).accept(self.sid,message,self.f.providers)
        data,_=self.command(w.store,'pause')
        await live_control(w.store,self.sid,data['requestId'])
        self.assertTrue(Messages(w.store).snapshot(self.sid)['held'])
        self.assertFalse(await runtime.result(self.base.native_result()));await runtime.finish(True)
        self.assertEqual(Messages(w.store).receipt(self.sid,message['requestId'])['state'],'queued')
        self.assertEqual(Messages(w.store).receipt(self.sid,message['requestId'])['afterRun'],target)
        w.command.assert_not_awaited()

    async def test_original_stop_is_applied_once_when_coordinator_delivery_is_lost(self):
        w,runtime=await self.active();data,_=self.command(w.store,'stop')
        goals=Goals(w.store);goals.recover({w.row['request_id'],data['requestId']})
        self.assertEqual(goals.receipt(self.sid,data['requestId'])['state'],'pending')
        # The still-running original worker polls only its accepted local
        # revocation. No restarted coordinator submits a native command.
        await runtime.control.drain();await runtime.control.drain()
        w.defer_stop.assert_called_once();w.broker.stop_admission.assert_called_once()
        self.assertTrue(w.stopping);self.assertEqual(goals.receipt(self.sid,data['requestId'])['state'],'confirmed')
        self.assertFalse(await runtime.result(self.base.native_result()));await runtime.finish(True)
        final=goals.snapshot(self.sid);self.assertEqual(final['goal']['status'],'paused');self.assertEqual(final['lastIntent'],'stop')

    async def test_changed_worker_generation_cannot_receive_control_or_new_authority(self):
        w,runtime=await self.active();data,_=self.command(w.store,'pause')
        meta=json.loads(w.store.db.execute('SELECT worker FROM runs WHERE id=?',(w.run_id,)).fetchone()[0]);meta['birth']='another-generation'
        with w.store.db:w.store.db.execute('UPDATE runs SET worker=? WHERE id=?',(encode(meta),w.run_id))
        with self.assertRaises(ProjectFault):await live_control(w.store,self.sid,data['requestId'])
        w.defer_stop.assert_not_called();self.assertEqual(Goals(w.store).receipt(self.sid,data['requestId'])['state'],'pending')

    async def test_late_pause_cannot_undo_a_direct_user_stop(self):
        w,runtime=await self.active();data,_=self.command(w.store,'pause')
        transition(w.store,w.run_id,'stopping');w.stopping=True
        runtime.journal.stop();stopping(w)
        await runtime.control.drain()
        goals=Goals(w.store);self.assertEqual(goals.receipt(self.sid,data['requestId'])['state'],'failed')
        self.assertEqual(goals.snapshot(self.sid)['lastIntent'],'stop')
        self.assertFalse(await runtime.result(self.base.native_result()));await runtime.finish(True)
        self.assertEqual(goals.snapshot(self.sid)['lastIntent'],'stop')


if __name__=='__main__':unittest.main()
