"""Real sidecar finalization, original user authority and lost commit response."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch
import uuid

import test_cleanup_tools as fixtures
from run_store import admit, transition
from session_store import encode


class FinalizeToolsTest(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.CleanupToolsTest.setUp
    tearDown = fixtures.CleanupToolsTest.tearDown
    open = fixtures.CleanupToolsTest.open
    start = fixtures.CleanupToolsTest.start
    finish = fixtures.CleanupToolsTest.finish
    call = fixtures.CleanupToolsTest.call
    good = fixtures.CleanupToolsTest.good
    initialize = fixtures.CleanupToolsTest.initialize
    prepare = fixtures.CleanupToolsTest.prepare

    async def ready(self, worker, initial):
        arguments = self.prepare(initial); prepared = await self.good(worker, 'cleanup_roadmap', arguments)
        summary = 'Reviewed this empty version. No durable knowledge needs a separate document beyond its complete archive.'
        verified = await self.good(worker, 'cleanup_roadmap', {**arguments, 'requestId': str(uuid.uuid4()),
            'workflowId': prepared['workflowId'], 'documents': [], 'documentationSummary': summary})
        return verified, {'action': 'finalize', 'requestId': str(uuid.uuid4()), 'workflowId': prepared['workflowId'],
                          'cleanupRequested': True, 'documents': [], 'documentationSummary': summary}

    async def test_pending_user_authorization_survives_many_runs_and_cannot_roll_over_again(self):
        self.data['text'] = 'Please clean up the roadmap.'
        first = self.start(); initial = await self.initialize(first); self.finish(first)
        # More than twenty later real admissions must not erase the original
        # pending authorization. These are storage admissions, without models.
        with self.open() as store:
            for index in range(25):
                run, _ = admit(store, self.sid, {'requestId': str(uuid.uuid4()), 'revision': store.get(self.sid)['revision'], 'text': 'Own follow-up ' + str(index)}, self.providers)
                transition(store, run['id'], 'completed')
        self.data['text'] = 'Continue the original request.'
        worker = self.start(); verified, final = await self.ready(worker, initial)
        result = await self.good(worker, 'cleanup_roadmap', final)
        self.assertEqual(result['phase'], 'complete'); self.assertEqual(result['nextNumber'], '0.2.X')
        current = await self.good(worker, 'read_roadmap', {'view': 'current'})
        self.assertEqual(current['entity']['number'], '0.2.X'); self.assertEqual(current['entity']['title'], 'New')
        # The completed old request is consumed. It does not authorize an empty
        # second cleanup just because the agent continues the same user turn.
        denied = await self.call(worker, 'cleanup_roadmap', self.prepare(current))
        self.assertEqual(denied['error'], 'denied')
        self.assertEqual(len((await self.good(worker, 'read_roadmap', {'view': 'versions'}))['items']), 2)

    async def test_original_user_message_is_rechecked_before_commit(self):
        self.data['text'] = 'Roadmap aufräumen.'
        worker = self.start(); initial = await self.initialize(worker); verified, final = await self.ready(worker, initial)
        row = worker.store.db.execute("SELECT item_id,payload FROM items WHERE run_id=? AND item_id LIKE 'user-%'", (worker.run_id,)).fetchone()
        changed = json.loads(row['payload']); changed['text'] = 'Only implement ordinary work.'
        with worker.store.db: worker.store.db.execute('UPDATE items SET payload=? WHERE item_id=?', (encode(changed), row['item_id']))
        denied = await self.call(worker, 'cleanup_roadmap', final)
        self.assertEqual(denied['error'], 'conflict')
        self.assertEqual(len((await self.good(worker, 'read_roadmap', {'view': 'versions'}))['items']), 1)
        with worker.store.db: worker.store.db.execute('UPDATE items SET payload=? WHERE item_id=?', (row['payload'], row['item_id']))
        self.assertEqual((await self.good(worker, 'cleanup_roadmap', final))['phase'], 'complete')

    async def test_lost_finalize_response_reconciles_same_next_version_in_another_session(self):
        self.data['text'] = 'Please tidy up the roadmap.'
        worker = self.start(); initial = await self.initialize(worker); verified, final = await self.ready(worker, initial)
        original_spawn = asyncio.create_subprocess_exec
        async def lose(*args, **kwargs):
            process = await original_spawn(*args, **kwargs); communicate = process.communicate
            async def lost(*args, **kwargs):
                raw, _ = await communicate(*args, **kwargs); self.assertIn(b'nextVersionId', raw)
                raise ConnectionError('Own lost finalization reply after commit')
            process.communicate = lost
            return process
        worker.development.stop_owned = AsyncMock()
        with patch('roadmap_tools.asyncio.create_subprocess_exec', side_effect=lose):
            result = await self.call(worker, 'cleanup_roadmap', final)
        self.assertEqual(result['error'], 'unknown'); await asyncio.sleep(0)
        transition(worker.store, worker.run_id, 'unknown'); worker.lease.close()
        row = worker.store.row(self.sid); other_id = str(uuid.uuid4())
        with worker.store.db:
            worker.store.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,NULL,1,'now','now')", (other_id, self.pid, 'Other session', row['settings'], row['engine']))
        self.data['text'] = 'Inspect the original workflow in this project.'
        later = self.start(other_id)
        status = await self.good(later, 'cleanup_roadmap', {'action': 'status', 'workflowId': verified['workflowId']})
        self.assertEqual(status['phase'], 'complete')
        recovered = await self.good(later, 'cleanup_roadmap', final)
        self.assertEqual(recovered['nextVersionId'], status['nextVersionId'])
        again = await self.good(later, 'cleanup_roadmap', {**final, 'requestId': str(uuid.uuid4())})
        self.assertEqual(again['nextVersionId'], status['nextVersionId'])
        self.assertEqual(len((await self.good(later, 'read_roadmap', {'view': 'versions'}))['items']), 2)
