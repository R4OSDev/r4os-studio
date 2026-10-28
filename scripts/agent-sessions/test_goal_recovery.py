"""Restart, original receipts and Stop races using owned session databases."""
import asyncio
import json
import os
import uuid
import unittest
from unittest.mock import AsyncMock,patch
from pathlib import Path
import test_goal_control as controls
from goal_store import Goals
from goal_readback import readback
from host import Host,UNIT
from lease import birth
from profile import write_json
from run_store import admit,get_run,transition
from session_store import encode
from store import ProjectFault


class GoalRecovery(unittest.IsolatedAsyncioTestCase):
    setUp=controls.GoalControlTests.setUp
    tearDown=controls.GoalControlTests.tearDown
    open=controls.GoalControlTests.open
    command=controls.GoalControlTests.command
    goal_worker=controls.GoalControlTests.goal_worker

    def host(self):
        return Host({'projects':str(self.projects),'r4os':str(self.r4os),'providers':str(self.providers),'uid':os.getuid()})

    async def test_readback_is_unloaded_and_isolated_without_changing_original_receipts(self):
        native=controls.Native()
        with self.open() as store:
            receipt,data=await self.command(store,native);before=Goals(store).receipt(self.sid,data['requestId'])
            state=store.directory/self.sid/'Codex';state.mkdir(parents=True);(state/'models.json').write_text('{}')
            native.goal.update(tokensUsed=39,timeUsedSeconds=12)
            native.calls.clear()
            with patch('goal_readback.prepare',return_value=(['bwrap','owned'],{})) as prepare:
                result=await readback(store,self.sid,native.factory)
            self.assertEqual(result['goal']['goal']['tokensUsed'],39)
            self.assertEqual(native.calls,[('thread/goal/get',{'threadId':native.thread})])
            self.assertEqual(prepare.call_args.args[1],state/'ReadbackHome')
            self.assertEqual(Goals(store).receipt(self.sid,data['requestId']),before)
            self.assertFalse(store.db.execute('SELECT 1 FROM runs').fetchone())

    async def test_readback_missing_catalog_or_native_failure_preserves_saved_goal(self):
        native=controls.Native()
        with self.open() as store:
            await self.command(store,native);before=Goals(store).snapshot(self.sid)
            with self.assertRaises(ProjectFault):await readback(store,self.sid,native.factory)
            self.assertEqual(Goals(store).snapshot(self.sid),before)
            (store.directory/self.sid/'Codex').mkdir(parents=True,exist_ok=True);(store.directory/self.sid/'Codex/models.json').write_text('{}')
            with patch('goal_readback.prepare',side_effect=OSError('owned failure')):
                with self.assertRaises(ProjectFault):await readback(store,self.sid,native.factory)
            self.assertEqual(Goals(store).snapshot(self.sid),before)

    async def test_readback_without_thread_is_only_a_local_read(self):
        with self.open() as store,patch('goal_readback.prepare') as prepare:
            result=await readback(store,self.sid)
            self.assertFalse(result['nativeRead']);prepare.assert_not_called()

    async def test_readback_cannot_reactivate_unowned_active_goal_or_clear_unknown_phase(self):
        native=controls.Native()
        with self.open() as store:
            await self.command(store,native);(store.directory/self.sid/'Codex').mkdir(parents=True,exist_ok=True);(store.directory/self.sid/'Codex/models.json').write_text('{}')
            native.goal['status']='active'
            with patch('goal_readback.prepare',return_value=(['bwrap'],{})):
                result=await readback(store,self.sid,native.factory)
            self.assertEqual(result['goal']['phase'],'unknown')
            native.goal['status']='paused'
            with patch('goal_readback.prepare',return_value=(['bwrap'],{})):
                result=await readback(store,self.sid,native.factory)
            self.assertEqual(result['goal']['phase'],'unknown')
            self.assertFalse(store.db.execute('SELECT 1 FROM runs').fetchone())

    async def test_coordinator_adopts_exact_live_worker_and_keeps_original_pending_play(self):
        w,native=await self.goal_worker();host=self.host();row=get_run(w.store,w.run_id)
        meta={'schema':1,**host.config,'runId':w.run_id,'projectId':self.pid,'sessionId':self.sid,
            'providerId':self.provider,'release':'own-fixture'}
        parent=host.root/w.run_id;parent.mkdir();write_json(parent/'worker.json',meta)
        async def systemctl(*args):
            if args[0]=='list-units':return UNIT.format(w.run_id)+' loaded active running Owned Goal'
            return str(os.getpid()) if '--property=MainPID' in args else 'active'
        with patch('host.validate_release'),patch('host.systemctl',side_effect=systemctl) as control:
            await host.recover()
        self.assertIn(w.run_id,host.active)
        self.assertEqual(Goals(w.store).command(self.sid,w.config['goalExecution']['requestId'])['state'],'pending')
        self.assertFalse(any(c.args[0] in ('start','stop') for c in control.call_args_list))
        for worker in ({'pid':os.getpid(),'birth':'wrong','release':'own-fixture'},
                       {'pid':os.getpid(),'birth':birth(os.getpid()),'release':'other-release'}):
            with w.store.db:w.store.db.execute('UPDATE runs SET worker=? WHERE id=?',(encode(worker),w.run_id))
            with patch('host.systemctl',side_effect=systemctl):self.assertFalse(await host.goal_worker_matches(meta,get_run(w.store,w.run_id)))
        host=self.host()
        with patch('host.validate_release'),patch('host.systemctl',side_effect=systemctl) as control:
            await host.recover()
        self.assertEqual(get_run(w.store,w.run_id)['state'],'unknown');self.assertIn(w.run_id,host.unbound)
        self.assertEqual(Goals(w.store).command(self.sid,w.config['goalExecution']['requestId'])['state'],'unknown')
        self.assertFalse(any(c.args[0] in ('start','stop') for c in control.call_args_list))
        self.assertEqual(row['worker'],encode({'release':'own-fixture','pid':os.getpid(),'birth':birth(os.getpid())}))

    async def test_lost_start_response_keeps_the_one_durable_play_without_restarting(self):
        native=controls.Native();host=self.host()
        with self.open() as store:
            await self.command(store,native);goals=Goals(store);rid=str(uuid.uuid4())
            goals.accept(self.sid,{'requestId':rid,'revision':goals.snapshot(self.sid)['revision'],'sessionRevision':1,'action':'play'})
        async def lost(request):
            with self.open() as store:admit(store,self.sid,request['input'],self.providers)
            raise ProjectFault('Owned lost unit response',503)
        with patch.object(host,'handle',side_effect=lost) as call:
            await host.goal_command('project',self.pid,self.sid,rid)
        self.assertEqual(call.call_count,1)
        with self.open() as store:
            goals=Goals(store);row=store.db.execute('SELECT * FROM runs').fetchone()
            self.assertEqual(row['request_id'],rid);self.assertEqual(row['busy'],1)
            self.assertEqual(goals.command(self.sid,rid)['stage'],'worker_queued')
            self.assertEqual(goals.receipt(self.sid,rid)['state'],'pending')
            transition(store,row['id'],'unknown');goals.lost_worker(row['id'])
            self.assertEqual(goals.receipt(self.sid,rid)['state'],'unknown')
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],1)

    async def test_restart_marks_lost_pausing_turn_unknown_and_does_not_undo_original_pause_receipt(self):
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'paused-but-inflight'}})
        goals=Goals(w.store);rid=str(uuid.uuid4())
        goals.accept(self.sid,{'requestId':rid,'revision':goals.snapshot(self.sid)['revision'],'action':'pause'})
        await w.goal_worker.pause(origin='user');receipt=goals.finish(self.sid,rid,phase='pausing')
        transition(w.store,w.run_id,'unknown');goals.lost_worker(w.run_id)
        self.assertEqual(goals.snapshot(self.sid)['phase'],'unknown')
        self.assertEqual(goals.receipt(self.sid,rid),receipt)
        self.assertEqual(w.store.db.execute('SELECT status FROM goal_turns').fetchone()[0],'unknown')

    async def test_late_goal_notifications_and_late_turn_do_not_undo_stop(self):
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        transition(w.store,w.run_id,'stopping');await w.stop()
        self.assertEqual(native.goal['status'],'paused')
        await w.notify('thread/goal/updated',{'threadId':w.thread_id,'goal':{**native.goal,'status':'active'}})
        await w.notify('thread/goal/cleared',{'threadId':w.thread_id})
        await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'late-turn'}})
        await asyncio.sleep(.1)
        self.assertEqual(Goals(w.store).snapshot(self.sid)['goal']['status'],'paused')
        self.assertEqual(Goals(w.store).snapshot(self.sid)['goal']['objective'],'Own Goal')
        self.assertEqual(get_run(w.store,w.run_id)['state'],'stopping')
        self.assertTrue(any(m=='turn/interrupt' and p['turnId']=='late-turn' for m,p in native.calls))

    async def test_late_distinct_turns_interrupt_once_without_blocking_reader_and_cleanup_waits(self):
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        transition(w.store,w.run_id,'stopping');await w.stop()
        self.assertTrue(w.stop_task.done());self.assertIsNone(w.turn_id)
        original=native.request;reply=asyncio.Event();received=[];cleanup=None
        async def waiting(method,params,**kwargs):
            if method=='turn/interrupt':received.append(params.copy());await reply.wait()
            return await original(method,params,**kwargs)
        try:
            with patch.object(native,'request',side_effect=waiting),patch.object(native,'close',new_callable=AsyncMock) as close:
                for thread,turn in ((w.thread_id,'late-first'),(w.thread_id,'late-second'),(w.thread_id,'late-first'),('foreign-thread','foreign-turn')):
                    await asyncio.wait_for(w.notify('turn/started',{'threadId':thread,'turn':{'id':turn}}),.2)
                await asyncio.sleep(0)
                self.assertEqual([v['turnId'] for v in received],['late-first','late-second'])
                self.assertTrue(all(v['threadId']==w.thread_id for v in received))
                cleanup=asyncio.create_task(w.cleanup());await asyncio.sleep(.02)
                self.assertFalse(cleanup.done());close.assert_not_awaited()
                self.assertIsNone(w.defer_interrupt('after-close-fence'))
                reply.set();await asyncio.wait_for(cleanup,1);close.assert_awaited_once()
            self.assertEqual(Goals(w.store).snapshot(self.sid)['goal']['status'],'paused')
            self.assertFalse(any(m=='turn/start' for m,_ in native.calls))
        finally:
            reply.set()
            if cleanup:await cleanup

    async def test_excess_turns_after_stop_are_bounded_and_end_unknown(self):
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        transition(w.store,w.run_id,'stopping');await w.stop()
        for i in range(65):await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'late-'+str(i)}})
        await asyncio.gather(*w.interrupt_tasks.values())
        calls=[p for m,p in native.calls if m=='turn/interrupt']
        self.assertEqual(len(calls),64);self.assertEqual(len({p['turnId'] for p in calls}),64)
        self.assertTrue(w.uncertain_effect);self.assertEqual(w.outcome,'unknown');self.assertTrue(w.done.is_set())
        self.assertFalse(any(m=='turn/start' for m,_ in native.calls))

    async def test_explicit_new_play_carries_unknown_effect_references_without_arguments_or_replay(self):
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        with w.store.db:w.store.db.execute('INSERT INTO tools VALUES (?,?,?,?,?,?,NULL)',
            (w.run_id,'original-effect','studio_write_file','own-hash','unknown',encode({'secret':'never-copy-this-value'})))
        await w.goal_worker.pause();transition(w.store,w.run_id,'unknown');Goals(w.store).lost_worker(w.run_id)
        await self.command(w.store,native,action='pause')
        goals=Goals(w.store);rid=str(uuid.uuid4());goals.accept(self.sid,{'requestId':rid,'revision':goals.snapshot(self.sid)['revision'],'sessionRevision':1,'action':'play'})
        second,_=admit(w.store,self.sid,{'requestId':rid,'revision':1,'mode':'goal','goalRequestId':rid},self.providers)
        config=json.loads(get_run(w.store,second['id'])['config'])
        self.assertEqual(config['goalRecovery']['tools'][0]['call_id'],'original-effect')
        self.assertNotIn('never-copy-this-value',encode(config))
        from goal_recovery import instructions
        self.assertIn('Never replay an unknown',instructions(config))
        self.assertEqual(w.store.db.execute('SELECT state FROM tools').fetchone()[0],'unknown')
