"""User input receipts, isolation and bounded storage; no provider process."""
from concurrent.futures import ThreadPoolExecutor
import json
import unittest
import uuid

from message_store import Messages
from store import ProjectFault
import test_runs as fixtures


class MessageReceipts(unittest.TestCase):
    setUp = fixtures.Runs.setUp
    tearDown = fixtures.Runs.tearDown
    open = fixtures.Runs.open

    def message_input(self, **changes):
        return {'requestId': str(uuid.uuid4()), 'revision': 1, 'mode': 'queue', 'text': 'Follow-up 🦀', **changes}

    def test_atomic_original_receipt_fifo_isolation_and_legacy(self):
        data = self.message_input()
        def send(_):
            with self.open() as store: return Messages(store).accept(self.sid, data)
        with ThreadPoolExecutor(2) as pool: replies = list(pool.map(send, range(2)))
        self.assertEqual(replies[0][0], replies[1][0]); self.assertEqual(sum(fresh for _, fresh in replies), 1)
        with self.open() as store:
            inbox = Messages(store)
            with self.assertRaises(ProjectFault): inbox.accept(self.sid, {**data, 'text': 'Changed'})
            second, _ = inbox.accept(self.sid, self.message_input())
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
                with self.assertRaises(ProjectFault): inbox.accept(self.sid, data)
            for _ in range(32): inbox.accept(self.sid, self.message_input())
            with self.assertRaises(ProjectFault) as full: inbox.accept(self.sid, self.message_input())
            self.assertEqual(full.exception.code, 429)
            rows = inbox.snapshot(self.sid)['messages']
            self.assertEqual(len(rows), 32)
            self.assertEqual(len({row['requestId'] for row in rows}), 32)
            self.assertTrue(all(row['state']=='queued' for row in rows))
            self.assertNotIn(str(self.root), json.dumps(rows))


if __name__ == '__main__': unittest.main()
