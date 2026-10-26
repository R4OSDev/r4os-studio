"""Focused isolated adapter checks; no network, accounts or user project mutations."""
import json
import os
from pathlib import Path
import tempfile
import shutil
import unittest
from unittest.mock import patch
import uuid
from common import ProjectFault, branch, inventory, locks, save
from store import connect
from operations import Operations, reconcile
from host import Coordinator


class GitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='studio-git-test-')
        self.root = Path(self.temp.name); self.projects = self.root / 'Projects'; self.projects.mkdir()
        self.identity = str(uuid.uuid4()); self.source = self.projects / self.identity / 'Workspace'; self.source.mkdir(parents=True)
        (self.source / 'module.R4MF').write_text('test manifest\n')
        with connect(self.projects) as db:
            db.execute('INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                       (self.identity, 'Own Git QA', '', 'Zig', 'terminal', 'qa', None, '{}', 'now', 'now', 1, 'ready'))
        self.config = {'schema': 1, 'uid': os.getuid(), 'projects': str(self.projects), 'github': str(self.root / 'GitHub')}
        self.cfg = self.root / 'config.json'; save(self.cfg, self.config)
        self.jobs = self.projects / '.studio/github/Jobs'; self.jobs.mkdir(parents=True)

    def tearDown(self): self.temp.cleanup()

    def job(self, kind='initialize', data=None):
        identity = str(uuid.uuid4()); directory = self.jobs / identity; directory.mkdir()
        job = {'schema': 1, 'id': identity, 'projectId': self.identity, 'kind': kind, 'input': data or {}, 'phase': 'starting', 'state': 'queued', 'createdAt': 'now', 'updatedAt': 'now'}
        save(directory / 'job.json', job); return job

    def test_real_isolated_git_initialization_and_source_only_status(self):
        action = Operations(self.config, self.job())
        self.assertTrue(action.initialize()['initialized'])
        result = action.status()
        self.assertIsNone(result['head']); self.assertEqual(result['state'], 'not_connected')
        self.assertEqual(result['changes'][0]['path'], 'module.R4MF')
        self.assertFalse((self.source / '.git').exists())
        self.assertTrue(reconcile(self.config, self.job())['initialized'])

    def test_source_paths_links_and_cross_process_mutation_lock(self):
        for value in ('-a', 'a..b', 'a.lock', 'a/../b', 'a@{b', 'a b'):
            with self.assertRaises(ProjectFault): branch(value)
        self.assertEqual(branch('feature/one'), 'feature/one')
        (self.source / 'link').symlink_to('/etc/passwd')
        with self.assertRaises(ProjectFault): inventory(self.source)
        (self.source / 'link').unlink()
        from project_use import acquire
        lease = acquire(self.projects, self.identity, exclusive=False)
        try:
            with self.assertRaises(ProjectFault):
                with locks(self.projects, self.identity): pass
        finally: lease.close()

    def test_request_identity_recovery_and_cross_project_receipts(self):
        host = Coordinator(self.config, self.cfg)
        data = {'operation': 'submit', 'projectId': self.identity, 'requestId': str(uuid.uuid4()), 'kind': 'initialize', 'input': {}}
        class Process:
            pid = 1234
            def poll(self): return None
        with patch.object(host, 'release', return_value=str(Path(__file__).resolve().parents[2])), patch('host.subprocess.Popen', return_value=Process()):
            first = host.request(data); self.assertEqual(host.request(data)['id'], first['id'])
            with self.assertRaises(ProjectFault): host.request({**data, 'kind': 'check'})
        with self.assertRaises(ProjectFault): host.request({'operation': 'job', 'projectId': str(uuid.uuid4()), 'requestId': data['requestId']})
        restored = Coordinator(self.config, self.cfg)
        self.assertEqual(restored.request({'operation': 'job', 'projectId': self.identity, 'requestId': data['requestId']})['state'], 'unknown')
        with self.assertRaises(ProjectFault): restored.request({**data, 'requestId': str(uuid.uuid4())})

    def test_portable_metadata_retains_pins_without_local_identity_or_private_state(self):
        from git_metadata import create
        original = {'id': self.identity, 'name': 'Own QA', 'language': 'Rust', 'template': 'terminal', 'moduleName': 'QA',
                    'pins': {'sdk': {'revision': 'a' * 40, 'sha256': 'b' * 64}}, 'vmId': str(uuid.uuid4())}
        create(self.source, original)
        value = json.loads((self.source / '.r4os-studio/project.json').read_text())
        self.assertEqual(value['pins'], original['pins']); self.assertNotIn('id', value); self.assertNotIn('vmId', value)
        self.assertNotIn('Cargo.lock', (self.source / '.gitignore').read_text())

    def test_create_repository_retains_original_remote_identity_and_does_not_repeat_uncertain_create(self):
        data = {'connectionId': str(uuid.uuid4()), 'tokenRevision': 1, 'userId': 7, 'repositoryName': 'own-qa', 'private': True}
        class Api:
            created = False; calls = 0
            def __init__(self, *args, **kwargs): self.user = {'login': 'octocat', 'id': 7}; self.token = 'dummy'
            def assert_current(self): pass
            def repository(self, *args):
                if not self.created: raise ProjectFault('not found', 404)
                return {'id': 11, 'owner': 'octocat', 'name': 'own-qa', 'fullName': 'octocat/own-qa', 'url': 'https://github.com/octocat/own-qa', 'private': True, 'defaultBranch': 'main', 'archived': False, 'read': True, 'push': True}
            def request(self, *args): Api.created = True; Api.calls += 1; return {'id': 11, 'owner': {'id': 7}}
        job = self.job('create_repository', data)
        with patch('operations.GitHub', Api):
            result = Operations(self.config, job).execute(); self.assertEqual(result['binding']['repository']['id'], 11)
            self.assertEqual(reconcile(self.config, job)['binding']['repository']['id'], 11); self.assertEqual(Api.calls, 1)
        # A different project with a lost create response must retain its original intent.
        from common import storage
        base = storage(self.projects, self.identity); (base / 'binding.json').unlink(); (base / 'create-repository.json').unlink()
        class Organization(Api):
            created = False; endpoint = None
            def request(self, path, *args):
                if path == '/orgs/R4OSDev': return {'id': 99, 'login': 'R4OSDev'}
                Organization.created = True; Organization.endpoint = path
                return {'id': 12, 'owner': {'id': 99}}
            def repository(self, *args):
                if not self.created: raise ProjectFault('not found', 404)
                return {'id': 12, 'owner': 'R4OSDev', 'name': 'own-qa', 'fullName': 'R4OSDev/own-qa', 'defaultBranch': 'main'}
        with patch('operations.GitHub', Organization):
            value = Operations(self.config, self.job('create_repository', {**data, 'owner': 'R4OSDev'})).execute()
            self.assertEqual(Organization.endpoint, '/orgs/R4OSDev/repos'); self.assertEqual(value['binding']['repository']['owner'], 'R4OSDev')
        (base / 'binding.json').unlink(); (base / 'create-repository.json').unlink()
        class Lost(Api):
            created = False
            def request(self, *args): raise ProjectFault('lost response', 503)
        uncertain = self.job('create_repository', data)
        with patch('operations.GitHub', Lost):
            with self.assertRaises(ProjectFault): Operations(self.config, uncertain).execute()
            self.assertTrue(uncertain['effectPossible']); self.assertIsNone(reconcile(self.config, uncertain))
            with self.assertRaises(ProjectFault): Operations(self.config, self.job('create_repository', data)).execute()

    def test_materialize_real_git_history_and_reject_links(self):
        from trees import materialize
        action = Operations(self.config, self.job()); action.initialize()
        (self.source / 'Cargo.lock').write_text('keep lockfile\n')
        action.git.run('add', '--all')
        action.git.run('-c', 'user.name=Own QA', '-c', 'user.email=qa@example.invalid', 'commit', '--no-gpg-sign', '-m', 'Own source fixture')
        head = action.git.head(); target = self.root / 'materialized'; target.mkdir()
        materialize(action.git, head, target)
        self.assertEqual((target / 'Cargo.lock').read_text(), 'keep lockfile\n')
        self.assertFalse((target / '.git').exists())
        oid = action.git.text('hash-object', '-w', '--stdin', data=b'/etc/passwd')
        action.git.run('update-index', '--add', '--cacheinfo', '120000', oid, 'unsafe')
        tree = action.git.text('write-tree')
        unsafe = action.git.text('-c', 'user.name=Own QA', '-c', 'user.email=qa@example.invalid', 'commit-tree', tree, '-m', 'Unsafe fixture')
        other = self.root / 'rejected'; other.mkdir()
        with self.assertRaises(ProjectFault): materialize(action.git, unsafe, other)

    def test_import_retains_commit_and_portable_pins_with_new_uuid(self):
        from importing import prepare, reconcile as readback
        from git_metadata import create
        from git import Git
        action = Operations(self.config, self.job()); action.initialize()
        portable = {'language': 'Zig', 'template': 'terminal', 'moduleName': 'QA', 'pins': {'sdk': {'revision': 'a' * 40}}}
        create(self.source, portable)
        action.git.run('add', '--all'); action.git.run('-c', 'user.name=Own QA', '-c', 'user.email=qa@example.invalid', 'commit', '--no-gpg-sign', '-m', 'Import fixture')
        commit = action.git.head(); new_id = str(uuid.uuid4())
        class Api:
            def __init__(self, *args): self.user = {'id': 7, 'login': 'octocat'}; self.token = None
            def assert_current(self): pass
            def repository(self, *args): return {'id': 11, 'owner': 'octocat', 'name': 'own-qa', 'fullName': 'octocat/own-qa', 'defaultBranch': 'main'}
        class RemoteFixture(Git):
            def run(self, *args, **kwargs):
                if args[0] == 'ls-remote': return (commit + '\trefs/heads/main\n').encode(), 0
                if args[0] == 'fetch':
                    shutil.copytree(action.repo / 'objects', self.root / 'objects', dirs_exist_ok=True)
                    (self.root / 'FETCH_HEAD').write_text(commit + '\n'); return b'', 0
                return super().run(*args, **kwargs)
        job = self.job('import', {'connectionId': str(uuid.uuid4()), 'tokenRevision': 1, 'userId': 7, 'repository': {'id': 11, 'owner': 'octocat', 'name': 'own-qa'}, 'branch': 'main'})
        job['projectId'] = new_id
        with patch('importing.GitHub', Api), patch('importing.Git', RemoteFixture): result = prepare(self.config, job)
        value = result['import']; self.assertEqual(value['projectId'], new_id); self.assertNotEqual(new_id, self.identity)
        self.assertEqual(value['commit'], commit); self.assertEqual(value['metadata']['pins'], portable['pins'])
        self.assertFalse((self.projects / new_id).exists()); self.assertEqual(readback(self.config, job), result)


if __name__ == '__main__': unittest.main()
