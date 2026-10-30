"""Current native quota events, shared holds and explicit new Play authority."""
import asyncio
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import uuid

from claude_admission import explicit_resume
from claude_goal_worker import ClaudeGoalRuntime
from claude_quota_guard import block,effective_hold,watch
from claude_quota_store import QuotaStore
from claude_limits_policy import usage_sample
from claude_worker import ClaudeWorker
from message_store import Messages
from host import Host
from run_store import admit
import test_claude_goal as goal_fixture
import test_claude_messages as message_fixture


class QuotaGuard(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.f=message_fixture.ClaudeMessages();self.f.setUp();self.addCleanup(self.f.doCleanups)

    def worker(self):
        store=self.enterContext(self.f.open())
        run,_=admit(store,self.f.sid,{'requestId':str(uuid.uuid4()),'revision':1,'text':'Owned quota boundary'},self.f.providers)
        w=self.f.receiver(store,run);w.manifest={'providers':str(self.f.providers)}
        w.done=asyncio.Event();w.quota_blocked=None;w.claude_goal=None;w.admission_denial=None
        w.broker=SimpleNamespace(stop_admission=Mock());w.input_usage=SimpleNamespace(notify=Mock());w.sent=True
        w.defer_stop=Mock(side_effect=lambda:setattr(w,'stopping',True))
        return w

    async def test_native_subscription_rejection_closes_tools_and_holds_the_original_queue(self):
        w=self.worker();Messages(w.store).accept(self.f.sid,self.f.message_input(),self.f.providers)
        def frame(status):return {'native':{'type':'rate_limit_event','session_id':self.f.native,
            'rate_limit_info':{'status':status,'rateLimitType':'five_hour','utilization':1,'overageEnabled':False}},
            'identity':{'nativeSessionId':self.f.native}}
        await ClaudeWorker.observe(w,frame('allowed_warning'))
        self.assertIsNone(w.quota_blocked);w.defer_stop.assert_not_called()
        await ClaudeWorker.observe(w,frame('rejected'))
        self.assertIsNotNone(w.quota_blocked);w.broker.stop_admission.assert_called_once();w.defer_stop.assert_called_once()
        self.assertEqual(w.outcome,'failed');self.assertTrue(Messages(w.store).snapshot(self.f.sid)['held'])
        self.assertFalse(block(w,w.quota_blocked));w.defer_stop.assert_called_once()

    async def test_a_shared_hold_stops_an_admitted_worker_without_resuming_other_work(self):
        w=self.worker();quota=QuotaStore(self.f.providers)
        held=quota.record(w.config['providerId'],denial={'reasonCode':'subscription_limit','reason':'Owned native subscription limit'})['hold']
        await watch(w)
        self.assertEqual(w.quota_blocked,held);self.assertTrue(w.stopping);w.defer_stop.assert_called_once()
        self.assertEqual(quota.read(w.config['providerId'])['hold'],held)

    async def test_session_read_uses_fresh_original_sample_and_exposes_the_account_hold(self):
        w=self.worker();provider=self.f.provider_value
        sample=usage_sample({'subscription_type':'pro','rate_limits_available':True,'rate_limits':{
            'five_hour':{'utilization':100},'seven_day':{'utilization':20},'extra_usage':{'is_enabled':False},'limits':[]}},provider,w.row['request_id'])
        hold=QuotaStore(self.f.providers).record(provider['id'],sample=sample,
            denial={'reasonCode':'subscription_limit','reason':'Owned reported quota'})['hold']
        host=Host({'projects':str(self.f.projects),'r4os':str(self.f.r4os),'providers':str(self.f.providers),'uid':os.getuid()})
        value=await host.handle({'operation':'session_claude_limits','projectId':self.f.pid,'sessionId':self.f.sid})
        self.assertEqual(value['limits'],sample);self.assertEqual(value['hold'],hold)
        self.assertEqual(QuotaStore(self.f.providers).read(provider['id'])['hold'],hold)

    async def test_resuming_one_account_does_not_authorize_another_old_input(self):
        w=self.worker();quota=QuotaStore(self.f.providers)
        data=self.f.message_input();Messages(w.store).accept(self.f.sid,data,self.f.providers)
        held=quota.record(w.config['providerId'],denial={'reasonCode':'subscription_limit','reason':'Owned account hold'})['hold']
        saved=quota.release(w.config['providerId'],held,str(uuid.uuid4()))
        self.assertIsNone(saved['hold']);self.assertEqual(effective_hold(w,saved),held)
        dispatched=SimpleNamespace(store=w.store,session_id=w.session_id,config={},
            row={'request_id':data['requestId'],'created_at':'2999-01-01T00:00:00+00:00'})
        self.assertEqual(effective_hold(dispatched,saved),held)
        w.quota_authorized_through=held['id'];self.assertIsNone(effective_hold(w,saved))

    async def test_only_a_new_human_play_can_release_a_hold_not_an_automatic_step(self):
        f=goal_fixture.ClaudeGoal();f.setUp();self.addCleanup(f.doCleanups)
        w,journal=f.prepare();w.sent=False;w.done=asyncio.Event();w.error=None;w.quota_blocked=None
        runtime=ClaudeGoalRuntime(w);runtime.journal=journal;runtime.started=True;w.claude_goal=runtime
        hold={'createdAt':'2000-01-01T00:00:00+00:00'}
        self.assertTrue(explicit_resume(w,hold,'own-account'))
        f.active(journal)
        journal.report({'status':'continue','reason':'One owned step remains.'},'owned-first-report')
        self.assertTrue(journal.result(f.native_result()));journal.next()
        self.assertFalse(explicit_resume(w,hold,'own-account'))
        f.active(journal)
        journal.report({'status':'continue','reason':'Another owned step remains.'},'owned-second-report')
        self.assertTrue(journal.result(f.native_result()))
        journal.stop('Owned quota pause')
        self.assertEqual(journal.read()['state'],'closing')
        runtime.stop();self.assertEqual(journal.read()['reason'],'Owned quota pause')
