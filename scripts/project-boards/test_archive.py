import unittest
import uuid
import sqlite3
from contextlib import closing
from unittest.mock import patch
import test_metadata as fixtures
import test_boards as base
from board_store import connection
from store import ProjectFault,connect
import delete as deletion

class Archive(unittest.TestCase):
    setUp=fixtures.Metadata.setUp
    tearDown=fixtures.Metadata.tearDown
    create=fixtures.Metadata.create
    change=fixtures.Metadata.change
    card=fixtures.Metadata.card
    seed=fixtures.Metadata.seed
    edit=fixtures.Metadata.edit
    item=fixtures.Metadata.item
    def call(self,op='list',**args):return base.Boards.call(self,op,clientLevel=4,**args)
    def archive_card(self,bid,cid,action='archive_card'):return self.change(bid,action,{'cardId':cid,'expectedCardRevision':self.card(bid,cid)['revision']})
    def test_board_archive_preserves_individual_card_states_and_full_contents(self):
        bid,cid=self.seed();label=self.change(bid,'create_label',{'name':'Keep','color':'purple'})[0]['labelId'];self.edit(bid,cid,priority='high',dueDate='2028-02-29',labelIds=[label],checklist=[self.item('Keep checked',True)]);self.archive_card(bid,cid)
        col=self.call('get',boardId=bid)['columns'][0]['id'];active=self.change(bid,'create_card',{'columnId':col,'title':'Active'})[0]['cardId'];before=self.call('get',boardId=bid)
        self.change(bid,'archive_board',{});archived=self.call('get',boardId=bid);self.assertTrue(archived['board']['archived']);self.assertEqual(before['cards'],archived['cards']);self.assertEqual(before['labels'],archived['labels'])
        with self.assertRaises(ProjectFault):self.edit(bid,active,title='Blocked')
        with self.assertRaises(ProjectFault):self.archive_card(bid,cid,'restore_card')
        self.change(bid,'restore_board',{});self.assertTrue(self.card(bid,cid)['archived']);self.assertFalse(self.card(bid,active)['archived']);self.archive_card(bid,cid,'restore_card');after=self.card(bid,cid)
        self.assertEqual(after['checklist'][0]['text'],'Keep checked');self.assertEqual(after['dueDate'],'2028-02-29');self.assertEqual(after['labelIds'],[label])
    def test_archived_card_transfer_keeps_valid_parent_and_restore_works(self):
        bid,cid=self.seed();self.archive_card(bid,cid);data=self.call('get',boardId=bid);source,target=data['columns'][:2]
        self.change(bid,'delete_column',{'columnId':source['id'],'expectedColumnRevision':source['revision'],'targetColumnId':target['id'],'confirm':True});self.archive_card(bid,cid,'restore_card');self.assertEqual(self.card(bid,cid)['columnId'],target['id'])
    def test_confirmed_board_delete_cascades_only_own_content_and_replays_original_receipt(self):
        bid,cid=self.seed();self.edit(bid,cid,checklist=[self.item('Own')]);other=self.create('Other')['boardId'];before=self.call('get',boardId=other)
        with self.assertRaises(ProjectFault):self.change(bid,'delete_board',{'confirm':False})
        deleted,body=self.change(bid,'delete_board',{'confirm':True});self.assertTrue(deleted['boardDeleted']);self.assertEqual(self.call('mutate',boardId=bid,input=body),deleted);self.assertEqual(self.call('receipt',requestId=body['requestId']),deleted)
        self.assertEqual({k:v for k,v in self.call('get',boardId=other)['board'].items() if k!='position'},{k:v for k,v in before['board'].items() if k!='position'});self.assertEqual(self.call('get',boardId=other)['columns'],before['columns'])
        with connection(self.projects,self.pid) as db:
            for table in ('columns','cards','labels','checklist','card_labels'):self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table+' WHERE board_id=?',(bid,)).fetchone()[0],0)
        with self.assertRaises(ProjectFault):self.call('get',boardId=bid)
        new=self.create()['boardId'];self.assertNotEqual(new,bid)
    def test_logical_corruption_and_interrupted_write_preserve_data_and_original_identity(self):
        bid,cid=self.seed();before=self.call('get',boardId=bid);rid=str(uuid.uuid4())
        import board_entries
        apply=board_entries.apply
        def fail(*args):apply(*args);raise OSError(28,'Owned disk-full fixture')
        with patch('board_entries.apply',side_effect=fail):
            with self.assertRaises(OSError):self.change(bid,'archive_card',{'cardId':cid,'expectedCardRevision':self.card(bid,cid)['revision']},rid=rid)
        self.assertEqual(self.call('get',boardId=bid),before)
        with self.assertRaises(ProjectFault):self.call('receipt',requestId=rid)
        path=self.projects/self.pid/'Boards/Boards.sqlite'
        with closing(sqlite3.connect(path)) as db,db:db.execute('UPDATE cards SET position=99 WHERE id=?',(cid,))
        raw=path.read_bytes()
        with self.assertRaises(ProjectFault):self.call('get',boardId=bid)
        self.assertEqual(path.read_bytes(),raw)
    def test_project_rename_shared_lifetime_and_confirmed_delete_preserve_other_project(self):
        bid,cid=self.seed();other=self.call('create',pid=self.other,input={'requestId':str(uuid.uuid4()),'expectedRevision':0,'name':'Foreign'})['boardId']
        with closing(connect(self.projects)) as db,db:db.execute('UPDATE projects SET name=?,revision=revision+1 WHERE id=?',('Renamed own project',self.pid))
        self.assertEqual(self.card(bid,cid)['boardId'],bid)
        with connection(self.projects,self.pid):
            with self.assertRaises(ProjectFault):deletion.delete(self.projects,self.pid,{'revision':2,'confirm':True},{'agents':True,'development':True})
        with patch.object(deletion,'AGENT_RUNTIME',self.root/'own-agents'),patch.object(deletion,'DEVELOPMENT_RUNTIME',self.root/'own-development'):
            self.assertTrue(deletion.delete(self.projects,self.pid,{'revision':2,'confirm':True},{'agents':True,'development':True})['deleted'])
        self.assertFalse((self.projects/self.pid).exists());self.assertEqual(self.call('get',pid=self.other,boardId=other)['board']['name'],'Foreign')

    def test_board_work_continues_with_busy_agent_goal_build_and_workspace_lock(self):
        import fcntl
        from project_maintenance import busy
        bid,cid=self.seed()
        for relative,sql in (('Sessions/Sessions.sqlite',"CREATE TABLE sessions(id TEXT); CREATE TABLE runs(id TEXT,busy INTEGER,mode TEXT); INSERT INTO runs VALUES('own-agent',1,'normal'); INSERT INTO runs VALUES('own-goal',1,'goal');"),('Development/Development.sqlite',"CREATE TABLE jobs(id TEXT,kind TEXT,state TEXT,busy INTEGER,payload TEXT); INSERT INTO jobs VALUES('own-build','build','running',1,'{}');")):
            path=self.projects/self.pid/relative;path.parent.mkdir()
            with closing(sqlite3.connect(path)) as db,db:db.executescript('PRAGMA user_version=1;'+sql)
        self.assertTrue(busy(self.projects,self.pid))
        lock=self.projects/'.studio'/('workspace-'+self.pid+'.lock')
        with lock.open('a') as held:
            fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.edit(bid,cid,title='User Board edit during active work')
            self.assertEqual(self.card(bid,cid)['title'],'User Board edit during active work')
            with self.assertRaises(ProjectFault):deletion.delete(self.projects,self.pid,{'revision':1,'confirm':True},{'agents':True,'development':True})
        self.assertTrue((self.projects/self.pid/'Boards/Boards.sqlite').exists())

if __name__=='__main__':unittest.main()
