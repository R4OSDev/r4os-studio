"""Real SQLite/lifetime/conflict and namespace boundaries, no model or VM runs."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid
sys.path.insert(1,str(Path(__file__).resolve().parents[1]/'projects'))
from store import connect,ProjectFault
from project_use import acquire
from cli import operation
from board_store import connection

class Boards(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.projects=self.root/'Projects'
        self.pid,self.other=[str(uuid.uuid4()) for _ in range(2)]
        with closing(connect(self.projects)) as db,db:
            for ident in (self.pid,self.other):
                db.execute("INSERT INTO projects VALUES (?,?,'','C','terminal',?,NULL,'{}','now','now',1,'ready')",(ident,ident,'own_'+ident.replace('-','')))
                path=self.projects/ident/'Workspace';path.mkdir(parents=True);(path/'module.R4MF').write_text('Own fixture')
    def tearDown(self):self.temp.cleanup()
    def call(self,op='list',pid=None,**args):return operation(self.projects,{'operation':op,'projectId':pid or self.pid,**args})
    def create(self,name='Own board',revision=0,rid=None):return self.call('create',input={'requestId':rid or str(uuid.uuid4()),'expectedRevision':revision,'name':name})

    def test_read_does_not_initialize_and_concurrent_original_create_has_one_result(self):
        self.assertEqual(self.call()['boards'],[]);self.assertFalse((self.projects/self.pid/'Boards').exists())
        rid=str(uuid.uuid4())
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:self.create(rid=rid),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(len(self.call()['boards']),1)
        snapshot=self.call('get',boardId=results[0]['boardId'])
        self.assertEqual([r['title'] for r in snapshot['columns']],['To do','In progress','Done'])
        self.assertEqual(snapshot['cards'],[])
        with connection(self.projects,self.pid) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM requests').fetchone()[0],1)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_original_receipt_stale_revision_names_and_foreign_parents(self):
        first=self.create();bid=first['boardId']
        data={'requestId':str(uuid.uuid4()),'expectedRevision':1,'name':'Renamed'}
        self.call('update',boardId=bid,input=data)
        self.assertEqual(self.call('update',boardId=bid,input=data)['revision'],2)
        with self.assertRaises(ProjectFault):self.call('update',boardId=bid,input={**data,'requestId':str(uuid.uuid4())})
        self.assertEqual(self.call('receipt',requestId=first['requestId']),first)
        with self.assertRaises(ProjectFault):self.call('get',pid=self.other,boardId=bid)
        with self.assertRaises(sqlite3.IntegrityError):self.create('RENAMED',2)
        self.assertEqual(self.call()['boards'][0]['name'],'Renamed')

    def test_full_order_preserves_ids_and_rejects_incomplete_inventory(self):
        first=self.create();second=self.create('Second',1)
        data={'requestId':str(uuid.uuid4()),'expectedRevision':2,'ids':[second['boardId'],first['boardId']]}
        self.call('reorder',input=data)
        self.assertEqual([b['id'] for b in self.call()['boards']],data['ids'])
        with self.assertRaises(ProjectFault):self.call('reorder',input={**data,'requestId':str(uuid.uuid4()),'expectedRevision':3,'ids':[first['boardId']]})
        with self.assertRaises(ProjectFault):self.call('reorder',input={**data,'ids':list(reversed(data['ids']))})

    def test_column_card_label_and_checklist_parent_keys_are_enforced(self):
        first=self.create();second=self.create('Second',1)
        foreign_column=self.call('get',boardId=second['boardId'])['columns'][0]['id']
        with connection(self.projects,self.pid) as db:
            with self.assertRaises(sqlite3.IntegrityError),db:
                db.execute("INSERT INTO cards(id,board_id,column_id,title,position,created_at,updated_at) VALUES(?,?,?,'Foreign',0,'now','now')",(str(uuid.uuid4()),first['boardId'],foreign_column))
            self.assertFalse(db.execute('SELECT 1 FROM cards').fetchone())

    def test_corruption_unknown_schema_links_and_invalid_text_preserve_existing_bytes(self):
        self.create();path=self.projects/self.pid/'Boards/Boards.sqlite'
        with sqlite3.connect(path) as db:db.execute('PRAGMA user_version=999')
        before=path.read_bytes()
        with self.assertRaises(ProjectFault):self.call()
        self.assertEqual(path.read_bytes(),before)
        foreign=self.root/'foreign';foreign.mkdir();(foreign/'keep').write_text('keep')
        parent=self.projects/self.other/'Boards';parent.symlink_to(foreign,target_is_directory=True)
        with self.assertRaises(ProjectFault):self.call(pid=self.other)
        self.assertEqual((foreign/'keep').read_text(),'keep')

    def test_storage_limit_and_project_deletion_lifetime_do_not_replace_data(self):
        first=self.create()
        with patch('board_mutations.MAX_BOARDS',1):
            with self.assertRaises(ProjectFault):self.create('Beyond limit',1)
        self.assertEqual(self.call('receipt',requestId=first['requestId']),first)
        with acquire(self.projects,self.pid,exclusive=True):
            with self.assertRaises(ProjectFault):self.call()
        lock=self.projects/'.studio'/('workspace-'+self.pid+'.lock');lock.parent.mkdir(exist_ok=True)
        with lock.open('a') as held:
            fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(self.create('During agent work',1)['revision'],1)

    def test_future_feature_level_and_legacy_source_layout_are_preserved(self):
        self.create();path=self.projects/self.pid/'Boards/Boards.sqlite'
        with sqlite3.connect(path) as db:db.execute('UPDATE meta SET feature_level=99')
        before=path.read_bytes()
        with self.assertRaises(ProjectFault):self.call()
        self.assertEqual(path.read_bytes(),before)
        work=self.projects/self.other/'Workspace';work.rename(work.parent/'OwnLegacySources')
        with self.assertRaises(ProjectFault):self.call(pid=self.other)
        self.assertFalse((self.projects/self.other/'Boards').exists())

    def test_actual_terminal_and_native_namespaces_cannot_read_private_boards(self):
        self.create();private=self.projects/self.pid/'Boards/Boards.sqlite'
        sys.path.insert(1,str(Path(__file__).resolve().parents[1]/'agent-sessions'))
        from sandbox import Sandbox
        from profile import prepare,CODEX_SHA256
        work=self.projects/self.pid/'Workspace';cache=self.root/'own-cache';(cache/'global/p').mkdir(parents=True)
        run_cache=cache/'run';(run_cache/'home').mkdir(parents=True)
        worker=SimpleNamespace(store=SimpleNamespace(owner_type='project',workspace=work),config={'engine':{'profile':'studio-tools-v10'}})
        sandbox=Sandbox(worker);sandbox.context={'paths':{},'cache':cache};sandbox.cache=run_cache
        sandbox.binary=Path(__file__).resolve().parents[2]/'Data/R4OS/Toolchains/Codex/0.163.0/codex'
        code="import os,json;assert not os.path.exists(%r);assert not os.path.exists('/workspace/../Boards');assert not any('cookie' in k.lower() or 'csrf' in k.lower() for k in os.environ);print(json.dumps({'privateBoardsHidden':True}))"%str(private)
        result=subprocess.run(sandbox.command(['/usr/bin/python3','-I','-c',code]),capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr.decode());self.assertTrue(json.loads(result.stdout)['privateBoardsHidden'])
        home=self.root/'own-provider';home.mkdir();(home/'models_cache.json').write_text('{"models":[{"slug":"fixture"}]}')
        dummy=self.root/'own-not-executed-binary';dummy.write_text('qualified namespace fixture only')
        features=json.loads((Path(__file__).resolve().parents[1]/'agent-sessions/features.json').read_text())
        with patch('profile.digest',return_value=CODEX_SHA256):args,_=prepare(dummy,home,self.root/'own-native-state',features)
        args.insert(1,'--unshare-net');index=args.index('/bin/codex',args.index('--clearenv'))
        result=subprocess.run(args[:index]+['/usr/bin/python3','-I','-c',code],capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr.decode());self.assertTrue(json.loads(result.stdout)['privateBoardsHidden'])
        self.assertTrue(private.exists())

if __name__=='__main__':unittest.main()
