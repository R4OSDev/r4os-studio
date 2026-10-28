"""Owned session/lease/native-RPC fixtures; no inference or provider credentials."""
import asyncio
import fcntl
import json
import unittest
import uuid
from unittest.mock import patch
import test_runs as fixtures
from goal_control import idle_control, live_control
from goal_store import Goals, exists
from owner import open_lock
from run_store import admit, get_run, transition
from session_store import encode
from store import ProjectFault
from worker import Worker, finalize


class Native:
    def __init__(self): self.goal=None;self.calls=[];self.thread=str(uuid.uuid4());self.lost=False;self.notify=None
    def factory(self,args,notification,tool): self.notify=notification;return self
    async def start(self): pass
    async def close(self): pass
    async def request(self,method,params,**kwargs):
        self.calls.append((method,params.copy()))
        if method=='thread/start': return {'thread':{'id':self.thread}}
        if method=='thread/goal/get': return {'goal':self.goal.copy() if self.goal else None}
        if method=='thread/goal/clear': self.goal=None;return {'cleared':True}
        if method=='thread/goal/set':
            self.goal={**(self.goal or {'threadId':self.thread,'tokensUsed':0,'timeUsedSeconds':0,'createdAt':1,'updatedAt':1}),
                       **{k:params[k] for k in ('objective','status') if k in params}}
            if self.lost: self.lost=False;raise asyncio.TimeoutError()
            return {'goal':self.goal.copy()}
        if method=='turn/interrupt': return {}
        raise AssertionError('Unexpected native request: '+method)


class GoalControlTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fixtures.Runs.setUp(self)
        from profile import LEGACY_PROFILE, CODEX_VERSION, CODEX_SHA256
        with self.open() as store, store.db:
            store.db.execute('UPDATE sessions SET engine=?',(encode({'profile':LEGACY_PROFILE,'version':CODEX_VERSION,'sha256':CODEX_SHA256}),))
    tearDown=fixtures.Runs.tearDown
    open=fixtures.Runs.open

    async def command(self,store,native,action='save',text='Own Goal',rid=None,revision=None):
        goals=Goals(store);data={'requestId':rid or str(uuid.uuid4()),'revision':goals.snapshot(self.sid)['revision'] if revision is None else revision,'action':action}
        if action=='save': data['objective']=text
        receipt,fresh=goals.accept(self.sid,data)
        if fresh:
            with patch('goal_control.prepare',return_value=([],{})):
                receipt=await idle_control(store,self.sid,data['requestId'],self.providers,native.factory)
        return receipt,data

    async def test_idle_save_materializes_same_native_thread_without_any_turn_and_survives_reopen(self):
        native=Native()
        with self.open() as store:
            self.assertIsNone(Goals(store).snapshot(self.sid)['goal']);self.assertFalse(exists(store))
            receipt,data=await self.command(store,native)
            self.assertEqual(receipt['state'],'confirmed');self.assertEqual(receipt['snapshot']['goal']['status'],'paused')
            self.assertEqual(store.row(self.sid)['thread_id'],native.thread)
            self.assertFalse(store.db.execute('SELECT 1 FROM runs').fetchone())
        with self.open() as store:
            original=Goals(store).receipt(self.sid,data['requestId'])
            self.assertEqual(original,receipt);self.assertEqual(Goals(store).snapshot(self.sid)['lastIntent'],'save')
        self.assertFalse(any(method.startswith('turn/') for method,_ in native.calls))

    async def test_same_text_preserves_usage_lost_reply_is_read_once_and_empty_save_keeps_thread(self):
        native=Native()
        with self.open() as store:
            await self.command(store,native);native.goal.update(tokensUsed=317,timeUsedSeconds=43)
            native.lost=True;receipt,_=await self.command(store,native,text=' Own Goal ')
            self.assertEqual(receipt['state'],'confirmed');self.assertEqual(receipt['snapshot']['goal']['tokensUsed'],317)
            calls=[params for method,params in native.calls if method=='thread/goal/set']
            self.assertEqual(len(calls),2);self.assertNotIn('objective',calls[-1]);self.assertNotIn('tokenBudget',calls[-1])
            cleared,_=await self.command(store,native,text='\n ')
            self.assertIsNone(cleared['snapshot']['goal']);self.assertEqual(store.row(self.sid)['thread_id'],native.thread)

    async def test_original_request_fingerprint_conflicts_and_owner_lease_prevent_effect(self):
        native=Native()
        with self.open() as store:
            receipt,data=await self.command(store,native);count=len(native.calls)
            duplicate,fresh=Goals(store).accept(self.sid,data);self.assertFalse(fresh);self.assertEqual(duplicate,receipt)
            with self.assertRaises(ProjectFault): Goals(store).accept(self.sid,{**data,'objective':'Other'})
            with self.assertRaises(ProjectFault): Goals(store).accept(self.sid,{**data,'requestId':str(uuid.uuid4())})
            with open_lock(self.projects,'project',self.pid) as lease:
                fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
                denied,_=await self.command(store,native,text='Must not replace')
            self.assertEqual(denied['state'],'failed');self.assertEqual(len(native.calls),count)
            self.assertEqual(Goals(store).snapshot(self.sid)['goal']['objective'],'Own Goal')

    async def test_pending_command_locks_settings_and_run_admission_then_recovery_never_replays(self):
        with self.open() as store:
            goals=Goals(store);data={'requestId':str(uuid.uuid4()),'revision':0,'action':'save','objective':'Pending'}
            goals.accept(self.sid,data)
            with self.assertRaises(ProjectFault): store.update(self.sid,{'revision':1,'name':'Changed'},self.providers)
            with self.assertRaises(ProjectFault): admit(store,self.sid,self.data,self.providers)
            goals.stage(self.sid,data['requestId'],'native_mutation');goals.recover()
            self.assertEqual(goals.receipt(self.sid,data['requestId'])['state'],'unknown')
            with self.assertRaises(ProjectFault): goals.accept(self.sid,{**data,'requestId':str(uuid.uuid4()),'revision':goals.snapshot(self.sid)['revision']})
            native=Native();paused,_=await self.command(store,native,action='pause')
            self.assertEqual(paused['state'],'confirmed');self.assertEqual(paused['snapshot']['lastIntent'],'pause')
            self.assertFalse(native.calls)

    async def goal_worker(self):
        native=Native()
        with self.open() as store:
            await self.command(store,native)
            receipt,_=Goals(store).accept(self.sid,{'requestId':str(uuid.uuid4()),'revision':Goals(store).snapshot(self.sid)['revision'],'action':'play','sessionRevision':1})
            run,_=admit(store,self.sid,{'requestId':receipt['requestId'],'revision':1,'mode':'goal','goalRequestId':receipt['requestId']},self.providers)
        w=Worker({'projects':str(self.projects),'r4os':str(self.r4os),'projectId':self.pid,'runId':run['id'],'release':'own-fixture'})
        w.client=native;w.thread_id=native.thread
        from lease import birth
        import os
        transition(w.store,w.run_id,'starting',worker={'pid':os.getpid(),'birth':birth(os.getpid()),'release':'own-fixture'})
        self.addAsyncCleanup(w.goal_worker.close);self.addCleanup(w.store.close)
        return w,native

    async def test_play_admits_without_fake_message_and_native_turn_end_does_not_complete_goal(self):
        w,native=await self.goal_worker();snapshot=json.loads(get_run(w.store,w.run_id)['config'])
        self.assertEqual(w.store.history(self.sid)['items'],[])
        await w.goal_worker.before_resume();await w.goal_worker.activate()
        for tid in ('first','second'):
            await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':tid}})
            await w.notify('turn/completed',{'threadId':w.thread_id,'turn':{'id':tid,'status':'completed'}})
            await asyncio.sleep(.12);self.assertFalse(w.done.is_set())
        self.assertEqual(json.loads(get_run(w.store,w.run_id)['config']),snapshot)
        self.assertEqual(w.store.db.execute('SELECT COUNT(*) FROM goal_turns').fetchone()[0],2)
        self.assertFalse(any(method=='turn/start' for method,_ in native.calls))
        native.goal['status']='complete';await w.notify('thread/goal/updated',{'threadId':w.thread_id,'goal':native.goal.copy()})
        await asyncio.wait_for(w.done.wait(),1);self.assertEqual(w.outcome,'completed')

    async def test_live_pause_receipt_keeps_current_turn_and_stop_clear_intents_are_distinct(self):
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'in-flight'}})
        goals=Goals(w.store);receipt,_=goals.accept(self.sid,{'requestId':str(uuid.uuid4()),'revision':goals.snapshot(self.sid)['revision'],'action':'pause'})
        result=await live_control(w.store,self.sid,receipt['requestId'])
        self.assertEqual(result['state'],'confirmed');self.assertEqual(result['snapshot']['phase'],'pausing')
        self.assertEqual(native.goal['status'],'paused');self.assertFalse(w.done.is_set())
        await w.notify('turn/completed',{'threadId':w.thread_id,'turn':{'id':'in-flight','status':'completed'}})
        await asyncio.wait_for(w.done.wait(),1)
        self.assertEqual(goals.snapshot(self.sid)['goal']['objective'],'Own Goal')

    async def test_lost_worker_keeps_native_uncertainty_and_requires_explicit_pause(self):
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        Goals(w.store).lost_worker(w.run_id);snapshot=Goals(w.store).snapshot(self.sid)
        self.assertEqual(snapshot['phase'],'unknown');self.assertEqual(snapshot['goal']['status'],'active')
        with self.assertRaises(ProjectFault): Goals(w.store).accept(self.sid,{'requestId':str(uuid.uuid4()),'revision':snapshot['revision'],'action':'play','sessionRevision':1})
        self.assertEqual(sum(method=='thread/goal/set' and params.get('status')=='active' for method,params in native.calls),1)

    async def live_exit(self,action,text=None):
        from host import Host
        import os
        w,native=await self.goal_worker();await w.goal_worker.before_resume();await w.goal_worker.activate()
        await w.notify('turn/started',{'threadId':w.thread_id,'turn':{'id':'old-turn'}})
        goals=Goals(w.store);data={'requestId':str(uuid.uuid4()),'revision':goals.snapshot(self.sid)['revision'],'action':action}
        if action=='save':data['objective']=text
        goals.accept(self.sid,data);ended=[]
        async def stop_unit(*args):
            self.assertEqual(args,('stop','r4os-studio-agent@'+w.run_id+'.service'))
            self.assertEqual(native.goal['status'],'paused')
            await w.stop();await w.cleanup();ended.append(True);return ''
        async def after_exit(*args):
            self.assertTrue(ended);self.assertEqual(get_run(w.store,w.run_id)['busy'],0)
            return await idle_control(*args,rpc_factory=native.factory)
        host=Host({'projects':str(self.projects),'r4os':str(self.r4os),'providers':str(self.providers),'uid':os.getuid()})
        with patch('host.systemctl',side_effect=stop_unit),patch('goal_control.idle_control',side_effect=after_exit),patch('goal_control.prepare',return_value=([],{})):
            await host.goal_command('project',self.pid,self.sid,data['requestId'])
        result=goals.receipt(self.sid,data['requestId']);self.assertEqual(result['state'],'confirmed',result)
        self.assertTrue(ended);self.assertEqual(result['snapshot']['lastIntent'],action)
        self.assertEqual(result['snapshot']['goal']['status'],'paused')
        self.assertEqual(result['snapshot']['goal']['objective'],text if action=='save' else 'Own Goal')
        self.assertFalse(any(method=='turn/start' for method,_ in native.calls))

    async def test_active_goal_save_waits_for_old_worker_end_before_replacing_objective(self):
        await self.live_exit('save','Replacement after worker end')

    async def test_stop_pauses_then_uses_existing_run_stop_and_keeps_objective(self):
        await self.live_exit('stop')

    async def test_stale_session_settings_cannot_activate_a_goal_with_another_model_choice(self):
        native=Native()
        with self.open() as store:
            await self.command(store,native)
            store.update(self.sid,{'revision':1,'name':'Changed in another browser'},self.providers)
            goals=Goals(store);rid=str(uuid.uuid4());before=len(native.calls)
            with self.assertRaises(ProjectFault):goals.accept(self.sid,{'requestId':rid,'revision':goals.snapshot(self.sid)['revision'],'sessionRevision':1,'action':'play'})
            self.assertEqual(len(native.calls),before);self.assertFalse(store.db.execute('SELECT 1 FROM runs').fetchone())
            receipt,fresh=goals.accept(self.sid,{'requestId':rid,'revision':goals.snapshot(self.sid)['revision'],'sessionRevision':2,'action':'play'})
            self.assertTrue(fresh);self.assertEqual(receipt['state'],'pending')


class GoalSkillControls(unittest.IsolatedAsyncioTestCase):
    from test_skills import Skills as fixtures
    setUp=fixtures.setUp
    tearDown=fixtures.tearDown
    open=fixtures.open
    settings=fixtures.settings

    async def test_skill_native_goal_uses_same_contract_and_cannot_be_read_by_another_owner(self):
        native=Native();sid=self.session['id'];rid=str(uuid.uuid4())
        with self.open() as store:
            goals=Goals(store);goals.accept(sid,{'requestId':rid,'revision':0,'action':'save','objective':'Own skill goal'})
            with patch('goal_control.prepare',return_value=([],{})):
                result=await idle_control(store,sid,rid,self.providers,native.factory)
            self.assertEqual(result['state'],'confirmed');self.assertEqual(result['snapshot']['owner'],{'type':'skill','id':self.ids[0]})
            self.assertEqual(store.row(sid)['thread_id'],native.thread)
        with self.open(self.ids[1]) as other:
            with self.assertRaises(ProjectFault): Goals(other).snapshot(sid)
            with self.assertRaises(ProjectFault): Goals(other).receipt(sid,rid)
        self.assertFalse(self.projects.exists());self.assertFalse(any(method.startswith('turn/') for method,_ in native.calls))
