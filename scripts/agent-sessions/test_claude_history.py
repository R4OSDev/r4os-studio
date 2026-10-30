"""Own native-history byte/binding fixtures; no reconstructed user transcript."""
import json
import unittest
import uuid
from unittest.mock import patch

from claude_history import ClaudeHistory
from profile import PROFILE
from run_store import admit,transition
from session_store import encode,permission_tools
from store import ProjectFault
import test_runs as fixtures


class NativeHistory(unittest.TestCase):
    def test_original_id_survives_reload_and_changed_or_unconfirmed_history_never_resumes(self):
        # Exercise byte preservation independently of real provider admission.
        admission=patch('claude_selection.freeze');admission.start();self.addCleanup(admission.stop)
        fixture=fixtures.Runs('test_concurrent_retry_snapshot_stop_and_replay');fixture.setUp();self.addCleanup(fixture.tearDown)
        with fixture.open() as store:
            # This is a controlled storage/receipt fixture, not an authenticated
            # provider or a publicly admitted Claude/model execution.
            engine={'kind':'claude-code','profile':PROFILE,'version':'2.1.312'}
            settings={**fixture.settings,'permissions':{'studio.'+tool:True for tool in permission_tools(PROFILE)}}
            store.db.execute('UPDATE sessions SET engine=?,settings=? WHERE id=?',(encode(engine),encode(settings),fixture.sid));store.db.commit()
            from claude_runtime import profile
            provider={'id':fixture.provider,'type':'claude-subscription','profileRevision':1,'runtimeProfileId':profile()['id']}
            store.db.execute('BEGIN IMMEDIATE')
            ClaudeHistory(store,fixture.sid).create(provider)
            self.assertTrue(store.db.in_transaction)
            store.db.rollback()
            self.assertNotIn('claude',store.get(fixture.sid)['engine'])
            history=ClaudeHistory(store,fixture.sid);created=history.create(provider)
            original_id=created['runtime']['nativeSessionId']
            self.assertEqual(history.create(provider)['runtime']['nativeSessionId'],original_id)
            run,_=admit(store,fixture.sid,fixture.data,fixture.providers)
            opening=history.prepare(run['id']);self.assertEqual(opening['mode'],'new')
            with self.assertRaises(ProjectFault):history.prepare(run['id'])
            closed={'nativeSessionId':original_id,'studioRequestId':fixture.data['requestId'],
                'promptSubmitted':False,'resultId':None,'originalStreamConfirmed':True}
            self.assertFalse(history.unstarted(run['id'],opening,{**closed,'promptSubmitted':True}))
            self.assertFalse(history.unstarted(run['id'],opening,{**closed,'studioRequestId':str(uuid.uuid4())}))
            self.assertTrue(history.unstarted(run['id'],opening,closed))
            self.assertEqual(history.get()['phase'],'allocated')
            self.assertEqual(history.prepare(run['id'])['mode'],'new')
            root=history.paths()['history'];folder=root/'-inference';folder.mkdir(mode=0o700)
            path=folder/(original_id+'.jsonl')
            native_record={'type':'user','sessionId':original_id,'uuid':str(uuid.uuid4()),'message':{'role':'user','content':'Own storage fixture'}}
            original=(json.dumps(native_record)+'\n').encode();path.write_bytes(original);path.chmod(0o600)
            receipt={'nativeSessionId':original_id,'nativeResultId':str(uuid.uuid4()),'studioRequestId':fixture.data['requestId'],
                'subtype':'success','nativeClosed':True,'historyReadable':True}
            self.assertEqual(history.finish(run['id'],receipt)['phase'],'ready');transition(store,run['id'],'completed')
        with fixture.open() as store:
            history=ClaudeHistory(store,fixture.sid);self.assertEqual(history.get()['runtime']['nativeSessionId'],original_id)
            later={**fixture.data,'requestId':str(uuid.uuid4())};run,_=admit(store,fixture.sid,later,fixture.providers)
            path.write_bytes(original+b'{incomplete native record')
            with self.assertRaises(ProjectFault):history.prepare(run['id'])
            self.assertEqual(path.read_bytes(),original+b'{incomplete native record')
            path.write_bytes(original);path.chmod(0o600)
            prepared=history.prepare(run['id']);self.assertEqual(prepared['mode'],'resume');self.assertTrue(prepared['historyConfirmed'])
            self.assertEqual(prepared['runtime']['nativeSessionId'],original_id)
            history.unconfirmed(run['id'])
            with self.assertRaises(ProjectFault):history.prepare(run['id'])
            self.assertEqual(path.read_bytes(),original)
