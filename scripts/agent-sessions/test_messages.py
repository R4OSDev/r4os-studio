"""User input receipts, isolation and bounded storage; no provider process."""
from concurrent.futures import ThreadPoolExecutor
import asyncio
import hashlib
import io
import json
import unittest
import uuid

from message_store import Messages
from store import ProjectFault
import test_runs as fixtures
from run_store import get_run, transition


class MessageReceipts(unittest.TestCase):
    setUp = fixtures.Runs.setUp
    tearDown = fixtures.Runs.tearDown
    open = fixtures.Runs.open

    def message_input(self, **changes):
        return {'requestId': str(uuid.uuid4()), 'revision': 1, 'mode': 'queue', 'text': 'Follow-up 🦀', **changes}

    def test_atomic_original_receipt_fifo_isolation_and_legacy(self):
        data = self.message_input()
        def send(_):
            with self.open() as store: return Messages(store).accept(self.sid, data, self.providers)
        with ThreadPoolExecutor(2) as pool: replies = list(pool.map(send, range(2)))
        self.assertEqual(replies[0][0], replies[1][0]); self.assertEqual(sum(fresh for _, fresh in replies), 1)
        with self.open() as store:
            inbox = Messages(store)
            with self.assertRaises(ProjectFault): inbox.accept(self.sid, {**data, 'text': 'Changed'}, self.providers)
            second, _ = inbox.accept(self.sid, self.message_input(), self.providers)
            self.assertGreater(second['sequence'], replies[0][0]['sequence'])
            self.assertEqual([m['sequence'] for m in inbox.snapshot(self.sid)['messages']], [replies[0][0]['sequence'], second['sequence']])
            with self.assertRaises(ProjectFault): inbox.receipt(str(uuid.uuid4()), data['requestId'])
            self.assertEqual(store.db.execute('PRAGMA user_version').fetchone()[0], 1)
            self.assertEqual(store.row(self.sid)['thread_id'], None)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        with self.open() as store: self.assertEqual(Messages(store).receipt(self.sid, data['requestId']), replies[0][0])

    def test_limits_target_and_payload_errors_preserve_existing_data(self):
        with self.open() as store:
            inbox = Messages(store)
            for data in [self.message_input(text='x'*65537), self.message_input(text='\x00'), self.message_input(revision=2),
                         self.message_input(target={'runId': str(uuid.uuid4())}), self.message_input(mode='steer'),
                         self.message_input(mode='steer', target={'runId': str(uuid.uuid4()), 'threadId': 'foreign', 'turnId': 'turn'})]:
                with self.assertRaises(ProjectFault): inbox.accept(self.sid, data, self.providers)
            for _ in range(32): inbox.accept(self.sid, self.message_input(), self.providers)
            with self.assertRaises(ProjectFault) as full: inbox.accept(self.sid, self.message_input(), self.providers)
            self.assertEqual(full.exception.code, 429)
            rows = inbox.snapshot(self.sid)['messages']
            self.assertEqual(len(rows), 32)
            self.assertEqual(len({row['requestId'] for row in rows}), 32)
            self.assertTrue(all(row['state']=='queued' for row in rows))
            self.assertNotIn(str(self.root), json.dumps(rows))

    def coordinator(self):
        from host import Host
        host = Host({'projects':str(self.projects), 'r4os':str(self.r4os), 'providers':str(self.providers), 'uid':0, 'maxActiveRuns':2})
        host.inboxes.add(('project', self.pid, self.sid))
        self.launched = []
        async def launch(store, run, kind, ident, sid):
            self.launched.append(run['id'])
            host.active[run['id']] = {'projectId':ident}
            transition(store, run['id'], 'running', turn_id='native-'+run['id'])
            return run
        host.launch_admitted = launch
        return host

    def test_three_frozen_messages_dispatch_once_in_order_and_recovery_holds(self):
        host = self.coordinator()
        with self.open() as store:
            inbox = Messages(store)
            requests = [self.message_input(text=text) for text in ['one','two','three']]
            for data in requests: inbox.accept(self.sid, data, self.providers)
        for index, data in enumerate(requests):
            asyncio.run(host.dispatch_queues()); asyncio.run(host.dispatch_queues())
            self.assertEqual(len(self.launched), index+1)
            rid = self.launched[-1]
            with self.open() as store:
                self.assertEqual(get_run(store, rid)['request_id'], data['requestId'])
                self.assertEqual(Messages(store).receipt(self.sid,data['requestId'])['state'], 'accepted')
                self.assertEqual(sum(r['busy'] for r in store.db.execute('SELECT busy FROM runs')), 1)
                transition(store,rid,'completed')
            host.active.pop(rid)
        self.assertEqual(len(self.launched),3)
        with self.open() as store:
            inbox=Messages(store);inbox.accept(self.sid,self.message_input(),self.providers);inbox.recover()
            self.assertTrue(inbox.snapshot(self.sid)['held'])
        asyncio.run(host.dispatch_queues());self.assertEqual(len(self.launched),3)

    def test_stop_failure_cancel_and_changed_selection_preserve_inputs(self):
        host=self.coordinator()
        with self.open() as store:
            inbox=Messages(store)
            first,_=inbox.accept(self.sid,self.message_input(),self.providers)
            second,_=inbox.accept(self.sid,self.message_input(),self.providers)
            inbox.hold(self.sid,'User Stop')
        asyncio.run(host.dispatch_queues());self.assertFalse(self.launched)
        with self.open() as store:
            inbox=Messages(store)
            action={'requestId':str(uuid.uuid4()),'revision':inbox.snapshot(self.sid)['revision'],'action':'resume'}
            self.assertEqual(inbox.control(self.sid,action),inbox.control(self.sid,action))
        asyncio.run(host.dispatch_queues())
        with self.open() as store:
            inbox=Messages(store)
            with self.assertRaises(ProjectFault):inbox.control(self.sid,{'requestId':str(uuid.uuid4()),'revision':inbox.snapshot(self.sid)['revision'],'action':'cancel','messageId':first['requestId']})
            transition(store,self.launched[-1],'failed','Fixture failure')
            self.assertTrue(inbox.snapshot(self.sid)['held'])
            inbox.control(self.sid,{'requestId':str(uuid.uuid4()),'revision':inbox.snapshot(self.sid)['revision'],'action':'resume'})
            with store.db:store.db.execute('UPDATE sessions SET revision=revision+1 WHERE id=?',(self.sid,))
        host.active.clear();asyncio.run(host.dispatch_queues())
        self.assertEqual(len(self.launched),1)
        with self.open() as store:
            inbox=Messages(store);self.assertTrue(inbox.snapshot(self.sid)['held'])
            self.assertEqual(inbox.receipt(self.sid,second['requestId'])['state'],'queued')
            inbox.control(self.sid,{'requestId':str(uuid.uuid4()),'revision':inbox.snapshot(self.sid)['revision'],'action':'cancel','messageId':second['requestId']})
            self.assertEqual(inbox.receipt(self.sid,second['requestId'])['state'],'cancelled')

    def test_queue_retains_ready_attachment_bytes_after_remove(self):
        from attachment_store import Attachments
        from image_inputs import file_path
        with self.open() as store:
            attachments=Attachments(store,self.sid);raw=b'Immutable queued document'
            result=attachments.upload({'requestId':str(uuid.uuid4()),'name':'note.txt','size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'mediaType':'text/plain'},io.BytesIO(raw))
            metadata=result['attachment'];inbox=Messages(store)
            data=self.message_input(attachments=[metadata['id']])
            message,_=inbox.accept(self.sid,data,self.providers,{'nativeImageInputs':1,'documentInputs':1})
            self.assertEqual(message['attachments'][0]['sha256'],hashlib.sha256(raw).hexdigest())
            self.assertTrue(attachments.used(metadata['id']))
            self.assertTrue(attachments.remove(metadata['id'])['retainedForHistory'])
            self.assertEqual(file_path(store,self.sid,message['attachments'][0]).read_bytes(),raw)
        host=self.coordinator();asyncio.run(host.dispatch_queues())
        self.assertEqual(len(self.launched),1)


if __name__ == '__main__': unittest.main()
