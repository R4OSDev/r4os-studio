"""Actual backup/delete and out-of-step numeric receipts, never inference."""
import json
from pathlib import Path
import os
import shutil
import sqlite3
import sys
import unittest
from unittest.mock import patch
from stats_store import Source,Statistics,read,scope
from stats_lifecycle import preserve_pending,flush_pending
import test_runs as fixtures

class StatsLifecycle(unittest.TestCase):
    setUp=fixtures.Runs.setUp
    tearDown=fixtures.Runs.tearDown
    open=fixtures.Runs.open
    def test_older_aggregate_rebuild_uses_rotating_receipts_without_double_credit(self):
        with self.open() as store:
            source=Source(store);source.put(self.sid,'tokens',{'response':'first'},{'total':1});source.flush()
            archive=self.root/'older.sqlite';shutil.copy2(self.projects/'.studio/statistics/Statistics.sqlite',archive)
            for n in (2,3):source.put(self.sid,'tokens',{'response':str(n)},{'total':n})
            source.flush();shutil.copy2(archive,self.projects/'.studio/statistics/Statistics.sqlite')
            for _ in range(6):source.flush(1,True)
            self.assertEqual(read(self.projects)['tokens']['total'],'6')
            for _ in range(6):source.flush(1,True)
            self.assertEqual(read(self.projects)['tokens']['total'],'6')
    def test_same_original_response_with_later_capture_date_is_not_new_or_conflicting(self):
        with self.open() as store:
            value=Source(store).put(self.sid,'tokens',{'response':'original'},{'total':7});Source(store).flush()
        db=Statistics(self.projects,True)
        try:
            self.assertFalse(db.apply({**value,'at':'2099-01-01T00:00:00Z'}));self.assertEqual(db.read()['tokens']['total'],'7');self.assertEqual(db.db.execute('SELECT COUNT(*) FROM conflicts').fetchone()[0],0)
        finally:db.close()
    def test_session_deletion_keeps_project_lifetime_and_global_maximum(self):
        with self.open() as store:
            source=Source(store);source.put(self.sid,'tokens',{'response':'retained'},{'total':7});source.put(self.sid,'goal',{'play':'retained'},{'durationMs':9000,'uncertain':False});source.flush()
            with store.db:store.db.execute('DELETE FROM sessions WHERE id=?',(self.sid,))
            source.flush(include_acknowledged=True)
        self.assertEqual(read(self.projects)['tokens']['total'],'7');self.assertEqual(read(self.projects)['longestGoalMs'],9000)
        self.assertEqual(read(self.projects,'project:'+scope({'type':'project','id':self.pid}))['tokens']['total'],'7')
    def test_actual_project_delete_retains_only_pending_numbers_during_aggregate_outage(self):
        with self.open() as store:Source(store).put(self.sid,'tokens',{'response':'pending'},{'total':7,'input':5,'output':2})
        from contextlib import closing
        from store import connect
        from session_store import SessionStore,encode
        import uuid
        other,other_sid=str(uuid.uuid4()),str(uuid.uuid4())
        with closing(connect(self.projects)) as db,db:db.execute("INSERT INTO projects VALUES (?,?,'','C','terminal',?,NULL,'{}','now','now',1,'ready')",(other,'Foreign numerical fixture','foreign_numerical_fixture'))
        workspace=self.projects/other/'Workspace';workspace.mkdir(parents=True);(workspace/'module.R4MF').write_text('R4OS_MODULE_MANIFEST=2\n')
        with closing(SessionStore(self.projects,self.r4os,other)) as store:
            with store.db:store.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,NULL,1,'now','now')",(other_sid,other,'Own second fixture',encode(self.settings),encode({'profile':__import__('profile').LEGACY_PROFILE})))
            Source(store).put(other_sid,'tokens',{'response':'other-project'},{'total':20});Source(store).flush()
        import delete as deletion
        foreign=self.root/'foreign';foreign.write_text('preserve foreign content');(self.projects/self.pid/'foreign-link').symlink_to(foreign)
        with patch('stats_lifecycle.Source.flush',side_effect=OSError('owned aggregate unavailable')),patch.object(deletion,'AGENT_RUNTIME',self.root/'agent-runtime'),patch.object(deletion,'DEVELOPMENT_RUNTIME',self.root/'dev-runtime'),patch.object(deletion,'worker_check'):
            result=deletion.delete(self.projects,self.pid,{'revision':1,'confirm':True},{'agents':True,'development':True})
        self.assertTrue(result['deleted']);self.assertFalse((self.projects/self.pid).exists());self.assertEqual(foreign.read_text(),'preserve foreign content')
        pending=list((self.projects/'.studio/statistics/Pending').glob('*.json'));self.assertEqual(len(pending),1)
        self.assertNotIn(self.pid,pending[0].read_text());self.assertNotIn('Fixture',pending[0].read_text())
        self.assertTrue(read(self.projects)['coverage']['delayed']);flush_pending(self.projects)
        self.assertEqual(read(self.projects)['tokens']['total'],'27');self.assertEqual(read(self.projects,'project:'+scope({'type':'project','id':other}))['tokens']['total'],'20');self.assertTrue(workspace.exists());self.assertEqual(flush_pending(self.projects),0)
    @unittest.skipIf(os.getuid()!=0,'Existing backup source is root-readable.')
    def test_actual_backup_restore_central_and_source_reconcile_preserves_numbers(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from contextlib import closing
        from session_store import SessionStore
        sys.path.insert(1,str(Path(__file__).resolve().parents[3]/'Tools/Backup'))
        import backup
        from restore import restore
        with self.open() as store:
            source=Source(store);source.put(self.sid,'tokens',{'response':'backup'},{'total':9});source.put(self.sid,'goal',{'play':'backup'},{'durationMs':12345,'uncertain':False});source.flush()
        root=self.root/'backup-root';root.mkdir()
        for source in backup.SOURCES:
            path=root/source
            if source=='AGENTS.md':path.write_text('Owned statistics backup')
            else:path.mkdir(parents=True,exist_ok=True)
        shutil.copytree(self.projects,root/'App/Data/Projects',dirs_exist_ok=True)
        paths=backup.Paths(root,self.root/'mount',self.root/'mount/backup',self.root/'backup-state',self.root/'backup.lock');paths.mount.mkdir()
        result=backup.run(paths,lambda _:('owned-statistics-mount',),datetime(2026,10,28,4,tzinfo=ZoneInfo('Europe/Berlin')))
        restored=self.root/'restored';restore(paths.destination/result['archive'],restored)
        projects=restored/'App/Data/Projects';self.assertEqual(len(backup.SOURCES),7);self.assertFalse((restored/'App/Data/Skills').exists())
        with closing(SessionStore(projects,self.r4os,self.pid)) as store:Source(store).flush(include_acknowledged=True)
        self.assertEqual(read(projects)['tokens']['total'],'9');self.assertEqual(read(projects)['longestGoalMs'],12345)
