"""Continuation limits, ordered observations and per-turn evidence."""
import asyncio
import json
import unittest
from unittest.mock import patch
import test_goal_control as controls
from goal_store import Goals
from run_store import item


class GoalWorkerTests(unittest.IsolatedAsyncioTestCase):
    setUp=controls.GoalControlTests.setUp
    tearDown=controls.GoalControlTests.tearDown
    open=controls.GoalControlTests.open
    command=controls.GoalControlTests.command
    goal_worker=controls.GoalControlTests.goal_worker

    async def test_queued_user_input_pauses_native_continuation_before_handoff(self):
        from message_store import Messages
        import uuid
        w,native=await self.goal_worker()
        await w.goal_worker.before_resume();await w.goal_worker.activate()
        Messages(w.store).accept(self.sid,{'requestId':str(uuid.uuid4()),'revision':1,'mode':'queue','text':'Next human task'},self.providers)
        await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'boundary'}})
        await w.notify('turn/completed',{'threadId':w.thread_id,'turn':{'id':'boundary','status':'completed'}})
        await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'racing-continuation'}})
        await asyncio.sleep(.05)
        await w.notify('turn/completed',{'threadId':w.thread_id,'turn':{'id':'racing-continuation','status':'interrupted'}})
        await asyncio.sleep(.2)
        self.assertTrue(w.goal_worker.queue_handoff)
        self.assertEqual(w.goal_worker.native['status'],'paused')
        self.assertTrue(w.done.is_set());self.assertEqual(w.outcome,'completed')
        self.assertFalse(Messages(w.store).snapshot(self.sid)['held'])

    async def test_late_read_cannot_replace_newer_native_notification_in_same_second(self):
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'own-turn'}})
        original=native.request;arrived=asyncio.Event();release=asyncio.Event()
        async def delayed(method,params,**kwargs):
            if method=='thread/goal/get':
                result={'goal':native.goal.copy()};arrived.set();await release.wait();return result
            return await original(method,params,**kwargs)
        with patch.object(native,'request',side_effect=delayed):
            task=asyncio.create_task(w.goal_worker.read());await arrived.wait()
            native.goal['status']='paused'
            await w.notify('thread/goal/updated',{'threadId':w.thread_id,'goal':native.goal.copy()})
            release.set();value=await task
        self.assertEqual(value['status'],'paused');self.assertEqual(Goals(w.store).snapshot(self.sid)['goal']['status'],'paused')

    async def test_native_limits_end_execution_without_claiming_goal_complete_or_setting_budget(self):
        for status in ('usageLimited','budgetLimited','blocked'):
            w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
            native.goal['status']=status
            await w.notify('thread/goal/updated',{'threadId':w.thread_id,'goal':native.goal.copy()})
            await asyncio.wait_for(w.done.wait(),1)
            self.assertEqual(Goals(w.store).snapshot(self.sid)['goal']['status'],status)
            self.assertNotEqual(Goals(w.store).snapshot(self.sid)['goal']['status'],'complete')
            self.assertFalse(any('tokenBudget' in params for _,params in native.calls))
            # Close this fixture execution before explicitly admitting another.
            from run_store import transition
            transition(w.store,w.run_id,'completed');await w.goal_worker.close();w.store.close()
            # Each independent native fixture starts without an earlier binding.
            with self.open() as store,store.db:
                store.db.execute('DELETE FROM session_goals');store.db.execute('UPDATE sessions SET thread_id=NULL')

    async def test_multiple_turn_history_is_correlated_and_usage_does_not_conflict_with_pause(self):
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'first'}})
        item(w.store,self.sid,w.run_id,{'id':'first-result','runId':w.run_id,'type':'assistant','text':'Own first result'})
        await w.notify('turn/completed',{'threadId':w.thread_id,'turn':{'id':'first','status':'completed'}})
        await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'second'}})
        item(w.store,self.sid,w.run_id,{'id':'second-result','runId':w.run_id,'type':'assistant','text':'Own second result'})
        goals=Goals(w.store);before=goals.snapshot(self.sid)['revision'];native.goal.update(tokensUsed=123,timeUsedSeconds=9)
        await w.notify('thread/goal/updated',{'threadId':w.thread_id,'goal':native.goal.copy()})
        self.assertEqual(goals.snapshot(self.sid)['revision'],before)
        history=w.store.history(self.sid)['items'];self.assertEqual([i['turnId'] for i in history],['first','second'])
        events=[json.loads(row[0]) for row in w.store.db.execute("SELECT payload FROM events WHERE kind='nativeTurn'")]
        self.assertEqual([(e['id'],e['status']) for e in events],[('first','running'),('first','completed'),('second','running')])

    async def test_unconfirmed_effect_pauses_but_remains_unknown_and_cannot_autoresume(self):
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        w.uncertain_effect=True;await w.goal_worker.pause()
        await asyncio.wait_for(w.done.wait(),1)
        self.assertEqual(native.goal['status'],'paused');self.assertEqual(w.outcome,'unknown')
        self.assertEqual(Goals(w.store).snapshot(self.sid)['phase'],'unknown')
        self.assertTrue(any(params.get('origin')=='automatic' for method,params in native.calls if method=='thread/goal/set'))

    async def test_image_limit_releases_rpc_reader_before_goal_pause_reply(self):
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        w.config['nativeImageGeneration']=True
        await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'own-image-turn'}})
        original=native.request;reply=asyncio.Event()
        async def waiting(method,params,**kwargs):
            if method=='thread/goal/get':await reply.wait()
            return await original(method,params,**kwargs)
        try:
            with patch.object(native,'request',side_effect=waiting):
                await asyncio.wait_for(w.notify('item/completed',{'threadId':w.thread_id,'item':{'id':'limited-image','type':'imageGeneration','status':'failed','failure':{'type':'usageLimitExceeded'}}}),0.2)
                self.assertTrue(w.stopping);reply.set();await asyncio.wait_for(w.stop_task,1)
            self.assertEqual(native.goal['status'],'paused');self.assertTrue(w.done.is_set())
            self.assertFalse(any(method=='turn/start' for method,_ in native.calls))
            self.assertEqual(len([i for i in w.store.history(self.sid)['items'] if i.get('id')=='limited-image']),1)
        finally:
            reply.set();await w.goal_worker.close();w.store.close()

    async def test_unconfirmed_native_image_failure_pauses_goal_and_preserves_unknown_outcome(self):
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        w.config['nativeImageGeneration']=True
        try:
            await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'own-image-turn'}})
            await w.notify('item/completed',{'threadId':w.thread_id,'item':{'id':'unconfirmed-image','type':'imageGeneration','status':'failed','failure':None}})
            await asyncio.wait_for(w.stop_task,1)
            state=Goals(w.store).snapshot(self.sid)
            self.assertEqual(native.goal['status'],'paused');self.assertEqual(state['phase'],'unknown');self.assertEqual(w.outcome,'unknown')
            value=next(i for i in w.store.history(self.sid)['items'] if i['id']=='unconfirmed-image')
            self.assertEqual(value['status'],'unknown');self.assertTrue(value['partialChangesPossible'])
            self.assertFalse(any(method=='turn/start' for method,_ in native.calls))
        finally:await w.goal_worker.close();w.store.close()

    async def test_missing_native_turn_end_is_unknown_without_rewriting_prior_completed_turn(self):
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'finished'}})
        await w.notify('turn/completed',{'threadId':w.thread_id,'turn':{'id':'finished','status':'completed'}})
        await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'lost'}})
        from goal_worker import end_turns
        end_turns(w.store,w.run_id)
        rows={r['turn_id']:r['status'] for r in w.store.db.execute('SELECT * FROM goal_turns')}
        self.assertEqual(rows,{'finished':'completed','lost':'unknown'})

    async def test_native_waiting_input_pauses_continuation_without_granting_new_tools(self):
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'waiting-turn'}})
        permissions=dict(w.config['permissions'])
        await w.notify('thread/status/changed',{'threadId':w.thread_id,'status':{'type':'active','activeFlags':['waitingOnUserInput']}})
        for _ in range(50):
            if native.goal['status']=='paused':break
            await asyncio.sleep(.01)
        self.assertEqual(native.goal['status'],'paused');self.assertEqual(w.config['permissions'],permissions)
        self.assertFalse(w.done.is_set())

    async def test_a_different_native_goal_requires_another_explicit_play(self):
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        native.goal['objective']='Another objective not accepted by this Play'
        await w.notify('thread/goal/updated',{'threadId':w.thread_id,'goal':native.goal.copy()})
        self.assertTrue(w.stopping)
        await asyncio.wait_for(w.done.wait(),1)
        self.assertEqual(native.goal['status'],'paused');self.assertIn('Review it',w.error)
        self.assertEqual(w.config['goalExecution']['objective'],'Own Goal')

    async def test_a_completed_goal_cannot_silently_start_the_same_goal_again(self):
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'own-turn'}})
        native.goal['status']='complete'
        await w.notify('thread/goal/updated',{'threadId':w.thread_id,'goal':native.goal.copy()})
        native.goal['status']='active'
        await w.notify('thread/goal/updated',{'threadId':w.thread_id,'goal':native.goal.copy()})
        self.assertTrue(w.stopping)
        await asyncio.wait_for(w.done.wait(),1)
        self.assertEqual(native.goal['status'],'paused')

    async def test_play_is_bound_to_the_goal_observed_at_the_original_user_request(self):
        from test_goal_control import Native
        from run_store import admit
        from store import ProjectFault
        import uuid
        native=Native()
        with self.open() as store:
            await self.command(store,native)
            goals=Goals(store);rid=str(uuid.uuid4())
            goals.accept(self.sid,{'requestId':rid,'revision':goals.snapshot(self.sid)['revision'],'action':'play','sessionRevision':1})
            native.goal['objective']='Changed after original Play'
            goals.observe(self.sid,native.thread,native.goal.copy())
            with self.assertRaises(ProjectFault):admit(store,self.sid,{'mode':'goal','goalRequestId':rid,'requestId':rid,'revision':1},self.providers)
            self.assertFalse(store.db.execute('SELECT 1 FROM runs').fetchone())
