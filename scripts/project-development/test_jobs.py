import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid

from contracts import DevelopmentFault, encode, digest, hash_value
from jobs import Jobs, now
from snapshot import capture
from store import connect, operation as project_operation, ProjectFault
from layout import save


class JobsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.id = str(uuid.uuid4()); self.workspace = self.root / self.id / 'Workspace'
        self.workspace.mkdir(parents=True); (self.workspace / 'module.R4MF').write_text('fixture')
        (self.workspace / 'main.zig').write_text('uncommitted source')
        db = connect(self.root)
        with db: db.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
            (self.id, 'fixture', '', 'Zig', 'terminal', 'FIXTURE', None, '{}', now(), now(), 1, 'ready'))
        db.close(); self.store = Jobs(self.root, self.root / 'R4OS', self.id)

    def tearDown(self): self.store.close(); self.temp.cleanup()

    def input(self): return {'requestId': str(uuid.uuid4()), 'projectRevision': 1, 'settingsRevision': 1}

    def test_idempotency_and_active_admission_survive_reopen(self):
        data = self.input(); job, fresh = self.store.admit('build', data); self.assertTrue(fresh)
        self.store.close(); self.store = Jobs(self.root, self.root / 'R4OS', self.id)
        repeated, fresh = self.store.admit('build', data)
        self.assertFalse(fresh); self.assertEqual(job['id'], repeated['id'])
        with self.assertRaises(DevelopmentFault): self.store.admit('build', self.input())
        with self.assertRaises(DevelopmentFault): self.store.admit('build', {**data, 'settingsRevision': 2})
        self.store.update(job['id'], 'failed', error='fixture')
        self.assertIsNone(self.store.get(job['id'])['artifactId'])
        next_job, fresh = self.store.admit('build', self.input()); self.assertTrue(fresh)
        self.assertNotEqual(next_job['id'], job['id'])

    def test_snapshot_keeps_uncommitted_source_and_rejects_links(self):
        (self.workspace / 'zig-out').mkdir(); (self.workspace / 'zig-out/STALE.R4X').write_text('stale')
        (self.workspace / 'empty-resources').mkdir()
        job, _ = self.store.admit('build', self.input()); source, path = capture(self.store, job)
        self.assertEqual((path / 'main.zig').read_text(), 'uncommitted source')
        self.assertFalse((path / 'zig-out').exists())
        self.assertTrue((path / 'empty-resources').is_dir())
        (self.workspace / 'main.zig').write_text('later edit')
        self.assertEqual((path / 'main.zig').read_text(), 'uncommitted source')
        self.assertEqual(len(source['files']), 2)
        self.store.update(job['id'], 'completed')
        for kind in ('symlink', 'hardlink'):
            linked = self.workspace / 'linked'
            if kind == 'symlink': linked.symlink_to('/etc/passwd')
            else: os.link(self.workspace / 'main.zig', linked)
            job, _ = self.store.admit('build', self.input())
            with self.assertRaises(DevelopmentFault): capture(self.store, job)
            self.store.update(job['id'], 'failed'); linked.unlink()

    def test_project_scope_and_bounded_output_are_enforced(self):
        job, _ = self.store.admit('build', self.input())
        self.store.evidence(job['id']).joinpath('output.log').write_bytes(b'x' * 100000)
        page = self.store.page(job['id'], 65000)
        self.assertEqual(page['nextOffset'], 100000)
        self.assertEqual(len(page['output']), 35000)
        log = self.store.evidence(job['id']).joinpath('output.log')
        log.write_bytes(b'x' * 65535 + '🦀end'.encode())
        first = self.store.page(job['id'])
        second = self.store.page(job['id'], first['nextOffset'])
        self.assertEqual(first['output'] + second['output'], 'x' * 65535 + '🦀end')
        with self.assertRaises(DevelopmentFault): self.store.get(str(uuid.uuid4()))
        with self.assertRaises(DevelopmentFault): self.store.page(job['id'], -1)
        with self.assertRaises(DevelopmentFault): self.store.artifact(str(uuid.uuid4()))

    def test_artifact_consumption_rejects_missing_or_modified_files(self):
        job, _ = self.store.admit('build', self.input())
        artifact_id = str(uuid.uuid4()); root = self.store.root / 'Artifacts' / artifact_id; root.mkdir(parents=True)
        binary = root / 'TEST.R4X'; binary.write_bytes(b'fixture')
        proof = root / 'build-proof.json'; save(proof, {'status': 'success'})
        files = [{'path': binary.name, 'bytes': 7, 'sha256': digest(binary)}]
        record = {'id': artifact_id, 'buildId': job['id'], 'files': files, 'packageSha256': hash_value(files),
                  'buildProof': {'bytes': proof.stat().st_size, 'sha256': digest(proof)}}
        save(root / 'artifact.json', record)
        with self.store.db: self.store.db.execute('INSERT INTO artifacts VALUES(?,?,?)', (artifact_id, job['id'], encode(record)))
        with self.assertRaises(DevelopmentFault): self.store.artifact(artifact_id)

        self.store.update(job['id'], 'completed', artifactId=artifact_id)
        self.assertEqual(self.store.artifact(artifact_id), record)
        binary.write_bytes(b'modified')
        with self.assertRaises(DevelopmentFault): self.store.artifact(artifact_id)
        binary.unlink()
        with self.assertRaises(DevelopmentFault): self.store.artifact(artifact_id)

    def test_project_reassignment_waits_for_its_guest_job(self):
        # Use a complete local receipt; the separate SDK tests qualify containers.
        build, _ = self.store.admit('build', self.input()); artifact_id = str(uuid.uuid4())
        root = self.store.root / 'Artifacts' / artifact_id; root.mkdir(parents=True)
        binary = root / 'TEST.R4X'; binary.write_bytes(b'fixture'); save(root / 'build-proof.json', {'status': 'success'})
        proof = root / 'build-proof.json'; files = [{'path': binary.name, 'bytes': 7, 'sha256': digest(binary)}]
        record = {'id': artifact_id, 'buildId': build['id'], 'files': files, 'pins': {},
            'packageSha256': hash_value(files), 'buildProof': {'bytes': proof.stat().st_size, 'sha256': digest(proof)}}
        save(root / 'artifact.json', record)
        with self.store.db: self.store.db.execute('INSERT INTO artifacts VALUES(?,?,?)', (artifact_id, build['id'], encode(record)))
        self.store.update(build['id'], 'completed', artifactId=artifact_id)
        deploy, _ = self.store.admit('deploy', {**self.input(), 'artifactId': artifact_id})
        vm_id = str(uuid.uuid4()); path = self.root / 'R4OS/Instances' / vm_id; path.mkdir(parents=True)
        save(path / 'vm.json', {'id': vm_id})
        db = connect(self.root)
        try:
            with self.assertRaises(ProjectFault):
                project_operation(db, {'operation': 'update', 'id': self.id, 'input': {'revision': 1, 'vmId': vm_id}}, self.root / 'R4OS')
        finally: db.rollback(); db.close()
        self.store.update(deploy['id'], 'failed')
        db = connect(self.root)
        try:
            result = project_operation(db, {'operation': 'update', 'id': self.id, 'input': {'revision': 1, 'vmId': vm_id}}, self.root / 'R4OS')
            self.assertEqual(result['vmId'], vm_id)
        finally: db.close()


if __name__ == '__main__': unittest.main()
