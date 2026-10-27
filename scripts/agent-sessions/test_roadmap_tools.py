"""Real run-bound sidecar, shared SQLite and native tool receipts, without inference."""
import asyncio
from contextlib import closing
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import AsyncMock, patch
import uuid

import test_runs as fixtures
from owner import open_lock
from profile import PROFILE, ROADMAP_TOOLS, permission_tools, default_enabled
from run_store import admit, get_run, transition
from session_store import encode
from tool_catalog import specifications, validate_arguments
from worker import Worker


BASELINES = {
    'studio-tools-v1': '2a8e8c5e80658419cf678bb368f04553e6c5ff06ac93c9a483cc54a3c6f5e44e',
    'studio-tools-v2': '0e85e82c2d125a15785608cd281ba39dd828f867ada68fc09de880823f0e3057',
    'studio-tools-v3': '4d392a7c5672c005ea051ba5672a1629ad881933776e248dd626f063385641c8',
    'studio-tools-v4': '22b62dcedaff93f3fb78f4acaf54f3b02ad7f0bbff5967599beb52e7c73cfae5',
    'studio-tools-v5': 'b743584c868f47a745e7ae4f88e7664ad902c8838cb0409ffa80638fd031148e',
    'studio-tools-v6': 'd3c76ebc68eadb9fb01df170923127ed6b4b66ede34a6da3cd150b653c5d7d7f',
    'studio-tools-v7': 'e2f7b16fff171ef9eb3dc7e80f78302ef544666f297c4bbdf32b1f514c6fceb4',
    'studio-skill-tools-v1': '052d6da018ae07d593af3537944b1819069ec6876ba56bf8f6c9dc1df650e2b1',
    'studio-skill-tools-v2': 'a1cabe60fbec894c9b1ae74c7e7fa519a3ceb9633dec92265e5a238ab47f2253',
}


class RoadmapToolsTest(unittest.IsolatedAsyncioTestCase):
    open = fixtures.Runs.open

    def setUp(self):
        fixtures.Runs.setUp(self)
        self.workers = []
        with self.open() as store:
            settings = {**self.settings, 'permissions': {'studio.' + t: default_enabled(t) for t in permission_tools(PROFILE)}}
            store.db.execute('UPDATE sessions SET settings=?,engine=?', (encode(settings), encode({'profile': PROFILE})))
            store.db.commit()

    def tearDown(self):
        for worker in self.workers:
            if worker.lease: worker.lease.close()
            worker.store.close()
        fixtures.Runs.tearDown(self)

    def start(self, sid=None, enabled=True):
        sid = sid or self.sid
        with self.open() as store:
            value = store.get(sid)
            value = store.update(sid, {'revision': value['revision'], 'roadmapEnabled': enabled}, self.providers)
            run, _ = admit(store, sid, {**self.data, 'requestId': str(uuid.uuid4()), 'revision': value['revision']}, self.providers)
            birth = (Path('/proc') / str(os.getpid()) / 'stat').read_text().rsplit(') ', 1)[1].split()[19]
            transition(store, run['id'], 'running', worker={'release': 'fixture', 'pid': os.getpid(), 'birth': birth})
        worker = Worker({'projects': str(self.projects), 'r4os': str(self.r4os), 'projectId': self.pid,
                         'sessionId': sid, 'runId': run['id'], 'release': 'fixture'})
        worker.thread_id = 'thread-' + sid; worker.turn_id = 'turn-' + run['id']
        worker.lease = open_lock(self.projects, 'project', self.pid)
        fcntl.flock(worker.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.workers.append(worker)
        return worker

    def finish(self, worker):
        transition(worker.store, worker.run_id, 'completed')
        worker.lease.close()

    async def call(self, worker, tool, arguments, call_id=None):
        result = await worker.tool({'namespace': None, 'threadId': worker.thread_id, 'turnId': worker.turn_id,
                                    'tool': 'studio_' + tool, 'callId': call_id or str(uuid.uuid4()), 'arguments': arguments})
        return json.loads(result['contentItems'][0]['text'])

    async def good(self, worker, tool, arguments, call_id=None):
        result = await self.call(worker, tool, arguments, call_id)
        self.assertTrue(result['success'], result)
        return json.loads(result['output'])

    async def test_shared_ui_store_all_levels_notes_and_original_request_receipts(self):
        worker = self.start()
        missing = await self.good(worker, 'read_roadmap', {'view': 'overview'})
        self.assertFalse(missing['exists'])
        initialized = await self.good(worker, 'update_roadmap', {'operation': 'initialize', 'requestId': str(uuid.uuid4())})
        root_id = initialized['entity']['id']
        current = await self.good(worker, 'read_roadmap', {'view': 'current'})
        current_id = current['currentVersionId']
        async def mutate(target, action, content):
            current = await self.good(worker, 'read_roadmap', {'view': 'revision'})
            arguments = {'operation': 'mutate', 'requestId': str(uuid.uuid4()), **{'expectedRevision': current['revision'], 'currentVersionId': current['currentVersionId']},
                         'target': target, 'action': action, 'input': content}
            return await self.good(worker, 'update_roadmap', arguments), arguments
        sub, _ = await mutate({'kind': 'subversion', 'versionId': current_id}, 'create', {'title': 'Shared work'})
        sub_id = sub['entity']['id']
        task, original = await mutate({'kind': 'task', 'versionId': current_id, 'subversionId': sub_id}, 'create', {'description': 'One task', 'notes': 'Original'})
        task_id = task['entity']['id']
        await mutate({'kind': 'acceptance', 'versionId': current_id, 'subversionId': sub_id}, 'create', {'description': 'Separate check', 'status': 'done'})
        await mutate({'kind': 'task', 'versionId': current_id, 'subversionId': sub_id, 'id': task_id}, 'append_notes', {'notes': 'Actual evidence 🙂'})
        await mutate({'kind': 'roadmap', 'id': root_id}, 'replace_notes', {'notes': 'Project history'})
        # Different native call ID with exactly the original request returns the old result.
        duplicate = await self.good(worker, 'update_roadmap', original)
        self.assertEqual(duplicate, task)
        receipt = await self.good(worker, 'read_roadmap', {'view': 'receipt', 'requestId': original['requestId']})
        self.assertTrue(receipt['confirmed']); self.assertEqual(receipt['result'], task)
        tasks = await self.good(worker, 'read_roadmap', {'view': 'tasks', 'versionId': current_id, 'subversionId': sub_id})
        self.assertEqual(len(tasks['items']), 1)
        self.assertNotIn('notes', tasks['items'][0]); self.assertIn('textFields', tasks['items'][0])
        # The browser's SQLite dataset is the very same committed row, with no extra API or DB.
        database = self.projects / self.pid / 'Roadmap/Roadmap.sqlite'
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute('SELECT notes FROM tasks WHERE id=?', (task_id,)).fetchone()[0], 'Original\nActual evidence 🙂')
            self.assertEqual(db.execute('SELECT count(*) FROM acceptances').fetchone()[0], 1)
        self.assertTrue(any(item.get('roadmap', {}).get('requestId') == original['requestId'] for item in worker.store.history(self.sid)['items']))
        # Another saved session sees the same project roadmap after the first run finishes.
        second = str(uuid.uuid4())
        row = worker.store.row(self.sid)
        worker.store.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,NULL,1,'now','now')", (second, self.pid, 'Second', row['settings'], row['engine'])); worker.store.db.commit()
        self.finish(worker)
        other = self.start(second)
        shared = await self.good(other, 'read_roadmap', {'view': 'entry', 'target': {'kind': 'roadmap', 'id': root_id}})
        self.assertEqual(shared['entity']['textFields']['notes']['preview'], 'Project history')

    async def test_off_parent_scope_stale_binding_worker_change_and_stop_fail_before_effect(self):
        worker = self.start(enabled=False)
        denied = await self.call(worker, 'update_roadmap', {'operation': 'initialize', 'requestId': str(uuid.uuid4())}, 'off')
        self.assertEqual(denied['error'], 'disabled')
        self.assertFalse((self.projects / self.pid / 'Roadmap').exists())
        self.finish(worker)
        worker = self.start()
        initialize = {'operation': 'initialize', 'requestId': str(uuid.uuid4())}
        await self.good(worker, 'update_roadmap', initialize, 'original-enabled-call')
        self.finish(worker)
        off_worker = self.start(enabled=False)
        historical = await self.call(off_worker, 'update_roadmap', initialize, 'original-enabled-call')
        self.assertEqual(historical['error'], 'disabled')
        self.finish(off_worker)
        worker = self.start()
        current = await self.good(worker, 'read_roadmap', {'view': 'current'})
        args = {'operation': 'mutate', 'requestId': str(uuid.uuid4()), 'expectedRevision': current['revision'], 'currentVersionId': str(uuid.uuid4()),
                'target': {'kind': 'version', 'id': current['currentVersionId']}, 'action': 'update', 'input': {'title': 'Must not save'}}
        result = await self.call(worker, 'update_roadmap', args); self.assertEqual(result['error'], 'conflict')
        result = await self.call(worker, 'read_roadmap', {'view': 'subversions', 'versionId': str(uuid.uuid4())}); self.assertFalse(result['success'])
        result = await self.call(worker, 'read_roadmap', {'view': 'current', 'projectId': str(uuid.uuid4())}); self.assertEqual(result['error'], 'invalidArguments')
        # Replaced worker metadata is re-read by the child, rather than trusting a cached Worker.config.
        with worker.store.db: worker.store.db.execute('UPDATE runs SET worker=? WHERE id=?', (encode({'pid': os.getpid(), 'birth': 'different', 'release': 'fixture'}), worker.run_id))
        result = await self.call(worker, 'read_roadmap', {'view': 'revision'}); self.assertEqual(result['error'], 'denied')
        transition(worker.store, worker.run_id, 'stopping')
        result = await self.call(worker, 'update_roadmap', args); self.assertEqual(result['error'], 'interrupted')

    async def test_text_and_full_export_are_byte_paged_and_cleanup_requires_original_workflow(self):
        worker = self.start()
        initialized = await self.good(worker, 'update_roadmap', {'operation': 'initialize', 'requestId': str(uuid.uuid4())})
        reference = {'kind': 'roadmap', 'id': initialized['entity']['id']}
        text = 'ä🙂\n' * 4000
        value = await self.good(worker, 'update_roadmap', {'operation': 'mutate', 'requestId': str(uuid.uuid4()), 'expectedRevision': initialized['revision'],
                    'currentVersionId': initialized['currentVersionId'], 'target': reference, 'action': 'replace_notes', 'input': {'notes': text}})
        offset, chunks = 0, []
        while offset is not None:
            page = await self.good(worker, 'read_roadmap', {'view': 'text', 'target': reference, 'field': 'notes', 'offset': offset, 'byteLimit': 4096, 'expectedRevision': value['revision']})
            chunks.append(page['text']); offset = page['nextOffset']
        self.assertEqual(''.join(chunks), text)
        request = {'operation': 'export', 'requestId': str(uuid.uuid4()), 'expectedRevision': value['revision'],
                   'currentVersionId': value['currentVersionId'], 'versionId': value['currentVersionId']}
        exported = await self.good(worker, 'update_roadmap', request)
        offset, chunks = 0, []
        while offset is not None:
            page = await self.good(worker, 'read_roadmap', {'view': 'export_chunk', 'exportId': exported['id'], 'offset': offset})
            chunks.append(page['text']); offset = page['nextOffset']
        raw = ''.join(chunks).encode()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), exported['sha256']); self.assertEqual(len(raw), exported['byteLength'])
        self.assertIn(text, raw.decode())
        unavailable = await self.call(worker, 'cleanup_roadmap', {'action': 'finalize'})
        self.assertEqual(unavailable['error'], 'failed')
        self.assertFalse((worker.store.workspace / 'Docs').exists())

    async def test_lost_sidecar_response_is_reconciled_after_restart_without_repeating_effect(self):
        worker = self.start()
        initial = await self.good(worker, 'update_roadmap', {'operation': 'initialize', 'requestId': str(uuid.uuid4())})
        arguments = {'operation': 'mutate', 'requestId': str(uuid.uuid4()), 'expectedRevision': initial['revision'],
                     'currentVersionId': initial['currentVersionId'], 'target': {'kind': 'version'}, 'action': 'create',
                     'input': {'title': 'Exactly one version', 'number': '0.2.X'}}
        original_spawn = asyncio.create_subprocess_exec

        async def lose_reply(*args, **kwargs):
            process = await original_spawn(*args, **kwargs)
            original_communicate = process.communicate

            async def communicate(*args, **kwargs):
                raw, _ = await original_communicate(*args, **kwargs)
                self.assertIn(b'Exactly one version', raw)  # DB committed; transport then loses this reply.
                raise ConnectionError('Own simulated lost pipe response')
            process.communicate = communicate
            return process

        worker.development.stop_owned = AsyncMock()
        with patch('roadmap_tools.asyncio.create_subprocess_exec', side_effect=lose_reply):
            result = await self.call(worker, 'update_roadmap', arguments, 'lost-reply')
        self.assertEqual(result['error'], 'unknown')
        await asyncio.sleep(0)
        self.assertTrue(worker.done.is_set())
        transition(worker.store, worker.run_id, 'unknown'); worker.lease.close()
        next_worker = self.start()
        receipt = await self.good(next_worker, 'read_roadmap', {'view': 'receipt', 'requestId': arguments['requestId']})
        self.assertTrue(receipt['confirmed'])
        recovered = await self.good(next_worker, 'update_roadmap', arguments)
        self.assertEqual(recovered, receipt['result'])
        versions = await self.good(next_worker, 'read_roadmap', {'view': 'versions'})
        self.assertEqual(len(versions['items']), 2)
        self.assertEqual(sum(v['title'] == 'Exactly one version' for v in versions['items']), 1)

    def test_original_profiles_stay_byte_identical_and_new_tools_have_no_individual_permissions(self):
        self.assertEqual(PROFILE, 'studio-tools-v8')
        self.assertEqual(len(specifications(PROFILE)), 34)
        self.assertFalse(set(ROADMAP_TOOLS) & set(permission_tools(PROFILE)))
        for profile, expected in BASELINES.items():
            actual = hashlib.sha256(json.dumps(specifications(profile), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            self.assertEqual(actual, expected, profile)
        for tool in ROADMAP_TOOLS:
            with self.assertRaises(ValueError): validate_arguments(tool, {}, 'studio-tools-v7')
        for bad in ({'view': 'current', 'path': '/etc'}, {'view': 'current', 'projectId': str(uuid.uuid4())}):
            with self.assertRaises(ValueError): validate_arguments('read_roadmap', bad)
        import importlib.util
        spec = importlib.util.spec_from_file_location('roadmap_update_compatibility', Path(__file__).resolve().parents[1] / 'updates/host.py')
        host = importlib.util.module_from_spec(spec); spec.loader.exec_module(host)
        for contract in (host.COMPATIBILITY, host.DEVELOPMENT_COMPATIBILITY, host.SKILL_COMPATIBILITY,
                         host.AUTHOR_COMPATIBILITY, host.UPDATE_COMPATIBILITY, host.GIT_COMPATIBILITY,
                         host.INPUT_COMPATIBILITY, host.ROADMAP_COMPATIBILITY):
            self.assertTrue(host.compatible(contract))
        self.assertFalse(host.compatible({**host.ROADMAP_COMPATIBILITY, 'agentDataSchema': 2}))
