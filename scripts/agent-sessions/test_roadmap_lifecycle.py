"""Project lifetime and actual isolated backup/restore; no inference or user data."""
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import unittest
from unittest.mock import patch
import uuid
import zipfile
from zoneinfo import ZoneInfo

import test_finalize_tools as fixtures
from store import connect, operation, ProjectFault
import delete as deletion
from project_use import acquire

sys.path.insert(1, str(Path(__file__).resolve().parents[1] / 'project-roadmaps'))
import inspect_restore
from cli import operation as roadmap


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()}


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.FinalizeToolsTest.setUp
    tearDown = fixtures.FinalizeToolsTest.tearDown
    open = fixtures.FinalizeToolsTest.open
    start = fixtures.FinalizeToolsTest.start
    finish = fixtures.FinalizeToolsTest.finish
    call = fixtures.FinalizeToolsTest.call
    good = fixtures.FinalizeToolsTest.good
    initialize = fixtures.FinalizeToolsTest.initialize
    prepare = fixtures.FinalizeToolsTest.prepare
    ready = fixtures.FinalizeToolsTest.ready

    def close_workers(self):
        for worker in self.workers:
            self.finish(worker); worker.store.close()
        self.workers.clear()

    async def test_rename_session_removal_and_confirmed_project_deletion_are_scoped(self):
        self.data['text'] = 'Roadmap aufräumen.'
        worker = self.start(); initial = await self.initialize(worker)
        verified, final = await self.ready(worker, initial)
        await self.good(worker, 'cleanup_roadmap', final)
        project = self.projects / self.pid; before = hashes(project / 'Roadmap')
        with closing(connect(self.projects)) as db:
            old = operation(db, {'operation': 'get', 'id': self.pid}, self.r4os)
            renamed = operation(db, {'operation': 'update', 'id': self.pid, 'input': {'revision': old['revision'], 'name': 'Renamed project'}}, self.r4os)
        for key in ('id', 'moduleName', 'pins', 'language'): self.assertEqual(renamed[key], old[key])
        self.assertEqual(hashes(project / 'Roadmap'), before)
        # Removal of an unused private session (no new public deletion feature)
        # cannot own or cascade into the project's common roadmap.
        sid = str(uuid.uuid4()); row = worker.store.row(self.sid)
        with worker.store.db:
            worker.store.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,NULL,1,'now','now')", (sid, self.pid, 'Unused', row['settings'], row['engine']))
            worker.store.db.execute('DELETE FROM sessions WHERE id=?', (sid,))
        self.assertEqual((await self.good(worker, 'read_roadmap', {'view': 'current'}))['entity']['number'], '0.2.X')
        other = str(uuid.uuid4()); vm = self.root / 'R4OS/Instances/own-vm/vm.json'
        vm.parent.mkdir(parents=True); vm.write_text('own untouched VM fixture')
        with closing(connect(self.projects)) as db, db:
            db.execute("INSERT INTO projects VALUES (?,?,'','C','terminal',?,NULL,'{}','now','now',1,'ready')", (other, 'Other project', 'other'))
        (self.projects / other / 'Workspace').mkdir(parents=True)
        (self.projects / other / 'Workspace/module.R4MF').write_text('Own second project fixture\n')
        roadmap(self.projects, {'operation': 'initialize', 'projectId': other, 'requestId': str(uuid.uuid4())})
        foreign = hashes(self.projects / other)
        (project / 'Roadmap/foreign').symlink_to(self.projects / other / 'Roadmap', target_is_directory=True)
        def remove(): return deletion.delete(self.projects, self.pid, {'revision': renamed['revision'], 'confirm': True}, {'agents': True, 'development': True})
        with patch.object(deletion, 'AGENT_RUNTIME', self.root / 'run-agents'), patch.object(deletion, 'DEVELOPMENT_RUNTIME', self.root / 'run-development'), patch.object(deletion, 'worker_check'):
            with self.assertRaises(ProjectFault): remove()
            self.close_workers()
            with acquire(self.projects, self.pid):
                with self.assertRaises(ProjectFault): remove()
            self.assertTrue(remove()['deleted'])
        self.assertFalse(project.exists()); self.assertEqual(hashes(self.projects / other), foreign)
        self.assertEqual(vm.read_text(), 'own untouched VM fixture')

    async def test_existing_backup_covers_wal_journal_docs_and_reports_cross_file_restore_drift(self):
        # Use the production backup/restore implementation with an isolated
        # seven-source root and explicit synthetic mount, never the real timer.
        sys.path.insert(1, str(Path(__file__).resolve().parents[3] / 'Tools/Backup'))
        import backup
        from restore import restore
        self.data['text'] = 'Please clean up the roadmap.'
        worker = self.start(); initial = await self.initialize(worker)
        source = self.projects / self.pid / 'Workspace'; docs = source / 'Docs'; docs.mkdir()
        knowledge = docs / 'Decision.md'; knowledge.write_text('Durable decision\n')
        sha = hashlib.sha256(knowledge.read_bytes()).hexdigest(); args = self.prepare(initial)
        prepared = await self.good(worker, 'cleanup_roadmap', args)
        verified = await self.good(worker, 'cleanup_roadmap', {**args, 'workflowId': prepared['workflowId'], 'requestId': str(uuid.uuid4()),
            'documents': [{'path': 'Docs/Decision.md', 'expectedSha256': sha, 'sha256': sha}], 'documentationSummary': 'Reviewed and preserved this durable project decision.'})
        self.close_workers()
        root = self.root / 'backup-root'; root.mkdir()
        for name in backup.SOURCES:
            p = root / name
            if name == 'AGENTS.md': p.write_text('Synthetic host configuration')
            else: p.mkdir(parents=True, exist_ok=True)
        copied = root / 'App/Data/Projects'; shutil.copytree(self.projects, copied, dirs_exist_ok=True)
        for name in ('Images/own/disk.img', 'Instances/own/disk.qcow2'):
            p = root / 'App/Data/R4OS' / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('excluded own VM fixture')
        database = copied / self.pid / 'Roadmap/Roadmap.sqlite'
        writer = sqlite3.connect(database); writer.execute('PRAGMA journal_mode=WAL'); writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute("UPDATE roadmap SET notes='Committed live-WAL project notes'"); writer.commit()
        self.assertTrue(Path(str(database) + '-wal').exists())
        paths = backup.Paths(root, self.root / 'mount', self.root / 'mount/backup', self.root / 'backup-state', self.root / 'backup.lock')
        paths.mount.mkdir(); original = backup.stable_copy; drifted = []
        def change_after_database(parent, name, relative, target):
            result = original(parent, name, relative, target)
            if relative == f'App/Data/Projects/{self.pid}/Roadmap/Roadmap.sqlite':
                p = copied / self.pid / 'Workspace/Docs/Decision.md'; p.write_text('Changed after the database snapshot\n'); drifted.append(True)
            return result
        try:
            with patch.object(backup, 'stable_copy', side_effect=change_after_database):
                result = backup.run(paths, lambda _p: ('own-fixture-mount',), datetime(2026, 10, 27, 4, tzinfo=ZoneInfo('Europe/Berlin')))
        finally: writer.close()
        self.assertEqual(drifted, [True]); archive = paths.destination / result['archive']
        with zipfile.ZipFile(archive) as z:
            manifest = [json.loads(line) for line in z.read(backup.MANIFEST).splitlines()]
            self.assertEqual(manifest[0]['sources'], list(backup.SOURCES))
            entry = next(m for m in manifest if m.get('path') == f'App/Data/Projects/{self.pid}/Roadmap/Roadmap.sqlite')
            self.assertTrue(entry['sqliteOnlineBackup'])
            self.assertFalse(any(n.endswith(('-wal', '-shm', '-journal')) or '/R4OS/Images/' in n or '/R4OS/Instances/' in n for n in z.namelist()))
        restored = self.root / 'isolated-restore'; restore(archive, restored)
        before = hashes(restored); state = inspect_restore.inspect(restored / 'App/Data/Projects', self.pid)
        self.assertEqual(hashes(restored), before); self.assertTrue(state['readOnly']); self.assertFalse(state['activated'])
        self.assertEqual(state['currentNumber'], '0.1.X'); self.assertTrue(state['pendingReconciliationRequired'])
        receipt = state['workflows'][0]
        self.assertEqual(receipt['workflowId'], verified['workflowId']); self.assertEqual(receipt['phase'], 'documents_verified')
        self.assertTrue(receipt['archiveMatchesReceipt']); self.assertTrue(receipt['originalUserEvidenceMatches'])
        self.assertFalse(receipt['workspaceIdentityMatches']); self.assertFalse(receipt['documentsMatchReceipts'])
        with closing(sqlite3.connect(restored / 'App/Data/Projects' / self.pid / 'Roadmap/Roadmap.sqlite')) as db:
            self.assertEqual(db.execute('SELECT notes FROM roadmap').fetchone()[0], 'Committed live-WAL project notes')
        with self.assertRaises(backup.BackupError): restore(archive, restored)
        # Original active fixture and its confirmed decision were never changed.
        self.assertEqual(knowledge.read_text(), 'Durable decision\n')
