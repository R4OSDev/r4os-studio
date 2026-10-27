"""Real SCM-bound workers and SFTP packets through an offline local process."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import unittest
import uuid
from unittest.mock import patch
from test_remote_commands import RemoteCommandTests, REMOTE
from transport import RemoteTransport
import file_access


class RemoteFilesTests(unittest.IsolatedAsyncioTestCase):
    setUp = RemoteCommandTests.setUp
    tearDown = RemoteCommandTests.tearDown
    open = RemoteCommandTests.open
    start = RemoteCommandTests.start
    finish = RemoteCommandTests.finish
    setup_remote = RemoteCommandTests.setup_remote
    reserve = RemoteCommandTests.reserve
    call = RemoteCommandTests.call
    good = RemoteCommandTests.good
    wait = RemoteCommandTests.wait

    async def setup_files(self, lost=False):
        worker = await self.setup_remote(); self.workspace = self.projects / self.pid / 'Workspace'
        config = worker.config
        config['permissions'].update({'studio.remote_files': True, 'studio.read_file': True, 'studio.write_file': True})
        with worker.store.db: worker.store.db.execute('UPDATE runs SET config=? WHERE id=?', (json.dumps(config), worker.run_id))
        self.remote_root = self.root / 'ActualSftpFiles'; (self.remote_root / 'C/TEMP').mkdir(parents=True)
        self.log = self.root / 'Wire.jsonl'; case = self
        class Wire(RemoteTransport):
            def argv(self, sftp=False):
                return ['/usr/bin/python3', '-u', str(REMOTE / 'fixtures/sftp_server.py'), str(case.remote_root), str(case.log), *(['--lose-close'] if lost else [])]
        self.broker.commands.transport = Wire
        return worker

    def args(self, action, name, **extra): return {'requestId': str(uuid.uuid4()), 'action': action, 'path': '/C/TEMP/' + name, **extra}

    async def transfer(self, worker, arguments):
        value = await self.good(worker, 'remote_files', arguments, wait=True); return value

    async def test_list_read_hash_bound_upload_and_atomic_new_download(self):
        worker = await self.setup_files(); raw = 'spaces ä🙂 and e\u0301\n'.encode()
        (self.remote_root / 'C/TEMP/ ä🙂.txt ').write_bytes(raw)
        listing = await self.transfer(worker, self.args('list', '').__or__({'path': '/C/TEMP'}))
        self.assertEqual(listing['state'], 'completed'); self.assertEqual(listing['result']['entries'][0]['name'], ' ä🙂.txt ')
        read = await self.transfer(worker, self.args('read', ' ä🙂.txt ')); self.assertEqual(read['result']['content'], raw.decode()); self.assertEqual(read['result']['sha256'], file_access.sha(raw))
        source = b'\0\xff' + bytes(range(256)) * 130; (self.workspace / 'source.bin').write_bytes(source)
        args = self.args('upload', 'new file.bin', sourcePath='source.bin', sha256=file_access.sha(source))
        upload = await self.transfer(worker, args)
        self.assertEqual(upload['state'], 'completed', upload); self.assertTrue(upload['result']['fullReadbackVerified']); self.assertEqual((self.remote_root / 'C/TEMP/new file.bin').read_bytes(), source)
        count = len(self.log.read_text().splitlines()); replay = await self.transfer(worker, args)
        self.assertEqual(upload, replay); self.assertEqual(len(self.log.read_text().splitlines()), count)
        download = await self.transfer(worker, self.args('download', 'new file.bin', localPath='download.bin', expectedSha256=None, remoteSha256=file_access.sha(source)))
        self.assertEqual(download['state'], 'completed', download); self.assertEqual((self.workspace / 'download.bin').read_bytes(), source)
        self.assertFalse(list((self.projects / self.pid / 'RemoteHosts/Snapshots').iterdir()))
        self.assertNotIn('rosebud', (self.projects / self.pid / 'RemoteHosts/Jobs.sqlite').read_bytes().decode('latin1'))

    async def test_existing_files_hash_conflicts_permissions_links_case_and_unsupported_operations(self):
        worker = await self.setup_files(); raw = b'keep saved bytes and editor draft'; (self.workspace / 'existing.txt').write_bytes(raw)
        arguments = self.args('download', 'source.txt', localPath='existing.txt', expectedSha256=None, remoteSha256=file_access.sha(raw))
        result = await self.call(worker, 'remote_files', arguments); self.assertEqual(result['code'], 409); self.assertFalse(self.log.exists()); self.assertEqual((self.workspace / 'existing.txt').read_bytes(), raw)
        (self.remote_root / 'C/TEMP/source.txt').write_bytes(b'existing remote')
        result = await self.transfer(worker, self.args('upload', 'source.txt', sourcePath='existing.txt', sha256=file_access.sha(raw)))
        self.assertEqual(result['state'], 'failed'); self.assertEqual((self.remote_root / 'C/TEMP/source.txt').read_bytes(), b'existing remote')
        self.assertEqual((await self.call(worker, 'remote_files', self.args('upload', 'bad.bin', sourcePath='existing.txt', sha256='0' * 64)))['code'], 409)
        (self.workspace / 'linked.txt').symlink_to(self.root / 'Outside'); (self.root / 'Outside').write_bytes(b'private')
        self.assertIn('error', await self.call(worker, 'remote_files', self.args('upload', 'bad.bin', sourcePath='linked.txt', sha256=file_access.sha(b'private'))))
        self.assertEqual((await self.call(worker, 'remote_files', self.args('upload', 'bad.bin', sourcePath='EXISTING.txt', sha256=file_access.sha(raw))))['code'], 409)
        self.assertEqual((await self.call(worker, 'remote_files', self.args('delete', 'source.txt')))['code'], 400)
        self.assertEqual((await self.call(worker, 'remote_files', self.args('upload', 'bad.bin', sourcePath='../private', sha256='0' * 64)))['code'], 400)
        self.assertEqual((await self.call(worker, 'remote_files', self.args('upload', 'bad.bin', sourcePath='.studio/private', sha256='0' * 64)))['code'], 403)
        worker.config['permissions']['studio.read_file'] = False
        with worker.store.db: worker.store.db.execute('UPDATE runs SET config=? WHERE id=?', (json.dumps(worker.config), worker.run_id))
        self.assertEqual((await self.call(worker, 'remote_files', self.args('upload', 'bad.bin', sourcePath='existing.txt', sha256=file_access.sha(raw))))['code'], 403)

    async def test_lost_close_preserves_original_unknown_without_upload_replay(self):
        worker = await self.setup_files(lost=True); raw = b'published before lost acknowledgement'; (self.workspace / 'source.bin').write_bytes(raw)
        args = self.args('upload', 'lost.bin', sourcePath='source.bin', sha256=file_access.sha(raw))
        value = await self.transfer(worker, args); self.assertEqual(value['state'], 'unknown'); self.assertEqual((self.remote_root / 'C/TEMP/lost.bin').read_bytes(), raw)
        self.assertEqual(value['transfer']['path'], '/C/TEMP/lost.bin'); self.assertEqual(value['transfer']['sha256'], file_access.sha(raw))
        self.assertEqual(value['result']['transferProgress']['stagedBytesAcknowledged'], len(raw)); self.assertFalse(value['result']['transferProgress']['publicationCloseAcknowledged'])
        count = len(self.log.read_text().splitlines()); self.assertEqual((await self.transfer(worker, args))['id'], value['id']); self.assertEqual(len(self.log.read_text().splitlines()), count)
        blocked = await self.call(worker, 'remote_files', self.args('upload', 'another.bin', sourcePath='source.bin', sha256=file_access.sha(raw)))
        self.assertEqual(blocked['code'], 409)
        read = await self.transfer(worker, self.args('read', 'lost.bin')); self.assertEqual(read['state'], 'completed'); self.assertEqual(read['result']['sha256'], file_access.sha(raw))

    async def test_download_rejects_appeared_destination_and_wrong_remote_hash(self):
        worker = await self.setup_files(); raw = b'actual download'; (self.remote_root / 'C/TEMP/source.bin').write_bytes(raw)
        wrong = await self.transfer(worker, self.args('download', 'source.bin', localPath='new.bin', expectedSha256=None, remoteSha256='0' * 64))
        self.assertEqual(wrong['state'], 'failed'); self.assertFalse((self.workspace / 'new.bin').exists())
        publish = file_access.publish
        def appeared(*args):
            (self.workspace / 'new.bin').write_bytes(b'concurrent saved file and draft'); return publish(*args)
        with patch.object(file_access, 'publish', appeared):
            result = await self.transfer(worker, self.args('download', 'source.bin', localPath='new.bin', expectedSha256=None, remoteSha256=file_access.sha(raw)))
        self.assertNotEqual(result['state'], 'completed'); self.assertEqual((self.workspace / 'new.bin').read_bytes(), b'concurrent saved file and draft')
        self.assertFalse(list(self.workspace.glob('.studio-remote-*')))

    async def test_explicit_verified_user_artifact_and_refused_other_session_artifact(self):
        worker = await self.setup_files(); build_id = str(uuid.uuid4()); artifact_id = str(uuid.uuid4()); raw = b'own completed build bytes fixture'
        root = self.projects / self.pid / 'Development'; files = root / 'Artifacts' / artifact_id; files.mkdir(parents=True)
        (files / 'OWN.R4X').write_bytes(raw); proof = b'controlled original inspector receipt'; (files / 'build-proof.json').write_bytes(proof)
        from contracts import hash_value
        record = {'id': artifact_id, 'projectId': self.pid, 'buildId': build_id, 'pins': worker.config['projectPins'],
                  'files': [{'path': 'OWN.R4X', 'bytes': len(raw), 'sha256': file_access.sha(raw)}], 'buildProof': {'bytes': len(proof), 'sha256': file_access.sha(proof)}}
        record['packageSha256'] = hash_value(record['files']); (files / 'artifact.json').write_text(json.dumps(record))
        build = {'kind': 'build', 'state': 'completed', 'artifactId': artifact_id, 'sessionId': None}
        db = sqlite3.connect(root / 'Development.sqlite'); db.executescript('CREATE TABLE artifacts(id TEXT,build_id TEXT,payload TEXT);CREATE TABLE jobs(id TEXT,payload TEXT);')
        with db:
            db.execute('INSERT INTO artifacts VALUES(?,?,?)', (artifact_id, build_id, json.dumps(record))); db.execute('INSERT INTO jobs VALUES(?,?)', (build_id, json.dumps(build)))
        (root / 'Development.sqlite').chmod(0o600)
        args = self.args('upload', 'OWN.R4X', artifactId=artifact_id, artifactPath='OWN.R4X', sha256=file_access.sha(raw))
        value = await self.transfer(worker, args); self.assertEqual(value['state'], 'completed', value); self.assertEqual((self.remote_root / 'C/TEMP/OWN.R4X').read_bytes(), raw)
        build['sessionId'] = str(uuid.uuid4())
        with db: db.execute('UPDATE jobs SET payload=?', (json.dumps(build),))
        db.close()
        self.assertEqual((await self.call(worker, 'remote_files', {**args, 'requestId': str(uuid.uuid4()), 'path': '/C/TEMP/OTHER.R4X'}))['code'], 403)

    async def test_native_capability_and_entry_byte_utf8_limits(self):
        worker = await self.setup_files(); folder = self.remote_root / 'C/TEMP'
        for i in range(140): (folder / ('entry-' + str(i))).write_bytes(b'x')
        listing = await self.transfer(worker, self.args('list', '').__or__({'path': '/C/TEMP'}))
        self.assertEqual(len(listing['result']['entries']), 128); self.assertTrue(listing['result']['truncated'])
        (folder / 'large').write_bytes(b'x' * 16385)
        value = await self.transfer(worker, self.args('read', 'large')); self.assertEqual(value['state'], 'failed'); self.assertIsNone(value['result']['nativeStatus'])
        from sftp_client import path
        self.assertEqual(path('/C/TEMP/' + '€' * 253 + '🙂'), '/C/TEMP/' + '€' * 253 + '🙂')
        for bad in ('/C/../secret', '/C/a:b', '/C/' + 'x' * 256, '/C/\ud800'):
            with self.assertRaises(Exception): path(bad)
        (self.remote_root / '.unsupported_lstat').write_text('')
        value = await self.transfer(worker, self.args('read', 'large'))
        self.assertEqual(value['state'], 'failed'); self.assertEqual(value['result']['nativeStatus'], 8); self.assertIn('not support', value['result']['message'])
