"""Real catalog/publication/settings/delete; template and SDK are controlled fixtures."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

import create
import delete
from store import connect, operation, ProjectFault
from remote_binding import exists, REMOTE_JOBS_APPLICATION_ID


class RemoteBindings(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)
        self.projects = self.root / 'Projects'; self.r4os = self.root / 'R4OS'; self.vm = str(uuid.uuid4())
        path = self.r4os / 'Instances' / self.vm / 'vm.json'; path.parent.mkdir(parents=True); path.write_text(json.dumps({'id': self.vm, 'name': 'Own VM metadata fixture'}))
        self.vm_bytes = path.read_bytes()
        self.hosts = [self.remote('create', input={'requestId': str(uuid.uuid4()), 'name': name, 'address': '127.0.0.1'}) for name in ('Own Remote A', 'Own Remote B')]
        self.context = {'revision': 'a'*64, 'templateRevision': 'b'*64, 'pins': {'sdk': {'revision': 'c'*40}, 'contract': {'revision': 'd'*40}, 'zig': {'version': 'fixture'}}}
        def render(context, source, data):
            source.mkdir(parents=True); (source / 'module.R4MF').write_text('Own controlled template fixture\n')
        for item in [patch('create.profile', return_value=self.context), patch('toolset.combination', return_value={'supported': True}), patch('create.render', side_effect=render)]: item.start(); self.addCleanup(item.stop)

    def remote(self, name, **extra):
        script = Path(__file__).resolve().parents[1] / 'remote-hosts/cli.py'
        result = subprocess.run([sys.executable, '-B', str(script), str(self.root / 'RemoteHosts')], input=json.dumps({'operation': name, **extra}), capture_output=True, text=True, check=False)
        value = json.loads(result.stdout)
        if 'error' in value: raise ProjectFault(value['error'], value['code'])
        return value['result']

    def new(self, vm=None, host=None):
        data = {'requestId': str(uuid.uuid4()), 'name': 'Own fixture project', 'description': '', 'language': 'Zig', 'template': 'terminal',
                'vmId': vm, 'remoteHostId': host, 'guestFormats': [], 'optionsRevision': self.context['revision']}
        with closing(connect(self.projects)) as db: return create.create(db, self.projects, self.r4os, data)

    def change(self, project, **input):
        with closing(connect(self.projects)) as db:
            return operation(db, {'operation': 'update', 'id': project['id'], 'input': {'revision': project['revision'], **input}}, self.r4os)

    def test_legacy_read_and_four_combinations_preserve_sources_vm_pins_and_portable_metadata(self):
        legacy = self.new()
        with closing(connect(self.projects)) as db: self.assertFalse(exists(db))
        before = (self.projects / 'Projects.sqlite').read_bytes()
        with closing(connect(self.projects)) as db:
            current = operation(db, {'operation': 'get', 'id': legacy['id']}, self.r4os); self.assertIsNone(current['remoteHostId']); self.assertFalse(exists(db))
        self.assertEqual((self.projects / 'Projects.sqlite').read_bytes(), before)
        for vm, host in ((self.vm, None), (None, self.hosts[0]['id']), (self.vm, self.hosts[0]['id'])):
            project = self.new(vm, host); self.assertEqual((project['vmId'], project['remoteHostId']), (vm, host))
            self.assertEqual(project['pins'], self.context['pins'])
            portable = (self.projects / project['id'] / 'Workspace/.r4os-studio/project.json').read_text()
            self.assertNotIn('remoteHostId', portable); self.assertNotIn('vmId', portable)
            self.assertNotIn(self.hosts[0]['id'], portable)
        self.assertEqual((self.r4os / 'Instances' / self.vm / 'vm.json').read_bytes(), self.vm_bytes)

    def test_shared_binding_rename_missing_host_validation_and_confirmed_project_delete(self):
        first = self.new(self.vm, self.hosts[0]['id']); second = self.new(None, self.hosts[0]['id'])
        renamed = self.remote('update', id=self.hosts[0]['id'], input={'requestId': str(uuid.uuid4()), 'revision': 1, 'name': 'Renamed remote'})
        with self.assertRaises(ProjectFault): self.remote('remove', id=renamed['id'], input={'requestId': str(uuid.uuid4()), 'revision': renamed['revision'], 'confirm': True})
        with self.assertRaises(ProjectFault): self.change(first, remoteHostId=str(uuid.uuid4()))
        updated = self.change(first, remoteHostId=self.hosts[1]['id'])
        self.assertEqual(updated['vmId'], self.vm); self.assertEqual(updated['pins'], first['pins']); self.assertEqual(updated['moduleName'], first['moduleName'])
        with self.assertRaises(ProjectFault): self.change(first, remoteHostId=None)
        with patch.object(delete, 'AGENT_RUNTIME', self.root / 'agent-runtime'), patch.object(delete, 'DEVELOPMENT_RUNTIME', self.root / 'development-runtime'):
            self.assertTrue(delete.delete(self.projects, second['id'], {'revision': second['revision'], 'confirm': True}, {'agents': True, 'development': True})['deleted'])
        self.assertEqual(self.remote('get', id=renamed['id']), renamed)
        self.assertTrue((self.projects / first['id'] / 'Workspace/module.R4MF').exists())
        self.assertEqual((self.r4os / 'Instances' / self.vm / 'vm.json').read_bytes(), self.vm_bytes)

    def test_unknown_remote_job_blocks_reassignment_and_project_deletion(self):
        project = self.new(None, self.hosts[0]['id']); path = self.projects / project['id'] / 'RemoteHosts/Jobs.sqlite'; path.parent.mkdir()
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript(f"CREATE TABLE jobs(state TEXT,payload TEXT); INSERT INTO jobs VALUES('unknown','{{}}'); PRAGMA user_version=1; PRAGMA application_id={REMOTE_JOBS_APPLICATION_ID};")
        with self.assertRaises(ProjectFault): self.change(project, remoteHostId=self.hosts[1]['id'])
        with self.assertRaises(ProjectFault): delete.delete(self.projects, project['id'], {'revision': project['revision'], 'confirm': True}, {'agents': True, 'development': True})
        with closing(sqlite3.connect(path)) as db, db: db.execute("UPDATE jobs SET state='completed'")
        self.assertEqual(self.change(project, remoteHostId=None)['remoteHostId'], None)

    def test_reference_lease_works_with_the_global_catalog_mounted_readonly(self):
        self.new(None, self.hosts[0]['id'])
        source = Path(__file__).resolve().parent
        script = "from pathlib import Path\nimport sys\nsys.path.insert(0,sys.argv[1])\nfrom remote_binding import hold\nwith hold(Path(sys.argv[2]),sys.argv[3]):print('read-only reference lease confirmed')\n"
        result = subprocess.run(['/usr/bin/bwrap', '--die-with-parent', '--unshare-net', '--ro-bind', '/', '/', '--bind', str(self.projects), str(self.projects),
                                 '--chdir', str(self.root), '--', sys.executable, '-B', '-c', script, str(source), str(self.projects), self.hosts[0]['id']], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), 'read-only reference lease confirmed')
