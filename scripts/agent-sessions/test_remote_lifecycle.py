"""Two real projects/actors share resolved endpoints; human review never replays."""
import asyncio
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import unittest
import uuid
from unittest.mock import AsyncMock, patch
from test_remote_profile import RemoteProfileTests
from test_remote_commands import RemoteCommandTests, remote_catalog, remote_checks, key
from session_store import SessionStore, encode
from profile import PROFILE
from run_store import admit, transition
from worker import Worker
from owner import open_lock
from store import connect
from remote_binding import set_binding, assert_change_safe
from catalog import CatalogFault
import lifecycle
import job_store


class RemoteLifecycleTests(unittest.IsolatedAsyncioTestCase):
    setUp = RemoteProfileTests.setUp
    tearDown = RemoteProfileTests.tearDown
    open = RemoteProfileTests.open
    start = RemoteProfileTests.start
    finish = RemoteProfileTests.finish
    setup_remote = RemoteProfileTests.setup_remote
    reserve = RemoteProfileTests.reserve
    native = RemoteProfileTests.native
    call = RemoteProfileTests.call
    wait = RemoteProfileTests.wait

    def second(self):
        host = remote_catalog.operation(self.directory, {'operation': 'create', 'input': {'requestId': str(uuid.uuid4()), 'name': 'Own DNS alias', 'address': 'localhost'}})
        attempt = remote_checks.begin(self.directory, host['id'], {'requestId': str(uuid.uuid4()), 'revision': 1})
        host = remote_checks.finish(self.directory, attempt, {'status': 'success', 'version': '0.0.1', 'kernel': '0.0.2', 'key': key()})['host']
        pid = str(uuid.uuid4())
        with closing(connect(self.projects)) as db, db:
            db.execute("INSERT INTO projects VALUES (?,?,'','C','terminal',?,NULL,'{}','now','now',1,'ready')", (pid, 'Second own project', 'second_own_project'))
            set_binding(db, pid, host['id'])
        workspace = self.projects / pid / 'Workspace'; workspace.mkdir(parents=True); (workspace / 'module.R4MF').write_text('R4OS_MODULE_MANIFEST=2\n')
        with closing(SessionStore(self.projects, self.r4os, pid)) as store, patch('session_store.engine', return_value={'profile': PROFILE, 'available': True}):
            session = store.create({'name': 'Second own session', 'providerId': self.provider, 'model': 'fixture', 'effort': 'low', 'requestId': str(uuid.uuid4())}, self.providers)
            run, _ = admit(store, session['id'], {'requestId': str(uuid.uuid4()), 'revision': 1, 'text': 'Own explicit remote test fixture', 'remoteHostTools': 1}, self.providers)
            birth = __import__('pathlib').Path('/proc/' + str(os.getpid()) + '/stat').read_text().rsplit(') ', 1)[1].split()[19]
            transition(store, run['id'], 'running', worker={'pid': os.getpid(), 'birth': birth, 'release': 'fixture'})
        worker = Worker({'projects': str(self.projects), 'r4os': str(self.r4os), 'projectId': pid, 'sessionId': session['id'], 'runId': run['id'], 'release': 'fixture'})
        worker.thread_id = 'own-thread-' + session['id']; worker.turn_id = 'own-turn-' + run['id']
        worker.lease = open_lock(self.projects, 'project', pid); fcntl.flock(worker.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        worker.development.stop_owned = AsyncMock(); self.workers.append(worker)
        return worker, host

    async def test_dns_and_ip_aliases_across_projects_do_not_dispatch_concurrent_effects(self):
        first = await self.native(); second, alias = self.second(); self.release.clear()
        pending = asyncio.create_task(self.call(first, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'OWN FIRST EFFECT'}))
        await asyncio.wait_for(self.reached.wait(), 5)
        blocked = await self.call(second, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'OWN SECOND EFFECT'})
        self.assertFalse(blocked['success']); self.assertEqual(self.calls, ['OWN FIRST EFFECT']); self.assertIn('active Studio effect', blocked['output'])
        first_job = next(iter(self.broker.commands.active)); original = job_store.read(self.projects, self.pid, first_job)
        self.assertEqual(original['endpointIdentity']['connectAddress'], '127.0.0.1')
        self.release.set(); self.assertTrue((await pending)['success'])
        next_job = await self.call(second, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'OWN SECOND EFFECT'})
        self.assertTrue(next_job['success'], next_job); self.assertEqual(len(self.calls), 2)
        original = json.loads(next_job['output']); self.assertIn('127.0.0.1', original['endpointIdentity']['addresses']); self.assertEqual(original['hostId'], alias['id'])

    async def test_unknown_alias_effect_review_is_human_only_exact_and_never_original_success(self):
        first = await self.native(); second, alias = self.second(); self.release.clear()
        args = {'requestId': str(uuid.uuid4()), 'command': 'OWN UNCERTAIN EFFECT'}
        pending = asyncio.create_task(self.call(first, 'run_remote_command', args)); await asyncio.wait_for(self.reached.wait(), 5)
        await first.stop(); result = await asyncio.wait_for(pending, 8); await self.wait()
        job_id = result['remote']['id']; original = job_store.read(self.projects, self.pid, job_id)
        self.assertEqual(original['state'], 'unknown')
        acknowledgement = {'requestId': str(uuid.uuid4()), 'expectedUpdatedAt': original['updatedAt'], 'confirmUnknown': True}
        with self.assertRaises(CatalogFault): lifecycle.review(self.projects, self.pid, self.host['id'], job_id, acknowledgement)
        with self.assertRaises(Exception): assert_change_safe(self.projects, self.pid)
        with self.assertRaises(CatalogFault): remote_catalog.operation(self.directory, {'operation': 'update', 'id': self.host['id'], 'input': {'requestId': str(uuid.uuid4()), 'revision': self.host['revision'], 'password': 'unapplied-password'}})
        self.release.set(); blocked = await self.call(second, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'OWN OTHER EFFECT'})
        self.assertFalse(blocked['success']); self.assertIn('uncertain effect', blocked['output']); self.assertEqual(len(self.calls), 1)
        diagnostic = await self.call(second, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'VER'})
        self.assertTrue(diagnostic['success']); self.assertEqual(len(self.calls), 2)
        transition(first.store, first.run_id, 'unknown'); first.lease.close()
        reviewed = lifecycle.review(self.projects, self.pid, self.host['id'], job_id, acknowledgement)
        self.assertEqual(reviewed['originalOutcome'], 'unknown'); self.assertFalse(reviewed['remoteProcessEndConfirmed'])
        self.assertEqual(lifecycle.review(self.projects, self.pid, self.host['id'], job_id, acknowledgement), reviewed)
        self.assertEqual(lifecycle.receipt(self.projects, self.pid, self.host['id'], job_id, acknowledgement['requestId']), reviewed)
        kept = job_store.read(self.projects, self.pid, job_id); self.assertEqual(kept['state'], 'unknown_reviewed'); self.assertEqual(kept['result'], original['result'])
        with job_store.connection(self.projects, self.pid) as db: self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?', (job_id,)).fetchone()[0], 'unknown')
        with self.assertRaises(CatalogFault): lifecycle.review(self.projects, self.pid, self.host['id'], job_id, {**acknowledgement, 'expectedUpdatedAt': 'different'})
        self.assertIsNone(assert_change_safe(self.projects, self.pid))
        allowed = await self.call(second, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'OWN NEW WORK'})
        self.assertTrue(allowed['success'], allowed); self.assertEqual(len(self.calls), 3)
        new_first = self.start(); new_first.development.stop_owned = AsyncMock()
        legacy = await RemoteCommandTests.call(self, new_first, 'run_remote_command', args)
        self.assertEqual(legacy['result']['state'], 'unknown'); self.assertEqual(len(self.calls), 3)
        replay = await self.call(new_first, 'run_remote_command', args)
        self.assertFalse(replay['success']); self.assertEqual(replay['error'], 'unknown'); self.assertEqual(len(self.calls), 3)
        await asyncio.sleep(.05)

    async def test_review_list_details_and_wrong_project_host_or_stale_input_do_not_change_original(self):
        worker = await self.native(); result = await self.call(worker, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'VER'})
        job_id = result['remote']['id']; listing = lifecycle.listings(self.projects, self.host['id'])
        self.assertEqual(listing['jobs'][0]['id'], job_id); self.assertNotIn('rosebud', json.dumps(listing))
        detail = lifecycle.details(self.projects, self.pid, self.host['id'], job_id); self.assertEqual(detail['state'], 'completed')
        with self.assertRaises(CatalogFault): lifecycle.details(self.projects, self.pid, str(uuid.uuid4()), job_id)
        with self.assertRaises(CatalogFault): lifecycle.review(self.projects, self.pid, self.host['id'], job_id, {'requestId': str(uuid.uuid4()), 'expectedUpdatedAt': detail['updatedAt'], 'confirmUnknown': True})
        self.assertEqual(job_store.read(self.projects, self.pid, job_id)['state'], 'completed')
        denied = await self.call(worker, 'review_remote_job', {'jobId': job_id})
        self.assertFalse(denied['success']); self.assertEqual(denied['error'], 'invalidCall')

    async def test_offline_restore_cli_reviews_only_its_copy_without_a_global_host_catalog(self):
        worker = await self.native(); self.release.clear()
        pending = asyncio.create_task(self.call(worker, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'OWN RESTORE FIXTURE'}))
        await asyncio.wait_for(self.reached.wait(), 5); await worker.stop(); result = await pending; await self.wait(); await asyncio.sleep(.05)
        transition(worker.store, worker.run_id, 'unknown'); worker.lease.close(); job_id = result['remote']['id']
        restored = self.root / 'OwnOfflineRestore' / 'Projects'
        shutil.copytree(self.projects, restored, ignore=lambda _path, names: [n for n in names if '.sqlite' in n.lower()])
        for path in self.projects.rglob('*.sqlite'):
            destination = restored / path.relative_to(self.projects)
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as source, closing(sqlite3.connect(destination)) as target: source.backup(target)
            destination.chmod(0o600)
        self.assertFalse((restored.parent / 'RemoteHosts').exists())
        helper = Path(__file__).resolve().parents[1] / 'remote-hosts/lifecycle-cli.py'
        async def cli(value):
            process = await asyncio.create_subprocess_exec('/usr/bin/python3', '-B', str(helper), str(restored), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            raw, error = await process.communicate(encode(value).encode()); self.assertFalse(error); response = json.loads(raw); self.assertEqual(process.returncode, 0, response); return response['result']
        request = {'operation': 'read', 'projectId': self.pid, 'hostId': self.host['id'], 'jobId': job_id}
        original = await cli(request); self.assertEqual(original['state'], 'unknown')
        acknowledged = await cli({**request, 'operation': 'review', 'input': {'requestId': str(uuid.uuid4()), 'expectedUpdatedAt': original['updatedAt'], 'confirmUnknown': True}})
        self.assertEqual(acknowledged['originalOutcome'], 'unknown'); self.assertEqual((await cli(request))['state'], 'unknown_reviewed')
        self.assertEqual(job_store.read(self.projects, self.pid, job_id)['state'], 'unknown'); self.assertEqual(len(self.calls), 1)
        self.assertFalse((restored.parent / 'RemoteHosts').exists())
