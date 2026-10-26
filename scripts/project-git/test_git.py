"""Focused isolated adapter checks; no network, accounts or user project mutations."""
import json
import os
from pathlib import Path
import tempfile
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
        with patch.object(host, 'release', return_value='/test-release'), patch('host.subprocess.Popen', return_value=Process()):
            first = host.request(data); self.assertEqual(host.request(data)['id'], first['id'])
            with self.assertRaises(ProjectFault): host.request({**data, 'kind': 'check'})
        with self.assertRaises(ProjectFault): host.request({'operation': 'job', 'projectId': str(uuid.uuid4()), 'requestId': data['requestId']})
        restored = Coordinator(self.config, self.cfg)
        self.assertEqual(restored.request({'operation': 'job', 'projectId': self.identity, 'requestId': data['requestId']})['state'], 'unknown')
        with self.assertRaises(ProjectFault): restored.request({**data, 'requestId': str(uuid.uuid4())})


if __name__ == '__main__': unittest.main()
