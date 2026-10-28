"""Live-Play provenance and dormant native admission, using private fixtures."""
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
        transition(w.store,w.run_id,'running',turn_id='current-turn',worker={'liveGoalPreparation':1})
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
