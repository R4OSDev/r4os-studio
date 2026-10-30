"""Owned credential lease/auth race cases, without native login or model use."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from claude_auth_store import AuthStore
from claude_auth import status_result
from claude_provider_store import account_identity
from claude_runtime import profile
from claude_run_leases import ClaudeRunLeases
from store import ProjectFault


class NativeLeases(unittest.TestCase):
    def test_authentication_waits_for_the_original_worker_and_unknown_end_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            auth=AuthStore(Path(temporary));owner='a'*64
            with patch('claude_provider_store.installed',return_value={'id':profile()['id']}):
                provider=auth.create({'requestId':str(uuid.uuid4()),'name':'Own synthetic account'})['provider']
            request=str(uuid.uuid4());auth.begin(provider['id'],{'requestId':request,'revision':1,'action':'status'},owner)
            status,account,_=status_result(json.dumps({'loggedIn':True,'authMethod':'claude.ai','apiProvider':'firstParty','configDirectory':'/config',
                'subscriptionType':'pro','email':'own@example.test','orgId':'own-org','orgName':'Own metadata fixture'}),0)
            provider=auth.finish(provider['id'],request,'complete',status=status,account=account)['provider']
            value={key:str(uuid.uuid4()) for key in ('studioSessionId','ownerId','runId','requestId','nativeSessionId')}
            value.update(providerId=provider['id'],providerRevision=provider['revision'],runtimeProfileId=provider['runtimeProfileId'],
                ownerType='project',accountIdentity=account_identity(provider['account']))
            leases=ClaudeRunLeases(temporary);self.assertEqual(leases.reserve(value)['state'],'reserved')
            self.assertEqual(leases.reserve(value)['state'],'reserved')
            with self.assertRaises(ProjectFault):leases.reserve({**value,'nativeSessionId':str(uuid.uuid4())})
            def auth_input():return {'requestId':str(uuid.uuid4()),'revision':provider['revision'],'action':'disconnect'}
            with self.assertRaises(ProjectFault):auth.begin(provider['id'],auth_input(),owner)
            worker={'release':'own-native-worker','pid':12345,'birth':'original-owned-process'}
            leases.claim(value,worker);self.assertTrue(leases.current_lease(value,worker))
            self.assertFalse(leases.current_lease(value,{**worker,'birth':'foreign'}))
            with self.assertRaises(ProjectFault):leases.claim(value,{**worker,'pid':99999})
            leases.finish_lease(value,worker,False)
            with self.assertRaises(ProjectFault):auth.begin(provider['id'],auth_input(),owner)
            leases.finish_lease(value,worker,True)
            self.assertFalse(leases.current_lease(value,worker))
            result,fresh=auth.begin(provider['id'],auth_input(),owner);self.assertTrue(fresh);self.assertEqual(result['state'],'pending')
            self.assertNotIn('token',(auth.root/'Providers.sqlite').read_bytes().decode('latin1').lower())
