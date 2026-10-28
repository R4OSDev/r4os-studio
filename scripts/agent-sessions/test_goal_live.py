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
        transition(w.store,w.run_id,'running',turn_id='current-turn',worker={'liveGoalPreparation':1,'liveGoalControl':1,'liveGoalOpen':True,'pid':os.getpid(),'birth':__import__('lease').birth(os.getpid())})
        self.addAsyncCleanup(w.goal_worker.close);self.addCleanup(w.store.close)
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
