"""Native queued intents, account/history holds and original input receipts."""
import asyncio
from contextlib import ExitStack
import copy
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from attachment_store import birth
from claude_auth import status_result
from claude_auth_store import AuthStore
from claude_history import ClaudeHistory
from claude_messages import acknowledge, context, finalize, validate_queue
from claude_run_leases import ClaudeRunLeases
from claude_runtime import profile
from host import Host
from message_store import Messages
from run_store import admit, get_run, transition
from session_store import encode
from store import ProjectFault
import test_runs as fixtures


class ClaudeMessages(unittest.TestCase):
    open = fixtures.Runs.open

    def setUp(self):
        fixtures.Runs.setUp(self); self.addCleanup(fixtures.Runs.tearDown, self)
        self.providers.chmod(0o700); runtime = profile()
        with patch('claude_provider_store.installed', return_value={'id': runtime['id']}):
            self.provider_value = AuthStore(self.providers).create({'requestId': str(uuid.uuid4()), 'name': 'Own queued account'})['provider']
        auth = AuthStore(self.providers); request = str(uuid.uuid4()); provider = self.provider_value
        auth.begin(provider['id'], {'requestId': request, 'revision': provider['revision'], 'action': 'status'}, 'a'*64)
        status, account, _ = status_result(json.dumps({'loggedIn': True, 'authMethod': 'claude.ai', 'apiProvider': 'firstParty',
            'configDirectory': '/config', 'subscriptionType': 'pro', 'email': 'own@example.test', 'orgId': 'own-org', 'orgName': 'Own fixture'}), 0)
        self.provider_value = auth.finish(provider['id'], request, 'complete', status=status, account=account)['provider']
        self.patches = ExitStack(); self.addCleanup(self.patches.close)
        self.patches.enter_context(patch('session_store.providers', return_value=[self.provider_value]))
        self.patches.enter_context(patch('session_store.provider_models', return_value=[{'id': 'sonnet', 'efforts': ['low']}]))
        self.patches.enter_context(patch('claude_selection.installed', return_value={'version': runtime['native']['version'], 'sha256': runtime['native']['files']['claude']['sha256']}))
        with self.open() as store:
            session = store.create({'requestId': str(uuid.uuid4()), 'name': 'Own native queue',
                'providerId': provider['id'], 'model': 'sonnet', 'effort': 'low'}, self.providers)
            self.sid = session['id']; self.native = session['engine']['claude']['nativeSessionId']

    def message_input(self):
        return {'requestId': str(uuid.uuid4()), 'revision': 1, 'mode': 'queue', 'text': 'Own literal /follow-up @file'}

    def opening(self, store, run):
        config = json.loads(get_run(store, run['id'])['config'])
        worker = {'release': 'own-queue-fixture', 'pid': os.getpid(), 'birth': birth(os.getpid())}
        lease = {**config['claudeProvider'], 'studioSessionId': self.sid, 'ownerType': 'project', 'ownerId': self.pid,
            'runId': run['id'], 'requestId': get_run(store, run['id'])['request_id'], 'nativeSessionId': self.native}
        ClaudeRunLeases(self.providers).claim(lease, worker)
        transition(store, run['id'], 'running', worker=worker)
        ClaudeHistory(store, self.sid).prepare(run['id'])
        return config, worker, lease

    def test_live_capture_fifo_no_inference_and_unknown_lease_rejection(self):
        with self.open() as store:
            original, _ = admit(store, self.sid, {'requestId': str(uuid.uuid4()), 'revision': 1, 'text': 'Original'}, self.providers)
            config, worker, lease = self.opening(store, original)
            messages = Messages(store); data = self.message_input()
            first, fresh = messages.accept(self.sid, data, self.providers); self.assertTrue(fresh)
            self.assertEqual(messages.accept(self.sid, data, self.providers), (first, False))
            second, _ = messages.accept(self.sid, self.message_input(), self.providers)
            self.assertEqual([m['requestId'] for m in messages.snapshot(self.sid)['messages']], [first['requestId'], second['requestId']])
            frozen = json.loads(messages.row(self.sid, data['requestId'])['frozen'])
            self.assertEqual(frozen['claudeQueue']['source']['runId'], original['id'])
            self.assertEqual(frozen['claudeQueue']['nativeSessionId'], self.native)
            self.assertEqual(store.db.execute('SELECT count(*) FROM runs').fetchone()[0], 1)
            self.assertEqual(ClaudeHistory(store, self.sid).get()['phase'], 'opening')
            with self.assertRaises(ProjectFault): validate_queue(store, self.sid, frozen)
            direct = self.message_input() | {'mode': 'steer', 'target': {'runId': original['id'], 'threadId': self.native, 'turnId': 'unavailable'}}
            with self.assertRaisesRegex(ProjectFault, 'Direct Claude messages'): messages.accept(self.sid, direct, self.providers)
            ClaudeRunLeases(self.providers).finish_lease(lease, worker, False)
            with self.assertRaises(ProjectFault): messages.accept(self.sid, self.message_input(), self.providers)
            self.assertEqual(store.db.execute('SELECT count(*) FROM session_messages').fetchone()[0], 2)
            self.assertEqual(json.loads(get_run(store, original['id'])['config']), config)

    def dispatched(self):
        data = self.message_input()
        with self.open() as store: Messages(store).accept(self.sid, data, self.providers)
        host = Host({'projects': str(self.projects), 'r4os': str(self.r4os), 'providers': str(self.providers), 'uid': os.getuid(), 'maxActiveRuns': 2})
        host.inboxes.add(('project', self.pid, self.sid)); launches = []
        async def launch(store, run, kind, owner, sid): launches.append(run)
        host.launch_admitted = launch
        asyncio.run(host.dispatch_queues()); self.assertEqual(len(launches), 1)
        asyncio.run(host.dispatch_queues()); self.assertEqual(len(launches), 1)
        return data, launches[0]

    def receiver(self, store, run):
        config, worker, _ = self.opening(store, run)
        return SimpleNamespace(store=store, session_id=self.sid, run_id=run['id'], row=get_run(store, run['id']),
            config=config, credential_worker=worker, sent=False, stopping=False, input_receipt=asyncio.Event(),
            uncertain_effect=False, outcome='completed', error=None)

    def frame(self, worker):
        return {'native': {'type': 'assistant', 'session_id': self.native}, 'identity': {'nativeType': 'assistant',
            'nativeInputRequestIds': [worker.row['request_id']], 'nativeSessionId': self.native,
            'nativeMessageId': str(uuid.uuid4()), 'providerMessageId': 'msg_owned_input'}}

    def test_actual_input_echo_accepts_once_and_stop_does_not_erase_receipt(self):
        data, run = self.dispatched()
        with self.open() as store:
            messages = Messages(store); worker = self.receiver(store, run)
            self.assertEqual(messages.receipt(self.sid, data['requestId'])['state'], 'dispatching')
            self.assertFalse(acknowledge(worker, {'identity': {}, 'native': {}}))
            metadata = self.frame(worker); metadata['identity']['nativeType'] = 'system'; metadata['native']['type'] = 'system'
            self.assertFalse(acknowledge(worker, metadata))
            self.assertEqual(messages.receipt(self.sid, data['requestId'])['state'], 'dispatching')
            foreign = self.frame(worker); foreign['identity']['nativeInputRequestIds'] = [str(uuid.uuid4())]
            with self.assertRaises(ProjectFault): acknowledge(worker, foreign)
            transition(store, run['id'], 'stopping'); worker.stopping = True
            self.assertTrue(acknowledge(worker, self.frame(worker))); self.assertTrue(worker.input_receipt.is_set())
            self.assertTrue(acknowledge(worker, self.frame(worker)))
            self.assertEqual(messages.receipt(self.sid, data['requestId'])['state'], 'accepted')
            self.assertEqual(store.db.execute('SELECT count(*) FROM claude_input_receipts').fetchone()[0], 1)
            self.assertEqual(get_run(store, run['id'])['state'], 'stopping')
            saved = json.loads(store.db.execute('SELECT payload FROM claude_input_receipts').fetchone()[0])
            self.assertIsNone(saved['nativeTurnId']); self.assertNotIn(data['text'], json.dumps(saved))

    def test_metadata_tags_do_not_admit_tools_and_denied_call_is_not_executed_after_ack(self):
        from claude_worker import ClaudeWorker
        from unittest.mock import AsyncMock
        data, run = self.dispatched()
        with self.open() as store: self.opening(store, run)
        worker = ClaudeWorker({'projects':str(self.projects),'r4os':str(self.r4os),'providers':str(self.providers),
            'projectId':self.pid,'runId':run['id'],'sessionId':self.sid,'release':'own-queue-fixture'})
        worker.execute = AsyncMock(return_value={'success':True,'output':'Own confirmed effect'})
        async def exercise():
            try:
                args={'path':'owned.txt','content':'Owned','expectedSha256':None}
                first=await worker.effect('studio_write_file',args,'own-waiting-call')
                self.assertTrue(first['isError']);worker.execute.assert_not_awaited()
                worker.input_receipt.set()
                repeated=await worker.effect('studio_write_file',args,'own-waiting-call')
                self.assertEqual(first,repeated);worker.execute.assert_not_awaited()
                self.assertFalse((await worker.effect('studio_write_file',args,'own-new-call'))['isError'])
                worker.execute.assert_awaited_once()
            finally:
                await worker.cleanup();worker.store.close()
        asyncio.run(exercise())

    def test_missing_input_echo_holds_original_without_replaying_or_repairing_history(self):
        data, run = self.dispatched()
        with self.open() as store:
            worker = self.receiver(store, run); worker.sent = True
            finalize(worker)
            self.assertTrue(worker.uncertain_effect); self.assertEqual(worker.outcome, 'unknown')
            transition(store, run['id'], worker.outcome, worker.error)
            queue = Messages(store).snapshot(self.sid)
            self.assertTrue(queue['held']); self.assertEqual(queue['messages'][0]['state'], 'unknown')
            self.assertIsNone(Messages(store).first(self.sid))
            self.assertEqual(ClaudeHistory(store, self.sid).get()['runtime']['nativeSessionId'], self.native)

    def test_cancel_restore_revision_and_account_changes_preserve_queued_text(self):
        with self.open() as store:
            messages = Messages(store); data = self.message_input(); messages.accept(self.sid, data, self.providers)
            frozen = json.loads(messages.row(self.sid, data['requestId'])['frozen'])
            validate_queue(store, self.sid, frozen)
            changed = copy.deepcopy(frozen); changed['claudeQueue']['nativeSessionId'] = str(uuid.uuid4())
            with self.assertRaises(ProjectFault): validate_queue(store, self.sid, changed)
            messages.recover(); queue = messages.snapshot(self.sid)
            self.assertTrue(queue['held']); self.assertIsNone(messages.first(self.sid))
            messages.control(self.sid, {'requestId': str(uuid.uuid4()), 'revision': queue['revision'], 'action': 'cancel', 'messageId': data['requestId']}, self.providers)
            self.assertEqual(messages.receipt(self.sid, data['requestId'])['state'], 'cancelled')
            self.assertEqual(messages.receipt(self.sid, data['requestId'])['text'], data['text'])
            self.assertEqual(store.db.execute('SELECT count(*) FROM runs').fetchone()[0], 0)
            # No unused credential lease is acquired for a mere queued intent.
            with ClaudeRunLeases(self.providers).leases() as db:
                self.assertTrue(db is None or db.execute('SELECT count(*) FROM claude_run_leases').fetchone()[0] == 0)

    def test_provider_revision_change_holds_saved_input_without_launch(self):
        data=self.message_input()
        with self.open() as store:Messages(store).accept(self.sid,data,self.providers)
        auth=AuthStore(self.providers);provider=self.provider_value;rid=str(uuid.uuid4())
        auth.begin(provider['id'],{'requestId':rid,'revision':provider['revision'],'action':'status'},'a'*64)
        auth.finish(provider['id'],rid,'complete',status='connected',account=provider['account'])
        host=Host({'projects':str(self.projects),'r4os':str(self.r4os),'providers':str(self.providers),'uid':os.getuid(),'maxActiveRuns':2})
        host.inboxes.add(('project',self.pid,self.sid));launched=[]
        async def launch(*args):launched.append(args)
        host.launch_admitted=launch
        asyncio.run(host.dispatch_queues());self.assertEqual(launched,[])
        with self.open() as store:
            value=Messages(store).snapshot(self.sid)
            self.assertTrue(value['held']);self.assertEqual(value['messages'][0]['text'],data['text'])
            self.assertEqual(store.db.execute('SELECT count(*) FROM runs').fetchone()[0],0)
