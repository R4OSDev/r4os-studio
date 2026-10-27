"""Isolated project/SQLite contract checks; never opens the installed data root."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'projects'))
from store import connect
from project_use import acquire
from cli import operation
from storage import connection, RoadmapFault


class RoadmapStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='studio-roadmap-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'Projects'
        self.ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        with closing(connect(self.root)) as db, db:
            for index, identity in enumerate(self.ids):
                (self.root / identity / 'Workspace').mkdir(parents=True)
                db.execute('''INSERT INTO projects(id,name,description,language,template,module_name,pins,
                    created_at,updated_at,state) VALUES(?,?,'','Zig','desktop',?,'{}','now','now','ready')''',
                           (identity, f'Project {index}', f'TEST{index}'))

    def call(self, operation_name='read', identity=None):
        return operation(self.root, {'operation': operation_name, 'projectId': identity or self.ids[0]})

    def process(self, operation_name='read', identity=None):
        child = subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('cli.py')), str(self.root)],
                               input=json.dumps({'operation': operation_name, 'projectId': identity or self.ids[0]}),
                               text=True, capture_output=True, check=False, timeout=10)
        return json.loads(child.stdout)

    def test_explicit_initialization_shared_between_processes_and_project_isolation(self):
        self.assertFalse(self.call()['exists'])
        self.assertFalse((self.root / self.ids[0] / 'Roadmap').exists())
        first = self.call('initialize')['roadmap']
        self.assertEqual(self.call('initialize')['roadmap'], first)
        self.assertEqual(self.process()['result']['roadmap'], first)
        self.assertEqual(self.process()['result']['roadmap'], first)
        self.assertFalse(self.call(identity=self.ids[1])['exists'])
        second = self.call('initialize', self.ids[1])['roadmap']
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(first['versions'][0]['number'], '0.1.X')
        self.assertEqual(first['versions'][0]['title'], 'New')
        self.assertEqual(first['versions'][0]['status'], 'open')
        self.assertEqual(first['versions'][0]['subversions'], [])
        self.assertEqual(first['currentVersionId'], first['versions'][0]['id'])

    def test_all_levels_keep_notes_and_separate_status_models(self):
        first = self.call('initialize')['roadmap']
        version_id, sub_id, task_id, acceptance_id = first['currentVersionId'], *[str(uuid.uuid4()) for _ in range(3)]
        with connection(self.root, self.ids[0]) as db:
            db.execute("UPDATE roadmap SET notes='Project notes',description='Shared description'")
            db.execute("UPDATE versions SET vision='Vision',notes='Version notes'")
            db.execute('''INSERT INTO subversions(id,version_id,patch,title,description,notes,position,created_at,updated_at)
                          VALUES(?,?,1,'First','Description','Subversion notes',0,'now','now')''', (sub_id, version_id))
            for table, identity in [('tasks', task_id), ('acceptances', acceptance_id)]:
                db.execute('INSERT INTO ' + table + '''(id,subversion_id,description,notes,status,position,created_at,updated_at)
                           VALUES(?,?,'Work','Notes on this item','done',0,'now','now')''', (identity, sub_id))
            db.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE versions SET status='done'")
            db.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE tasks SET status='complete'")
            db.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO tasks VALUES(?,'missing','No parent','','open',1,1,'now','now')", (str(uuid.uuid4()),))
            db.rollback()
        result = self.process()['result']['roadmap']
        self.assertEqual(result['notes'], 'Project notes')
        self.assertEqual(result['versions'][0]['vision'], 'Vision')
        sub = result['versions'][0]['subversions'][0]
        self.assertEqual(sub['number'], '0.1.1')
        self.assertEqual(sub['notes'], 'Subversion notes')
        self.assertEqual(sub['status'], 'open')  # Done items never complete a version.
        self.assertEqual(sub['tasks'][0]['id'], task_id)
        self.assertEqual(sub['acceptances'][0]['id'], acceptance_id)
        self.assertEqual(sub['acceptances'][0]['notes'], 'Notes on this item')

    def test_corrupt_unknown_and_wrong_project_databases_are_preserved(self):
        self.call('initialize')
        path = self.root / self.ids[0] / 'Roadmap/Roadmap.sqlite'
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('PRAGMA user_version=99')
        original = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(self.process('initialize')['code'], 503)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), original)
        path.write_bytes(b'not a SQLite database')
        self.assertEqual(self.process('initialize')['code'], 503)
        self.assertEqual(path.read_bytes(), b'not a SQLite database')
        target = self.root / self.ids[1] / 'Roadmap'
        target.mkdir()
        path.write_bytes(b'')
        self.assertEqual(self.process('initialize')['code'], 503)
        self.assertEqual(path.read_bytes(), b'')
        self.call('initialize', self.ids[1])
        path.write_bytes((target / 'Roadmap.sqlite').read_bytes())
        original = path.read_bytes()
        self.assertEqual(self.process()['code'], 503)
        self.assertEqual(path.read_bytes(), original)

    def test_concurrent_initialization_has_exactly_one_published_roadmap(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.process('initialize'), range(2)))
        successful = [x['result']['roadmap'] for x in results if 'result' in x]
        self.assertTrue(successful)
        for result in results:
            if 'error' in result:
                self.assertEqual(result['code'], 409)
        final = self.call('initialize')['roadmap']
        self.assertTrue(all(x == final for x in successful))
        self.assertEqual(len(final['versions']), 1)

    def test_links_invalid_identity_and_deletion_reservation_cannot_initialize(self):
        external = Path(self.temp.name) / 'outside'
        external.mkdir()
        (self.root / self.ids[0] / 'Roadmap').symlink_to(external, target_is_directory=True)
        self.assertEqual(self.process('initialize')['code'], 503)
        self.assertEqual(list(external.iterdir()), [])
        with self.assertRaises(RoadmapFault):
            self.call('initialize')
        self.assertEqual(self.process('initialize', '../outside')['code'], 400)
        with acquire(self.root, self.ids[1], exclusive=True):
            self.assertEqual(self.process('initialize', self.ids[1])['code'], 409)
        self.assertFalse((self.root / self.ids[1] / 'Roadmap').exists())


if __name__ == '__main__':
    unittest.main()
