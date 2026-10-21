import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from session_store import SessionStore, TOOL_IDS, encode
from run_store import admit, get_run, transition, events, item
from store import connect, ProjectFault
from worker import Worker


class Runs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.projects = self.root / 'Projects'; self.r4os = self.root / 'R4OS'
        self.pid, self.sid, self.provider = (str(uuid.uuid4()) for _ in range(3))
        with closing(connect(self.projects)) as db, db:
            db.execute("INSERT INTO projects VALUES (?,?,'','C','terminal',?,NULL,'{}','now','now',1,'ready')", (self.pid, 'Fixture', 'fixture'))
        (self.projects / self.pid / 'Workspace').mkdir(parents=True)
        (self.projects / self.pid / 'Workspace/module.R4MF').write_text('R4OS_MODULE_MANIFEST=2\n')
        self.providers = self.root / 'Providers'; (self.providers / self.provider).mkdir(parents=True)
        (self.providers / 'providers.json').write_text(encode([{'id': self.provider, 'name': 'Fixture', 'type': 'openai', 'connected': True}]))
        (self.providers / self.provider / 'models_cache.json').write_text(encode({'models': [{'slug': 'fixture', 'visibility': 'list', 'supported_reasoning_levels': [{'effort': 'low'}]}]}))
        self.settings = {'providerId': self.provider, 'model': 'fixture', 'effort': 'low', 'permissions': {t: True for t in TOOL_IDS}}
        with self.open() as s:
            s.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,NULL,1,'now','now')", (self.sid, self.pid, 'Fixture', encode(self.settings), '{}')); s.db.commit()
        self.data = {'requestId': str(uuid.uuid4()), 'revision': 1, 'text': 'Concurrent input'}

    def open(self):
        from contextlib import closing
        return closing(SessionStore(self.projects, self.r4os, self.pid))

    def tearDown(self): self.tmp.cleanup()

    def test_concurrent_retry_snapshot_stop_and_replay(self):
        def send():
            with self.open() as s: return admit(s, self.sid, self.data, self.providers)
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(lambda _: send(), range(2)))
        self.assertEqual(results[0][0]['id'], results[1][0]['id']); self.assertEqual(sum(f for _, f in results), 1)
        rid = results[0][0]['id']
        with self.open() as s:
            with self.assertRaises(ProjectFault): admit(s, self.sid, {**self.data, 'text': 'Changed'}, self.providers)
            with self.assertRaises(ProjectFault): admit(s, self.sid, {**self.data, 'requestId': str(uuid.uuid4())}, self.providers)
            with self.assertRaises(ProjectFault): s.update(self.sid, {'revision': 1, 'name': 'Busy'}, self.providers)
            self.assertEqual(json.loads(get_run(s, rid)['config'])['permissions'], self.settings['permissions'])
            transition(s, rid, 'stopping'); transition(s, rid, 'running', turn_id='late')
            self.assertEqual(get_run(s, rid)['state'], 'stopping')
            transition(s, rid, 'interrupted'); transition(s, rid, 'running')
            self.assertEqual(get_run(s, rid)['busy'], 0)
            history = s.history(self.sid)
            self.assertEqual(len(history['items']), 1)
            self.assertEqual(events(s, self.sid, history['cursor'])['events'], [])
            self.assertEqual(len(events(s, self.sid)['events']), 4)
            # A new process sees the same run; retries never add a user message.
        with self.open() as s:
            result, fresh = admit(s, self.sid, self.data, self.providers)
            self.assertFalse(fresh); self.assertEqual(result['state'], 'interrupted')
            self.assertEqual(len(s.history(self.sid)['items']), 1)

    def test_large_history_is_byte_paginated_without_gaps(self):
        with self.open() as s:
            run, _ = admit(s, self.sid, self.data, self.providers)
            for i in range(5):
                item(s, self.sid, run['id'], {'id': 'large-' + str(i), 'runId': run['id'], 'type': 'assistant', 'text': 'x'*180000, 'status': 'completed'})
            page = s.history(self.sid); pages = [page]; self.assertLess(len(page['items']), 5)
            while page['before']:
                page = s.history(self.sid, page['before']); pages.append(page)
            values = [i['id'] for page in reversed(pages) for i in page['items']]
            self.assertEqual(values, ['user-' + self.data['requestId']] + ['large-' + str(i) for i in range(5)])
            self.assertTrue(all(len(encode(page).encode()) < 530000 for page in pages))

    def test_stop_commit_closes_tool_admission_before_signal_delivery(self):
        with self.open() as store:
            run, _ = admit(store, self.sid, self.data, self.providers)
        worker = Worker({'projects': str(self.projects), 'r4os': str(self.r4os), 'projectId': self.pid, 'runId': run['id']})
        worker.thread_id = 'thread'; worker.turn_id = 'turn'; calls = []
        async def execute(*args): calls.append(args); return {'success': True, 'output': 'unexpected'}
        worker.execute = execute
        with self.open() as store: transition(store, run['id'], 'stopping')
        self.assertFalse(worker.stopping)  # SIGTERM has not arrived in this process.
        params = {'namespace': None, 'threadId': 'thread', 'turnId': 'turn', 'tool': 'studio_write_file', 'callId': 'after-stop',
                  'arguments': {'path': 'not-created.txt', 'content': 'must not execute', 'expectedSha256': None}}
        try:
            result = asyncio.run(worker.tool(params))
            self.assertFalse(result['success']); self.assertIn('interrupted', result['contentItems'][0]['text'])
            self.assertEqual(calls, [])
            receipt = worker.store.db.execute("SELECT result FROM tools WHERE call_id='after-stop'").fetchone()[0]
            self.assertEqual(json.loads(receipt)['error'], 'interrupted')
        finally: worker.store.close()

    def test_mutating_io_failure_preserves_effect_and_closes_following_calls(self):
        with self.open() as store:
            run, _ = admit(store, self.sid, self.data, self.providers)
        worker = Worker({'projects': str(self.projects), 'r4os': str(self.r4os), 'projectId': self.pid, 'runId': run['id']})
        worker.thread_id = 'thread'; worker.turn_id = 'turn'; calls = []
        file = worker.store.workspace/'effect.txt'
        async def execute(*args):
            calls.append(args); file.write_text('one effect'); raise OSError('fsync failed after publication')
        worker.execute = execute
        params = {'namespace': None, 'threadId': 'thread', 'turnId': 'turn', 'tool': 'studio_write_file', 'callId': 'uncertain',
                  'arguments': {'path': 'effect.txt', 'content': 'one effect', 'expectedSha256': None}}
        async def scenario():
            result = await worker.tool(params); self.assertFalse(result['success'])
            self.assertEqual(json.loads(result['contentItems'][0]['text'])['error'], 'unknown')
            later = await worker.tool({**params, 'callId': 'automatic-retry'})
            self.assertEqual(json.loads(later['contentItems'][0]['text'])['error'], 'interrupted')
            self.assertEqual(len(calls), 1); self.assertEqual(file.read_text(), 'one effect')
            await asyncio.sleep(0)
            self.assertEqual(worker.outcome, 'unknown'); self.assertTrue(worker.done.is_set())
            self.assertEqual(worker.store.db.execute("SELECT state FROM tools WHERE call_id='uncertain'").fetchone()[0], 'unknown')
        try: asyncio.run(scenario())
        finally: worker.store.close()

    def test_tool_projection_preserves_partial_results_and_bounds_escaped_output(self):
        with self.open() as store:
            run, _ = admit(store, self.sid, self.data, self.providers)
        worker = Worker({'projects': str(self.projects), 'r4os': str(self.r4os), 'projectId': self.pid, 'runId': run['id']})
        worker.thread_id = 'thread'; worker.turn_id = 'turn'
        async def execute(*args):
            return {'success': False, 'error': 'patchFailed', 'output': '\x01'*50000, 'partialChangesPossible': True,
                    'files': {'changed.c': 'a'*64}, 'nextLine': 12, 'truncated': True}
        worker.execute = execute
        params = {'namespace': None, 'threadId': 'thread', 'turnId': 'turn', 'tool': 'studio_apply_patch', 'callId': 'partial',
                  'arguments': {'patch': '*** Begin Patch\n*** End Patch', 'expectedHashes': {}}}
        try:
            result = asyncio.run(worker.tool(params)); self.assertFalse(result['success'])
            value = next(i for i in worker.store.history(self.sid)['items'] if i['id']=='partial')
            self.assertTrue(value['partialChangesPossible']); self.assertTrue(value['truncated'])
            self.assertEqual(value['files'], {'changed.c': 'a'*64}); self.assertEqual(value['nextLine'], 12)
            self.assertLess(len(encode(value).encode()), 262144)
        finally: worker.store.close()

    def test_tool_denial_and_unconfirmed_receipt_never_execute(self):
        with self.open() as s:
            run, _ = admit(s, self.sid, self.data, self.providers)
        w = Worker({'projects': str(self.projects), 'r4os': str(self.r4os), 'projectId': self.pid, 'runId': run['id']})
        w.thread_id = 'thread'; w.turn_id = 'turn'; w.config['permissions']['studio.write_file'] = False
        calls = []
        async def execute(*args): calls.append(args); return {'success': True, 'output': 'done'}
        w.execute = execute
        params = {'namespace': None, 'threadId': 'thread', 'turnId': 'turn', 'tool': 'studio_write_file', 'callId': 'call', 'arguments': {'path': 'x', 'content': 'x', 'expectedSha256': None}}
        async def scenario():
            first = await w.tool(params); second = await w.tool(params)
            self.assertEqual(first, second); self.assertFalse(first['success']); self.assertFalse(calls)
            w.store.db.execute("UPDATE tools SET result=NULL,state='intent'"); w.store.db.commit()
            result = await w.tool(params)
            self.assertIn('unknown', result['contentItems'][0]['text']); self.assertFalse(calls)
        try: asyncio.run(scenario())
        finally: w.store.close()


if __name__ == '__main__': unittest.main()
