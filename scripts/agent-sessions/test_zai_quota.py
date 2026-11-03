"""Subscription semantics and private original receipts, using only own data."""
import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from api_provider_store import ApiProviders
from zai_policy import BASE_URL
from zai_quota import Quota,normalize,scope
from store import ProjectFault


def rid():return str(uuid.uuid4())


def body():
    return {'code':200,'success':True,'data':{'level':'pro','limits':[
        {'type':'CREDIT_LIMIT','unit':3,'number':5,'usage':12000,'currentValue':0,'remaining':12000,'percentage':0},
        {'type':'CREDIT_LIMIT','unit':6,'number':1,'usage':60000,'currentValue':60016,'remaining':0,'percentage':100,'nextResetTime':1793830124999}]}}


class ZaiQuota(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.api=ApiProviders(Path(self.temp.name));self.store=Quota(self.api.parent)
        self.data={'requestId':rid(),'name':'Own quota','kind':'zai-coding-plan','baseUrl':BASE_URL,
                   'protocol':'chat-completions','auth':'bearer','key':'own-subscription-fixture-key'}
        self.provider=self.api.mutate('create',None,self.data)['provider']

    def start(self,provider=None):
        provider=provider or self.provider
        data={'requestId':rid(),'providerRevision':provider['revision']}
        return data,self.store.start_refresh(provider['id'],data)[0]

    def test_credit_windows_independence_and_real_zero(self):
        value=normalize(body());five,week=value['limits']
        self.assertEqual((five['window'],week['window']),('5-hour','Weekly'))
        self.assertEqual(five['unit'],'credits');self.assertEqual(five['used'],0)
        self.assertEqual(week['remaining'],0);self.assertEqual(week['used'],60016)
        self.assertIsNone(five['resetAt']);self.assertIn('2026-',week['resetAt'])

    def test_unknown_units_types_and_missing_values_are_not_tokens_or_zero(self):
        original={'success':True,'data':{'limits':[{'type':'FUTURE_ALLOWANCE','unit':'future','number':17},{'type':'TOKENS_LIMIT'}]}}
        value=normalize(original)['limits'];self.assertEqual(value[0]['unit'],'unknown')
        self.assertEqual(value[0]['window'],'Provider window');self.assertIsNone(value[0]['remaining'])
        self.assertIsNone(value[1]['used']);self.assertEqual(value[1]['unit'],'tokens')
        self.assertEqual(original['data']['limits'][0]['type'],'FUTURE_ALLOWANCE')
        for invalid in ({'success':False,'data':{'limits':[]}}, {'data':{'limits':[None]}}, {'data':{'limits':[{}]*33}}):
            with self.assertRaises(ValueError):normalize(invalid)

    def test_original_refresh_idempotency_and_receipt_recovery(self):
        self.assertEqual(self.store.listing(self.provider['id'])['state'],'unknown')
        data,result=self.start();same,fresh=self.store.start_refresh(self.provider['id'],data)
        self.assertFalse(fresh);self.assertEqual(result,same)
        self.assertEqual(self.store.receipt(self.provider['id'],data['requestId'])['state'],'pending')
        done=self.store.finish(self.provider['id'],data['requestId'],body=body())
        self.assertEqual(self.store.receipt(self.provider['id'],data['requestId']),done)
        self.assertEqual(self.store.finish(self.provider['id'],data['requestId']),done)
        with self.assertRaises(ProjectFault):self.store.start_refresh(self.provider['id'],{**data,'providerRevision':99})
        sample=self.store.listing(self.provider['id']);self.assertEqual(sample['state'],'current')
        self.assertNotIn(self.data['key'],json.dumps(sample))
        with self.api.connect() as db:
            original=json.loads(self.store.request(db,self.provider['id'],data['requestId'])['binding'])
            self.assertEqual(original['quotaOriginal'],body())

    def test_monitor_failure_retains_stale_original_without_erasing_usage(self):
        first,_=self.start();self.store.finish(self.provider['id'],first['requestId'],body=body())
        second,_=self.start();self.store.finish(self.provider['id'],second['requestId'],error='timeout')
        sample=self.store.listing(self.provider['id']);self.assertEqual(sample['state'],'stale')
        self.assertEqual(sample['limits'][1]['remaining'],0);self.assertIn('timed out',sample['error'])
        with self.api.connect() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='statistic_api_wire'").fetchone())

    def test_key_rotation_never_shows_previous_accounts_quota(self):
        first,_=self.start();self.store.finish(self.provider['id'],first['requestId'],body=body())
        self.api.mutate('update',self.provider['id'],{'requestId':rid(),'revision':1,'key':'other-own-account-key'})
        sample=self.store.listing(self.provider['id']);self.assertEqual(sample['state'],'unknown');self.assertEqual(sample['limits'],[])

    def test_scope_shares_identical_keys_and_keeps_other_accounts_separate(self):
        second=self.api.mutate('create',None,{**self.data,'requestId':rid(),'name':'Same own account'})['provider']
        third=self.api.mutate('create',None,{**self.data,'requestId':rid(),'name':'Other own account','key':'other-key'})['provider']
        with self.api.connect(write=True) as db:
            self.store.schema(db)
            one=scope(db,self.provider,True);two=scope(db,second,True);other=scope(db,third,True)
            self.assertEqual(one,two);self.assertNotEqual(one,other)
            self.assertNotIn(self.data['key'],one)

    def test_reflected_secret_is_rejected_and_not_persisted_in_monitor_records(self):
        data,_=self.start();raw=body();raw['data']['level']=self.data['key']
        result=self.store.finish(self.provider['id'],data['requestId'],body=raw)
        self.assertEqual(result['state'],'failed');self.assertEqual(self.store.listing(self.provider['id'])['limits'],[])
        self.assertNotIn(self.data['key'].encode(),(self.api.root/'Providers.sqlite').read_bytes())


if __name__=='__main__':unittest.main()
