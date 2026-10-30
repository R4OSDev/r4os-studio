"""Atomic native session creation and original run reservations, without a model."""
import json
import unittest
from unittest.mock import patch
import uuid

from claude_auth import status_result
from claude_auth_store import AuthStore
from claude_history import ClaudeHistory
from claude_runtime import profile
from run_store import admit,get_run
from store import ProjectFault
import test_runs as fixtures


class NativeSelection(unittest.TestCase):
    def test_original_create_retry_atomic_rollback_and_credential_reservation(self):
        f=fixtures.Runs('test_concurrent_retry_snapshot_stop_and_replay');f.setUp();self.addCleanup(f.tearDown)
        f.providers.chmod(0o700);runtime=profile()
        with patch('claude_provider_store.installed',return_value={'id':runtime['id']}):
            provider=AuthStore(f.providers).create({'requestId':str(uuid.uuid4()),'name':'Own selection fixture'})['provider']
        auth=AuthStore(f.providers);rid=str(uuid.uuid4())
        auth.begin(provider['id'],{'requestId':rid,'revision':1,'action':'catalog'},'a'*64)
        status,account,_=status_result(json.dumps({'loggedIn':True,'authMethod':'claude.ai','apiProvider':'firstParty',
            'configDirectory':'/config','subscriptionType':'pro','email':'own@example.test','orgId':'own-org','orgName':'Own fixture'}),0)
        provider=auth.finish(provider['id'],rid,'complete',status=status,account=account,
            models=[{'value':'sonnet','resolvedModel':'sonnet','displayName':'Own fixture','description':'Owned native model facts',
                'supportsEffort':True,'supportedEffortLevels':['low']}])['provider']
        # Native model facts enable selection, never replace fresh per-send
        # subscription admission. This fixture starts no native model process.
        with f.open() as store, patch('session_store.providers',return_value=[provider]), \
            patch('session_store.provider_models',return_value=[{'id':'sonnet','efforts':['low']}]), \
            patch('claude_selection.installed',return_value={'version':runtime['native']['version'],'sha256':runtime['native']['files']['claude']['sha256']}):
            data={'requestId':str(uuid.uuid4()),'name':'Own native','providerId':provider['id'],'model':'sonnet','effort':'low'}
            session=store.create(data,f.providers);sid=session['id'];original=ClaudeHistory(store,sid).get()['runtime']['nativeSessionId']
            self.assertEqual(store.create(data,f.providers)['id'],sid)
            self.assertEqual(ClaudeHistory(store,sid).get()['runtime']['nativeSessionId'],original)
            count=store.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
            create=ClaudeHistory.create
            def interrupted(history,selected):
                create(history,selected)
                raise RuntimeError('Own interruption after native identity, before original receipt')
            with patch.object(ClaudeHistory,'create',interrupted),self.assertRaises(RuntimeError):
                store.create({**data,'requestId':str(uuid.uuid4())},f.providers)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],count)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM claude_sessions').fetchone()[0],1)
            request={'requestId':str(uuid.uuid4()),'revision':session['revision'],'text':'Own input'}
            run,fresh=admit(store,sid,request,f.providers);self.assertTrue(fresh)
            same,again=admit(store,sid,request,f.providers);self.assertFalse(again);self.assertEqual(run['id'],same['id'])
            frozen=json.loads(get_run(store,run['id'])['config'])
            self.assertEqual(frozen['claudeRunId'],run['id'])
            self.assertEqual(frozen['engine']['claude']['nativeSessionId'],original)
            with self.assertRaises(ProjectFault):
                auth.begin(provider['id'],{'requestId':str(uuid.uuid4()),'revision':provider['revision'],'action':'disconnect'},'a'*64)
