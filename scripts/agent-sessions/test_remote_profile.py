"""Real v9 admission, native-call dispatcher, private actor and streamed harness."""
import asyncio
from contextlib import closing
import hashlib
import json
import subprocess
import unittest
import uuid
from unittest.mock import AsyncMock, patch
from test_remote_commands import RemoteCommandTests, remote_catalog
from test_remote_files import RemoteFilesTests
from profile import PROFILE, REMOTE_TOOLS, ROADMAP_PROFILE, SKILL_PROFILES, permission_tools, tools_for
from run_store import get_run, transition
from store import connect, operation
from tool_catalog import specifications, validate_arguments
import remote_tools
import job_store


class RemoteProfileTests(unittest.IsolatedAsyncioTestCase):
    setUp = RemoteCommandTests.setUp
    tearDown = RemoteCommandTests.tearDown
    open = RemoteCommandTests.open
    start = RemoteCommandTests.start
    finish = RemoteCommandTests.finish
    setup_remote = RemoteCommandTests.setup_remote
    setup_files = RemoteFilesTests.setup_files
    wait = RemoteCommandTests.wait

    def reserve(self, worker):
        # This suite requires actual RunStore.freeze; no trusted-field rewrite.
        self.assertEqual(worker.config['engine']['profile'], PROFILE)
        self.assertEqual(worker.config['remoteHostBinding'], self.host)

    async def native(self, files=False):
        self.data['remoteHostTools'] = 1
        worker = await self.setup_files() if files else await self.setup_remote()
        patcher = patch.object(remote_tools, 'SOCKET_PATH', str(self.runtime / 'agent.sock')); patcher.start(); self.addCleanup(patcher.stop)
        worker.development.stop_owned = AsyncMock()
        return worker

    async def call(self, worker, name, arguments):
        raw = await worker.tool({'namespace': None, 'threadId': worker.thread_id, 'turnId': worker.turn_id,
                                'callId': str(uuid.uuid4()), 'tool': 'studio_' + name, 'arguments': arguments})
        return json.loads(raw['contentItems'][0]['text'])

    async def test_actual_frozen_host_native_dispatch_streamed_card_and_original_receipt(self):
        worker = await self.native(); self.assertFalse(self.calls)
        metadata = await self.call(worker, 'get_remote_host', {}); self.assertTrue(metadata['success'], metadata)
        self.assertEqual(json.loads(metadata['output'])['hostId'], self.host['id']); self.assertFalse(self.calls)
        result = await self.call(worker, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'VER'})
        self.assertTrue(result['success'], result); self.assertEqual(result['exitCode'], 0); self.assertEqual(self.calls, ['VER'])
        self.assertEqual(result['remote']['hostName'], self.host['name']); self.assertFalse(result['remote']['remoteProcessEndConfirmed'])
        read = await self.call(worker, 'read_remote_job', {'jobId': result['remote']['id']}); self.assertTrue(read['success']); self.assertEqual(len(self.calls), 1)
        cards = [json.loads(row[0]) for row in worker.store.db.execute("SELECT payload FROM events WHERE kind='item'")]
        self.assertTrue(any(c.get('remote', {}).get('id') == result['remote']['id'] and c['status'] == 'running' for c in cards))
        self.assertTrue(any(c.get('remote', {}).get('state') == 'completed' for c in cards))
        self.assertNotIn('rosebud', json.dumps(cards))
        frozen = json.loads(get_run(worker.store, worker.run_id)['config']); self.assertEqual(frozen['remoteHostBinding'], self.host)

    async def test_saved_off_is_frozen_and_does_not_contact_the_host(self):
        worker = await self.native(); self.finish(worker)
        with self.open() as store:
            old = store.get(self.sid); permissions = dict(old['permissions'])
            for name in REMOTE_TOOLS: permissions['studio.' + name] = False
            saved = store.update(self.sid, {'revision': old['revision'], 'permissions': permissions}, self.providers)
            self.assertTrue(all(saved['permissions']['studio.' + name] is False for name in REMOTE_TOOLS))
        worker = self.start(); worker.development.stop_owned = AsyncMock()
        self.assertEqual(worker.config['permissions'], permissions); self.assertEqual(worker.config['remoteHostBinding'], self.host)
        result = await self.call(worker, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'VER'})
        self.assertFalse(result['success']); self.assertEqual(result['error'], 'disabled'); self.assertFalse(self.calls)

    async def test_native_file_schema_dispatch_permissions_and_original_sftp_receipt(self):
        worker = await self.native(files=True); raw = b'own native-file-boundary bytes'; (self.workspace / 'new.bin').write_bytes(raw)
        sha = hashlib.sha256(raw).hexdigest()
        upload = await self.call(worker, 'remote_files', {'requestId': str(uuid.uuid4()), 'action': 'upload', 'path': '/C/TEMP/new.bin', 'sourcePath': 'new.bin', 'sha256': sha})
        self.assertTrue(upload['success'], upload); self.assertEqual(upload['remote']['operation'], 'files')
        self.assertTrue(json.loads(upload['output'])['result']['fullReadbackVerified'])
        download = await self.call(worker, 'remote_files', {'requestId': str(uuid.uuid4()), 'action': 'download', 'path': '/C/TEMP/new.bin', 'localPath': 'download.bin', 'expectedSha256': None, 'remoteSha256': sha})
        self.assertTrue(download['success'], download); self.assertEqual((self.workspace / 'download.bin').read_bytes(), raw)

    async def test_missing_assignment_and_changed_target_revision_prevent_effect(self):
        worker = await self.native()
        remote_catalog.operation(self.directory, {'operation': 'update', 'id': self.host['id'], 'input': {'requestId': str(uuid.uuid4()), 'revision': self.host['revision'], 'port': 2222}})
        result = await self.call(worker, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'VER'})
        self.assertFalse(result['success']); self.assertEqual(result['error'], 'conflict'); self.assertFalse(self.calls)
        self.finish(worker)
        with closing(connect(self.projects)) as db:
            revision = db.execute('SELECT revision FROM projects WHERE id=?', (self.pid,)).fetchone()[0]
            operation(db, {'operation': 'update', 'id': self.pid, 'input': {'revision': revision, 'remoteHostId': None}}, self.r4os)
        worker = self.start(); self.assertIsNone(worker.config['remoteHostBinding'])
        metadata = await self.call(worker, 'get_remote_host', {}); self.assertFalse(metadata['success']); self.assertIn('No Remote Host', metadata['output'])
        result = await self.call(worker, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'VER'})
        self.assertFalse(result['success']); self.assertFalse(self.calls)

    async def test_user_stop_does_not_require_model_stop_permission_or_claim_remote_end(self):
        worker = await self.native(); self.finish(worker)
        with self.open() as store:
            value = store.get(self.sid); permissions = {**value['permissions'], 'studio.stop_remote_job': False}
            store.update(self.sid, {'revision': value['revision'], 'permissions': permissions}, self.providers)
        worker = self.start(); worker.development.stop_owned = AsyncMock(); self.release.clear()
        pending = asyncio.create_task(self.call(worker, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'OWN WORK'}))
        await asyncio.wait_for(self.reached.wait(), 5)
        transition(worker.store, worker.run_id, 'stopping'); await worker.stop(); result = await asyncio.wait_for(pending, 8); await self.wait()
        self.assertEqual(len(self.calls), 1); self.assertFalse(result['success']); self.assertEqual(result['error'], 'unknown')
        original = job_store.read(self.projects, self.pid, result['remote']['id'])
        self.assertEqual(original['state'], 'unknown'); self.assertFalse(original['result']['remoteProcessEndConfirmed'])
        await asyncio.sleep(.05)

    async def test_metadata_reader_works_in_a_real_readonly_namespace_without_catalog_changes(self):
        worker = await self.native(); before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.directory.iterdir() if p.is_file()}
        from test_remote_commands import REMOTE
        result = await asyncio.to_thread(subprocess.run, ['/usr/bin/bwrap', '--unshare-net', '--ro-bind', '/', '/', '--', '/usr/bin/python3', '-B', str(REMOTE / 'metadata.py'), str(self.directory), self.host['id']], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode()); value = json.loads(result.stdout)['result']; self.assertEqual(value['id'], self.host['id']); self.assertNotIn('password', value)
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.directory.iterdir() if p.is_file()})

    def test_v9_schemas_old_profile_separation_and_new_session_defaults(self):
        self.assertEqual(PROFILE, 'studio-tools-v12'); self.assertEqual(len(specifications(PROFILE)), 42)
        self.assertEqual(len(specifications('studio-tools-v9')),39)
        self.assertEqual(len(specifications('studio-tools-v10')),40)
        self.assertEqual(len(specifications('studio-tools-v11')),42)
        self.assertFalse(set(REMOTE_TOOLS) & set(tools_for(ROADMAP_PROFILE)))
        for profile in SKILL_PROFILES: self.assertFalse(set(REMOTE_TOOLS) & set(tools_for(profile)))
        rid = str(uuid.uuid4())
        validate_arguments('remote_files', {'requestId': rid, 'action': 'download', 'path': '/C/a.bin', 'localPath': 'a.bin', 'expectedSha256': None, 'remoteSha256': 'f' * 64})
        for bad in ({'jobId': rid, 'requestId': rid}, {}, {'address': 'example.org'}):
            with self.assertRaises(ValueError): validate_arguments('read_remote_job', bad)
        with self.assertRaises(ValueError): validate_arguments('remote_files', {'requestId': rid, 'action': 'upload', 'path': '/C/a.bin'})
        from session_store import SessionStore
        with self.open() as store, patch('session_store.engine', return_value={'profile': PROFILE, 'available': True}):
            created = store.create({'requestId': rid, 'name': 'Current own profile', 'providerId': self.provider, 'model': 'fixture', 'effort': 'low'}, self.providers)
        self.assertTrue(all(created['permissions']['studio.' + name] is True for name in REMOTE_TOOLS))
        self.assertEqual(len(created['permissions']), len(permission_tools(PROFILE)))
