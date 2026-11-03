"""Proven account scope, original admissions and native failures; no real quota."""
import asyncio
import copy
import datetime
import json
import os
import unittest
from types import SimpleNamespace
from attachment_store import birth
from provider_errors import describe
from test_zai_quota import ZaiQuota,body,rid
from zai_limits import refresh,state,observe
from zai_quota import normalize
from store import ProjectFault


class ZaiLimits(unittest.TestCase):
    setUp=ZaiQuota.setUp

    def original(self,provider=None,kind='project',model='glm-5.3'):
        provider=provider or self.provider
        run,owner,sid,request=(rid() for _ in range(4))
        selected={k:provider[k] for k in ('id','kind','baseUrl','protocol','auth','revision','credentialRevision')}
        config={'apiRunId':run,'apiProvider':selected,'model':model}
        return (run,kind,owner,sid,request,config)

    def quota(self,weekly=0,five=12000,reset=None):
        raw=body();raw['data']['limits'][0]['remaining']=five
        raw['data']['limits'][1]['remaining']=weekly
        raw['data']['limits'][1].pop('nextResetTime',None)
        if reset is not None:raw['data']['limits'][1]['nextResetTime']=reset
        with self.api.connect(write=True) as db:
            self.store.schema(db);refresh(db,self.provider,normalize(raw),datetime.datetime.now(datetime.timezone.utc).isoformat())

    def test_weekly_hold_shared_across_project_skill_queue_and_same_key_only(self):
        same=self.api.mutate('create',None,{**self.data,'requestId':rid(),'name':'Same own subscription'})['provider']
        other=self.api.mutate('create',None,{**self.data,'requestId':rid(),'name':'Different own subscription','key':'different-owned-key'})['provider']
        self.quota(weekly=0,five=12000)
        for provider,kind in ((self.provider,'project'),(same,'skill'),(same,'project')):
            with self.subTest(kind=kind),self.assertRaisesRegex(ProjectFault,'Weekly'):
                self.api.reserve(*self.original(provider,kind))
        self.api.reserve(*self.original(other,'skill'))
        self.assertIsNone(state(self.api.parent,other,'glm-5.3'))

    def test_unknown_monitor_is_not_a_hold_and_failure_does_not_clear_confirmed_hold(self):
        self.api.reserve(*self.original())
        self.quota()
        data={'requestId':rid(),'providerRevision':1};self.store.start_refresh(self.provider['id'],data)
        self.store.finish(self.provider['id'],data['requestId'],error='timeout')
        with self.assertRaises(ProjectFault):self.api.reserve(*self.original())
        with self.api.connect(write=True) as db:
            refresh(db,self.provider,normalize({'success':True,'data':{'limits':[]}}),datetime.datetime.now(datetime.timezone.utc).isoformat())
        with self.assertRaises(ProjectFault):self.api.reserve(*self.original())
        self.quota(weekly=1200)
        self.api.reserve(*self.original())
        self.assertIsNone(state(self.api.parent,self.provider,'glm-5.3'))

    def test_original_reservation_rechecked_before_claim_and_fresh_reset_does_not_start_work(self):
        args=self.original();self.api.reserve(*args)
        worker={'pid':os.getpid(),'birth':birth(os.getpid()),'release':'owned-test'}
        self.quota()
        with self.assertRaises(ProjectFault):self.api.claim(*args,worker)
        with self.api.connect() as db:self.assertEqual(db.execute('SELECT state FROM leases WHERE run_id=?',(args[0],)).fetchone()[0],'reserved')
        self.quota(weekly=100)
        with self.api.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM leases').fetchone()[0],1)
        self.assertEqual(self.api.claim(*args,worker),self.data['key'])

    def test_native_model_hold_original_and_other_model_and_rotation(self):
        args=self.original();self.api.reserve(*args)
        worker={'pid':os.getpid(),'birth':birth(os.getpid()),'release':'owned-test'}
        self.api.claim(*args,worker)
        evidence={'ordinal':1,'code':'1311','resetAt':None,'httpStatus':429,'event':'zai-limit'}
        observe(self.api.parent,args[-1]['apiProvider'],'glm-5.3',args[0],evidence)
        observe(self.api.parent,args[-1]['apiProvider'],'glm-5.3',args[0],evidence)
        with self.assertRaises(ProjectFault):self.api.reserve(*self.original())
        self.api.reserve(*self.original(model='glm-5.3-flash'))
        with self.assertRaises(ProjectFault):observe(self.api.parent,args[-1]['apiProvider'],'glm-5.3',rid(),evidence)
        with self.api.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM zai_native_limits').fetchone()[0],1)
        rotated=self.api.mutate('update',self.provider['id'],{'requestId':rid(),'revision':1,'key':'new-own-account-key'})['provider']
        self.api.reserve(*self.original(rotated))
        self.assertIsNotNone(state(self.api.parent,self.provider,'glm-5.3'))

    def test_only_native_reset_can_expire_the_hold(self):
        past=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=1)).timestamp()*1000
        self.quota(reset=past)
        self.api.reserve(*self.original())
        self.quota(reset=None)
        with self.assertRaises(ProjectFault):self.api.reserve(*self.original())

    def test_sanitized_native_http_and_sse_errors_keep_real_http_status(self):
        for safe,expected in [('zai_subscription_exhausted','zaiSubscriptionExhausted'),('zai_model_unavailable','zaiModelUnavailable'),('zai_subscription_expired','zaiSubscriptionExpired')]:
            raw=json.dumps({'error':{'code':safe,'message':'never-render-this-provider-text'}},separators=(',',':'))
            error={'codexErrorInfo':{'httpConnectionFailed':{'httpStatusCode':429}},'message':'unexpected status: 429 '+raw}
            result=describe(error,api=True)
            self.assertEqual(result['code'],expected);self.assertEqual(result['httpStatusCode'],429)
            self.assertFalse(result['transientCandidate']);self.assertNotIn('never-render',result['text'])
            self.assertEqual(describe({'codexErrorInfo':'other','message':'stream error: '+raw},True)['code'],expected)
        self.assertEqual(describe({'codexErrorInfo':{'httpConnectionFailed':{'httpStatusCode':429}}},True)['code'],'rateLimitExceeded')


class ActiveHold(unittest.IsolatedAsyncioTestCase):
    async def test_dual_stack_zai_selects_validated_ipv4_without_an_http_retry(self):
        import socket
        from unittest.mock import patch
        from api_runtime import resolve_binding
        binding={'kind':'zai-coding-plan','baseUrl':'https://api.z.ai/api/coding/paas/v4'}
        records=[(socket.AF_INET6,socket.SOCK_STREAM,6,'',('2606:4700::1111',443,0,0)),
                 (socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))]
        with patch('api_runtime.socket.getaddrinfo',return_value=records):
            self.assertEqual(await resolve_binding(binding),['8.8.8.8','2606:4700::1111'])
        records.append((socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443)))
        with patch('api_runtime.socket.getaddrinfo',return_value=records),self.assertRaises(ProjectFault):
            await resolve_binding(binding)

    async def test_host_hold_only_blocks_future_requests_without_stop_or_replay(self):
        from unittest.mock import patch,AsyncMock
        from zai_limit_guard import watch
        runtime=SimpleNamespace(block_subscription=AsyncMock())
        worker=SimpleNamespace(done=asyncio.Event(),stopping=False,api_runtime=runtime,manifest={'providers':'own'},config={'apiProvider':{},'model':'glm-5.3'})
        with patch('zai_limit_guard.state',return_value={'reason':'Own exhausted weekly window'}):await watch(worker)
        runtime.block_subscription.assert_awaited_once()


if __name__=='__main__':unittest.main()
