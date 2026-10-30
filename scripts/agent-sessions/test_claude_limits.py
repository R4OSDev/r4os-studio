"""Native quota/overage policy, not estimates from model token counters."""
import copy
import json
import time
import unittest
import uuid

from claude_limits_policy import usage_sample,event_sample,admission


class NativeLimits(unittest.TestCase):
    def setUp(self):
        self.provider={'id':str(uuid.uuid4()),'revision':2,'status':'connected','account':{'email':'own@example.test',
            'orgId':'own-org','orgName':'Own fixture','plan':'pro','authMethod':'claude.ai','apiProvider':'firstParty','checkedAt':'own receipt'}}
        self.data={'subscription_type':'pro','rate_limits_available':True,'rate_limits':{
            'five_hour':{'utilization':25,'resets_at':'2026-10-30T15:00:00Z'},
            'seven_day':{'utilization':50,'resets_at':None},'extra_usage':{'is_enabled':False},'limits':[]},
            'behaviors':{'private_unrelated_history':'must never persist'},'session':{'total_cost_usd':123456}}
        self.auth={'returncode':0,'output':json.dumps({'loggedIn':True,'authMethod':'claude.ai','apiProvider':'firstParty',
            'configDirectory':'/config','subscriptionType':'pro','email':'own@example.test','orgId':'own-org','orgName':'Own fixture'})}
        self.account={'subscriptionType':'Claude Pro','apiProvider':'firstParty','email':'own@example.test'}
        self.binding={'nativeSessionId':str(uuid.uuid4()),'model':'own-sonnet-model'}
    def sample(self,data=None):return usage_sample(data or self.data,self.provider,str(uuid.uuid4()))
    def gate(self,sample=None,**extra):
        return admission(sample or self.sample(),self.provider,self.auth,self.account,self.binding,extra.pop('started_at',time.time()),**extra)

    def test_original_usage_units_scope_reset_and_no_behaviors_or_cost_to_quota(self):
        sample=self.sample();self.assertEqual(sample['coverage'],'available')
        self.assertEqual(sample['windows'][0]['usedPercent'],25);self.assertEqual(sample['windows'][0]['remainingPercent'],75)
        self.assertEqual(sample['windows'][0]['resetsAt'],'2026-10-30T15:00:00+00:00')
        self.assertIsNone(sample['windows'][1]['resetsAt'])
        self.assertNotIn('behaviors',sample);self.assertNotIn('session',sample)
        self.assertTrue(self.gate(sample)['allowed'])

    def test_extra_usage_absent_enabled_malformed_unknown_or_stale_never_admits(self):
        for extra in [None,{}, {'is_enabled':True},{'is_enabled':0},{'is_enabled':'false'}]:
            data=copy.deepcopy(self.data);data['rate_limits']['extra_usage']=extra
            self.assertFalse(self.gate(self.sample(data))['allowed'])
        data=copy.deepcopy(self.data);data['rate_limits']['five_hour']['utilization']=None
        sample=self.sample(data);self.assertEqual(sample['coverage'],'partial')
        self.assertIsNone(sample['windows'][0]['remainingPercent']);self.assertFalse(self.gate(sample)['allowed'])
        for value in [True,float('nan'),-1,101,'25']:
            data=copy.deepcopy(self.data);data['rate_limits']['five_hour']['utilization']=value
            self.assertEqual(self.sample(data)['coverage'],'unavailable')
        self.assertFalse(self.gate(started_at=time.time()-21)['allowed'])

    def test_actual_account_auth_plan_binding_and_exhaustion_win(self):
        for change in [{'apiProvider':'vertex'},{'tokenSource':'ANTHROPIC_AUTH_TOKEN'},{'apiKeySource':'apiKeyHelper'},
                {'email':'foreign@example.test'},{'subscriptionType':'Claude Max'}]:
            saved=self.account;self.account={**saved,**change};self.assertFalse(self.gate()['allowed']);self.account=saved
        for change in [{'authMethod':'api_key'},{'configDirectory':'/foreign'},{'orgId':'foreign-org'}]:
            saved=self.auth;self.auth={**saved,'output':json.dumps({**json.loads(saved['output']),**change})}
            self.assertFalse(self.gate()['allowed']);self.auth=saved
        data=copy.deepcopy(self.data);data['rate_limits']['five_hour']['utilization']=100
        self.assertFalse(self.gate(self.sample(data))['allowed'])
        data=copy.deepcopy(self.data);data['rate_limits']['seven_day_opus']={'utilization':100,'resets_at':None}
        self.assertFalse(self.gate(self.sample(data))['allowed'])
        self.assertTrue(self.gate(self.sample(data),model_scope='sonnet')['allowed'])

    def test_event_fraction_and_epoch_are_separate_and_do_not_fake_a_usage_proof(self):
        event=event_sample({'status':'allowed_warning','utilization':0.75,'resetsAt':1793362800,'rateLimitType':'five_hour'})
        self.assertEqual(event['usedPercent'],75);self.assertEqual(event['status'],'allowed_warning')
        self.assertEqual(event_sample({'status':'rejected'})['resetsAt'],None)
        self.assertNotIn('extraUsageEnabled',event)
        with self.assertRaises(ValueError):event_sample({'status':'allowed','resetsAt':1793362800000})
        with self.assertRaises(ValueError):event_sample({'status':'unknown'})
