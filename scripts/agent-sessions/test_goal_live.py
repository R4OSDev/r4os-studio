"""Live-Play provenance and dormant native admission, using private fixtures."""
import asyncio
import os
import unittest
import uuid
import test_goal_control as controls
from goal_live import LiveGoals
from goal_store import Goals
from run_store import admit, get_run, transition
from store import ProjectFault
from worker import Worker

class LiveGoalTests(unittest.IsolatedAsyncioTestCase):
    setUp=controls.GoalControlTests.setUp
    tearDown=controls.GoalControlTests.tearDown
    open=controls.GoalControlTests.open
    command=controls.GoalControlTests.command

    async def prepared(self):
        native=controls.Native()
        with self.open() as store:
            await self.command(store,native)
            run,_=admit(store,self.sid,{**self.data,'liveGoalPreparation':1},self.providers)
        w=Worker({'projects':str(self.projects),'r4os':str(self.r4os),'projectId':self.pid,'runId':run['id'],'release':'own-fixture'})
        w.client=native;w.thread_id=native.thread
        transition(w.store,w.run_id,'running',turn_id='current-turn',worker={'liveGoalPreparation':1,'liveGoalControl':1,'liveGoalOpen':True,'release':'own-fixture','pid':os.getpid(),'birth':__import__('lease').birth(os.getpid())})
        self.addCleanup(w.store.close);self.addAsyncCleanup(w.goal_worker.close)
        await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'current-turn'}})
        return w,native

    async def test_dormant_resume_pauses_saved_active_and_normal_turn_ends(self):
        w,native=await self.prepared();native.goal['status']='active'
        await w.goal_worker.before_resume();await w.goal_worker.start_control()
        self.assertEqual(native.goal['status'],'paused');self.assertFalse(w.done.is_set())
        await w.notify('turn/completed',{'threadId':w.thread_id,'turn':{'id':'current-turn','status':'completed'}})
        self.assertTrue(w.done.is_set());self.assertEqual(w.outcome,'completed')
        self.assertFalse(any(method=='turn/start' or params.get('status')=='active' for method,params in native.calls))

    async def test_play_provenance_is_additive_replayable_and_target_bound(self):
        w,native=await self.prepared();goals=Goals(w.store)
        original=get_run(w.store,w.run_id)['config']
        data={'requestId':str(uuid.uuid4()),'revision':goals.snapshot(self.sid)['revision'],'action':'play','sessionRevision':1,
              'target':{'runId':w.run_id,'threadId':w.thread_id,'turnId':'current-turn'}}
        with self.assertRaises(ProjectFault):goals.accept(self.sid,{**data,'target':{**data['target'],'threadId':'foreign'}})
        receipt,fresh=goals.accept(self.sid,data);self.assertTrue(fresh)
        duplicate,fresh=goals.accept(self.sid,data);self.assertFalse(fresh);self.assertEqual(duplicate,receipt)
        with self.assertRaises(ProjectFault):goals.accept(self.sid,{**data,'target':{**data['target'],'turnId':'other'}})
        proof=LiveGoals(w.store).evidence(self.sid,data['requestId'])
        self.assertEqual(proof['goal']['objective'],'Own Goal');self.assertEqual(proof['binding']['runId'],w.run_id)
        self.assertEqual(get_run(w.store,w.run_id)['config'],original)
        self.assertFalse(any(params.get('status')=='active' for _,params in native.calls))

    async def test_unrequested_native_activation_closes_tool_admission(self):
        w,native=await self.prepared();await w.goal_worker.start_control()
        native.goal['status']='active'
        await w.notify('thread/goal/updated',{'threadId':w.thread_id,'goal':native.goal.copy()})
        self.assertTrue(w.stopping)
        await w.stop_task
        self.assertEqual(native.goal['status'],'paused')

    async def live(self,w,action,objective=None):
        from goal_control import live_control
        goals=Goals(w.store)
        data={'requestId':str(uuid.uuid4()),'revision':goals.snapshot(self.sid)['revision'],'action':action,'sessionRevision':1,
              'target':{'runId':w.run_id,'threadId':w.thread_id,'turnId':w.turn_id}}
        if action=='save':data['objective']=objective
        goals.accept(self.sid,data)
        return await live_control(w.store,self.sid,data['requestId']),data

    async def test_live_save_then_play_retains_original_run_and_usage(self):
        w,native=await self.prepared();await w.goal_worker.start_control()
        original=get_run(w.store,w.run_id)['config'];native.goal.update(tokensUsed=77,timeUsedSeconds=9)
        saved,_=await self.live(w,'save','Own Goal')
        self.assertEqual(saved['state'],'confirmed');self.assertEqual(native.goal['status'],'paused')
        self.assertTrue(w.goal_worker.dormant);self.assertFalse(w.done.is_set())
        receipt,data=await self.live(w,'play');self.assertEqual(receipt['state'],'confirmed')
        self.assertEqual(native.goal['tokensUsed'],77);self.assertEqual(native.goal['timeUsedSeconds'],9)
        self.assertEqual(get_run(w.store,w.run_id)['config'],original)
        await w.notify('turn/completed',{'threadId':w.thread_id,'turn':{'id':'current-turn','status':'completed'}})
        await asyncio.sleep(.1);self.assertFalse(w.done.is_set())
        native.goal['status']='complete'
        await w.notify('thread/goal/updated',{'threadId':w.thread_id,'goal':native.goal.copy()})
        await asyncio.wait_for(w.done.wait(),1)
        self.assertEqual(w.outcome,'completed')
        sets=[p for m,p in native.calls if m=='thread/goal/set' and p.get('status')=='active']
        self.assertEqual(len(sets),1);self.assertNotIn('objective',sets[0]);self.assertNotIn('tokenBudget',sets[0])

    async def test_accepted_play_wins_turn_boundary_and_lost_reply_is_read_only(self):
        from goal_control import live_control
        w,native=await self.prepared();await w.goal_worker.start_control();goals=Goals(w.store)
        data={'requestId':str(uuid.uuid4()),'revision':goals.snapshot(self.sid)['revision'],'action':'play','sessionRevision':1,
              'target':{'runId':w.run_id,'threadId':w.thread_id,'turnId':w.turn_id}}
        goals.accept(self.sid,data)
        await w.notify('turn/completed',{'threadId':w.thread_id,'turn':{'id':'current-turn','status':'completed'}})
        self.assertFalse(w.done.is_set());native.lost=True
        receipt=await live_control(w.store,self.sid,data['requestId']);self.assertEqual(receipt['state'],'confirmed')
        self.assertEqual(await live_control(w.store,self.sid,data['requestId']),receipt)
        self.assertEqual(sum(m=='thread/goal/set' and p.get('status')=='active' for m,p in native.calls),1)
        await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'native-followup'}})
        paused,_=await self.live(w,'pause');self.assertEqual(paused['state'],'confirmed');self.assertFalse(w.done.is_set())
        await w.notify('turn/completed',{'threadId':w.thread_id,'turn':{'id':'native-followup','status':'completed'}})
        await asyncio.wait_for(w.done.wait(),1)

    async def test_completion_fence_rejects_late_play_and_keeps_draft(self):
        w,native=await self.prepared();await w.goal_worker.start_control()
        await w.notify('turn/completed',{'threadId':w.thread_id,'turn':{'id':'current-turn','status':'completed'}})
        self.assertTrue(w.done.is_set())
        with self.assertRaises(ProjectFault):await self.live(w,'play')
        self.assertEqual(native.goal['status'],'paused')

    async def test_recovery_keeps_only_claimed_original_command_and_never_replays(self):
        w,native=await self.prepared();goals=Goals(w.store)
        def command():return {'requestId':str(uuid.uuid4()),'revision':goals.snapshot(self.sid)['revision'],'action':'play','sessionRevision':1,'target':{'runId':w.run_id,'threadId':w.thread_id,'turnId':w.turn_id}}
        first=command();goals.accept(self.sid,first);goals.recover()
        self.assertEqual(goals.receipt(self.sid,first['requestId'])['state'],'failed')
        second=command();goals.accept(self.sid,second);goals.stage(self.sid,second['requestId'],'native_live_mutation')
        goals.recover({second['requestId']});self.assertEqual(goals.receipt(self.sid,second['requestId'])['state'],'pending')
        transition(w.store,w.run_id,'unknown');goals.lost_worker(w.run_id)
        self.assertEqual(goals.receipt(self.sid,second['requestId'])['state'],'unknown')
        self.assertFalse(any(p.get('status')=='active' for _,p in native.calls))

    async def test_live_goal_human_context_rejects_corrupted_capture_and_older_run(self):
        from human_context import contexts
        w,native=await self.prepared();await w.goal_worker.start_control()
        receipt,data=await self.live(w,'play');owner={'type':'project','id':self.pid}
        self.assertIn('Own Goal',[c['text'] for c in contexts(w.store.db,self.sid,w.run_id,owner)])
        self.assertNotIn('Own Goal',[c['text'] for c in contexts(w.store.db,self.sid,'different-current-run',owner)])
        with w.store.db:w.store.db.execute("UPDATE goal_activations SET capture_hash='corrupt' WHERE request_id=?",(data['requestId'],))
        self.assertNotIn('Own Goal',[c['text'] for c in contexts(w.store.db,self.sid,w.run_id,owner)])

    async def test_stop_during_activation_keeps_original_receipt_without_second_effect(self):
        from goal_control import live_control
        w,native=await self.prepared();await w.goal_worker.start_control();goals=Goals(w.store)
        original=native.request;arrived=asyncio.Event();release=asyncio.Event()
        async def delayed(method,params,**kwargs):
            result=await original(method,params,**kwargs)
            if method=='thread/goal/set' and params.get('status')=='active':arrived.set();await release.wait()
            return result
        native.request=delayed
        data={'requestId':str(uuid.uuid4()),'revision':goals.snapshot(self.sid)['revision'],'action':'play','sessionRevision':1,'target':{'runId':w.run_id,'threadId':w.thread_id,'turnId':w.turn_id}}
        goals.accept(self.sid,data);task=asyncio.create_task(live_control(w.store,self.sid,data['requestId']))
        await asyncio.wait_for(arrived.wait(),1)
        transition(w.store,w.run_id,'stopping');await w.stop();release.set()
        receipt=await task;self.assertIn(receipt['state'],('unknown','confirmed'))
        self.assertEqual(native.goal['status'],'paused');self.assertTrue(w.stopping)
        self.assertEqual(sum(m=='thread/goal/set' and p.get('status')=='active' for m,p in native.calls),1)

    async def test_original_identity_change_blocks_control_before_mutation(self):
        from goal_control import live_control
        import json
        w,native=await self.prepared();await w.goal_worker.start_control();goals=Goals(w.store)
        data={'requestId':str(uuid.uuid4()),'revision':goals.snapshot(self.sid)['revision'],'action':'play','sessionRevision':1,'target':{'runId':w.run_id,'threadId':w.thread_id,'turnId':w.turn_id}}
        goals.accept(self.sid,data);meta=json.loads(get_run(w.store,w.run_id)['worker']);meta['birth']='other-process'
        transition(w.store,w.run_id,'running',worker=meta)
        with self.assertRaises(ProjectFault):await live_control(w.store,self.sid,data['requestId'])
        self.assertEqual(native.goal['status'],'paused')

    @unittest.skipIf(os.getuid()!=0,'Existing backup script is root-readable.')
    async def test_existing_backup_restore_preserves_live_play_ledger_without_replay(self):
        import json,shutil,sys
        from pathlib import Path
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from contextlib import closing
        from unittest.mock import patch
        from session_store import SessionStore
        w,native=await self.prepared();await w.goal_worker.start_control()
        receipt,data=await self.live(w,'play');await w.stop()
        sys.path.insert(1,str(Path(__file__).resolve().parents[3]/'Tools/Backup'))
        import backup
        from restore import restore
        root=self.root/'owned-backup';root.mkdir()
        for source in backup.SOURCES:
            path=root/source
            if source=='AGENTS.md':path.write_text('Owned Live Goal backup')
            else:path.mkdir(parents=True,exist_ok=True)
        shutil.copytree(self.projects,root/'App/Data/Projects',dirs_exist_ok=True)
        paths=backup.Paths(root,self.root/'mount',self.root/'mount/backup',self.root/'backup-state',self.root/'backup.lock');paths.mount.mkdir()
        result=backup.run(paths,lambda _:('owned-mount',),datetime(2026,10,28,4,tzinfo=ZoneInfo('Europe/Berlin')))
        restored=self.root/'restored';restore(paths.destination/result['archive'],restored)
        with closing(SessionStore(restored/'App/Data/Projects',self.r4os,self.pid)) as store:
            proof=LiveGoals(store).evidence(self.sid,data['requestId'])
            self.assertEqual(proof['goal']['objective'],'Own Goal')
            self.assertEqual(Goals(store).receipt(self.sid,data['requestId']),receipt)
        self.assertEqual(sum(m=='thread/goal/set' and p.get('status')=='active' for m,p in native.calls),1)

    async def test_coordinator_reconstruction_recognizes_originally_normal_live_goal_worker(self):
        from host import Host
        from unittest.mock import AsyncMock,patch
        w,native=await self.prepared();await w.goal_worker.start_control();receipt,data=await self.live(w,'play')
        host=Host({'projects':str(self.projects),'r4os':str(self.r4os),'providers':str(self.providers),'uid':os.getuid()})
        record=host.root/w.run_id;record.mkdir();(record/'worker.json').write_text('{}')
        meta={'projectId':self.pid,'sessionId':self.sid,'runId':w.run_id,'release':'own-fixture'}
        control=AsyncMock(return_value=str(os.getpid()))
        with patch.object(host,'metadata',return_value=meta),patch.object(host,'active_unit',AsyncMock(return_value=True)),patch.object(host,'check_unbound',AsyncMock()),patch('host.systemctl',control):
            await host.recover()
        self.assertEqual(host.active[w.run_id],meta)
        self.assertEqual(Goals(w.store).receipt(self.sid,data['requestId'])['state'],'confirmed')
        self.assertEqual(get_run(w.store,w.run_id)['state'],'running')
        self.assertTrue(all(call.args[0]=='show' for call in control.call_args_list))

    async def test_clock_begins_at_live_play_and_counts_until_paused_turn_ends(self):
        from goal_clock import GoalClock,snapshot
        w,native=await self.prepared();await w.goal_worker.start_control()
        tick=[100000000000];w.goal_worker.clock=GoalClock(w,lambda:tick[0])
        tick[0]+=30000000000;self.assertIsNone(snapshot(w.store,self.sid))
        receipt,_=await self.live(w,'play');self.assertEqual(receipt['state'],'confirmed')
        tick[0]+=4000000000;await self.live(w,'pause')
        tick[0]+=3000000000
        await w.notify('turn/completed',{'threadId':w.thread_id,'turn':{'id':'current-turn','status':'completed'}})
        await asyncio.wait_for(w.done.wait(),1)
        clock=snapshot(w.store,self.sid);self.assertEqual(clock['state'],'ended');self.assertEqual(clock['durationMs'],7000)
