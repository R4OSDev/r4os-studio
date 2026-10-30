"""Shared real-identity keys, persistent holds and explicit compare-and-swap release."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from claude_auth import status_result
from claude_auth_store import AuthStore
from claude_limits_policy import usage_sample
from claude_quota_store import QuotaStore
from claude_runtime import profile
from store import ProjectFault


class NativeQuotaHolds(unittest.TestCase):
    def test_same_verified_account_shares_hold_metadata_cannot_clear_and_new_rejection_wins(self):
        with tempfile.TemporaryDirectory() as temporary:
            auth=AuthStore(Path(temporary));providers=[]
            for org in ('same-org','same-org','different-org'):
                with patch('claude_provider_store.installed',return_value={'id':profile()['id']}):
                    p=auth.create({'requestId':str(uuid.uuid4()),'name':'Same display name'})['provider']
                rid=str(uuid.uuid4());auth.begin(p['id'],{'requestId':rid,'revision':1,'action':'status'},'a'*64)
                status,account,_=status_result(json.dumps({'loggedIn':True,'authMethod':'claude.ai','apiProvider':'firstParty',
                    'configDirectory':'/config','subscriptionType':'pro','email':'own@example.test','orgId':org,'orgName':'Same name'}),0)
                providers.append(auth.finish(p['id'],rid,'complete',status=status,account=account)['provider'])
            first,second,foreign=providers;quota=QuotaStore(temporary)
            raw={'subscription_type':'pro','rate_limits_available':True,'rate_limits':{'limits':[],
                'five_hour':{'utilization':100,'resets_at':None},'seven_day':{'utilization':20,'resets_at':None},'extra_usage':{'is_enabled':False}}}
            sample=usage_sample(raw,first,str(uuid.uuid4()));denial={'reasonCode':'subscription_limit','reason':'Native quota exhausted'}
            original=quota.record(first['id'],sample=sample,denial=denial)['hold']
            self.assertEqual(quota.read(second['id'])['hold'],original)
            self.assertIsNone(quota.read(foreign['id']))
            # A fresh metadata value or a passed reset time never authorizes
            # a queue/Goal restart, and a warning is not a failed original run.
            raw['rate_limits']['five_hour']['utilization']=10
            later=usage_sample(raw,second,str(uuid.uuid4()));self.assertEqual(quota.record(second['id'],sample=later)['hold'],original)
            newest=quota.record(second['id'],denial=denial)['hold'];self.assertNotEqual(newest['id'],original['id'])
            with self.assertRaises(ProjectFault):quota.release(first['id'],original,str(uuid.uuid4()))
            self.assertIsNone(quota.release(first['id'],newest,str(uuid.uuid4()))['hold'])
