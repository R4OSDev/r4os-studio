from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import uuid

import delete as deletion
from project_use import acquire
from store import connect, operation, ProjectFault


class DeleteProject(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name); self.projects = self.root / 'Projects'
        self.id, self.run, self.job, self.lease = [str(uuid.uuid4()) for _ in range(4)]
        self.request = str(uuid.uuid4()); self.input = {'requestId': self.request, 'name': 'Fixture'}
        self.fingerprint = hashlib.sha256(json.dumps({'name': 'Fixture'}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        with closing(connect(self.projects)) as db, db:
            db.execute("INSERT INTO projects VALUES (?,?,'','Zig','terminal',?,NULL,'{}','now','now',1,'ready')", (self.id, 'Fixture', 'fixture'))
            db.execute("INSERT INTO requests VALUES (?,?,?,'complete','{}',NULL)", (self.request, self.fingerprint, self.id))
        self.project = self.projects / self.id
        (self.project / 'Workspace/nested').mkdir(parents=True)
        (self.project / 'Workspace/nested/ü.txt').write_text('project source')
        self.foreign = self.root / 'Foreign'; self.foreign.mkdir(); (self.foreign / 'keep').write_text('must survive')
        (self.project / 'Workspace/external').symlink_to(self.foreign, target_is_directory=True)
        (self.projects / '.studio').mkdir(exist_ok=True)
        (self.projects / '.studio/Settings.sqlite').write_text('global settings must survive')
        self.agent_runtime = self.root / 'run-agents'; self.dev_runtime = self.root / 'run-development'
        self.patches = [patch.object(deletion, 'AGENT_RUNTIME', self.agent_runtime), patch.object(deletion, 'DEVELOPMENT_RUNTIME', self.dev_runtime)]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in self.patches: p.stop()
        self.temp.cleanup()

    def records(self):
        path = self.project / 'Sessions/Sessions.sqlite'; path.parent.mkdir()
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript('CREATE TABLE sessions(id TEXT); CREATE TABLE runs(id TEXT,busy INTEGER); PRAGMA user_version=1;')
            db.execute('INSERT INTO sessions VALUES (?)', (str(uuid.uuid4()),)); db.execute('INSERT INTO runs VALUES (?,0)', (self.run,))
        path = self.project / 'Development/Development.sqlite'; path.parent.mkdir()
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript('CREATE TABLE jobs(id TEXT,kind TEXT,state TEXT,busy INTEGER,payload TEXT); PRAGMA user_version=1;')
            db.execute("INSERT INTO jobs VALUES (?,'build','completed',0,'{}')", (self.job,))
        self.json(self.projects / '.studio/agents' / self.run / 'worker.json', {'projectId': self.id, 'runId': self.run})
        self.json(self.projects / '.studio/development' / self.job / 'worker.json', {'projectId': self.id, 'jobId': self.job, 'kind': 'build'})
        self.json(self.projects / '.studio/development/leases' / (self.lease + '.json'), {'scope': {'projectId': self.id}, 'closedAt': 'now'})
        self.json(self.projects / '.studio/development/Forwards' / (self.lease + '.json'), {'scope': {'projectId': self.id}, 'state': 'closed'})
        self.json(self.projects / '.studio/development/Unconfirmed/Resolved' / (self.job + '.json'), {'projectId': self.id})
        self.json(self.agent_runtime / self.run / 'receipt.json', {})
        self.json(self.dev_runtime / 'Jobs' / self.job / 'receipt.json', {})
        self.json(self.dev_runtime / 'auth' / self.lease / 'private.json', {})

    @staticmethod
    def json(path, value):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value))

    def delete(self, **input):
        return deletion.delete(self.projects, self.id, {'revision': 1, 'confirm': True, **input}, {'agents': True, 'development': True})

    def test_removes_content_and_records_without_following_links_or_recreating(self):
        self.records(); result = self.delete(); self.assertTrue(result['deleted']); self.assertFalse(self.project.exists())
        for p in [self.projects / '.studio/agents' / self.run, self.projects / '.studio/development' / self.job,
                  self.agent_runtime / self.run, self.dev_runtime / 'auth' / self.lease]: self.assertFalse(p.exists())
        self.assertEqual((self.foreign / 'keep').read_text(), 'must survive')
        self.assertEqual((self.projects / '.studio/Settings.sqlite').read_text(), 'global settings must survive')
        self.assertEqual(self.delete(), result)
        with closing(connect(self.projects)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM projects').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM requests').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM project_deletions').fetchone()[0], 0)
            from create import create
            with self.assertRaises(ProjectFault) as caught: create(db, self.projects, self.root, self.input)
            self.assertEqual(caught.exception.code, 410)

    def test_refuses_busy_locked_stale_foreign_and_unconfirmed_targets(self):
        self.records()
        for data in ({'confirm': False}, {'revision': 2}):
            with self.assertRaises(ProjectFault): self.delete(**data)
        with acquire(self.projects, self.id):
            with self.assertRaises(ProjectFault): self.delete()
        with closing(sqlite3.connect(self.project / 'Sessions/Sessions.sqlite')) as db, db: db.execute('UPDATE runs SET busy=1')
        with self.assertRaises(ProjectFault): self.delete()
        with closing(sqlite3.connect(self.project / 'Sessions/Sessions.sqlite')) as db, db: db.execute('UPDATE runs SET busy=0')
        with self.assertRaises(ProjectFault): deletion.delete(self.projects, self.id, {'revision': 1, 'confirm': True})
        self.json(self.projects / '.studio/agents' / self.run / 'worker.json', {'projectId': str(uuid.uuid4()), 'runId': self.run})
        with self.assertRaises(ProjectFault): self.delete()
        self.json(self.projects / '.studio/agents' / self.run / 'worker.json', {'projectId': self.id, 'runId': self.run})
        self.json(self.projects / '.studio/development/Unconfirmed' / (str(uuid.uuid4()) + '.json'), {'jobId': self.job})
        with self.assertRaises(ProjectFault): self.delete()
        self.assertTrue(self.project.exists()); self.assertEqual((self.foreign / 'keep').read_text(), 'must survive')
        with closing(connect(self.projects)) as db: self.assertEqual(db.execute('SELECT state FROM projects').fetchone()[0], 'ready')

    def test_interruption_resumes_confirmed_deletion_and_keeps_pending_action_visible(self):
        self.records(); actual = deletion.remove
        def fail(path):
            if path == self.projects / '.studio/agents' / self.run: raise OSError('injected interruption')
            return actual(path)
        with patch.object(deletion, 'remove', side_effect=fail):
            with self.assertRaises(OSError): self.delete()
        self.assertFalse(self.project.exists())
        with closing(connect(self.projects)) as db:
            self.assertTrue(operation(db, {'operation': 'list'}, self.root)[0]['deleting'])
            with self.assertRaises(ProjectFault): operation(db, {'operation': 'get', 'id': self.id}, self.root)
            self.assertTrue(operation(db, {'operation': 'get_settings', 'id': self.id}, self.root)['deleting'])
        self.assertEqual(deletion.recover(self.projects), [{'id': self.id, 'deleted': True}])
        self.assertEqual((self.foreign / 'keep').read_text(), 'must survive')


if __name__ == '__main__': unittest.main()
