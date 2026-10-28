import hashlib
import sqlite3
import unittest
from unittest.mock import patch
import uuid
import test_boards as fixtures
from store import ProjectFault
from board_store import connection

class Entries(unittest.TestCase):
    setUp=fixtures.Boards.setUp
    tearDown=fixtures.Boards.tearDown
    def call(self,op='list',**args):return fixtures.Boards.call(self,op,clientLevel=2,**args)
    def create(self,name='Own board'):
        return self.call('create',input={'requestId':str(uuid.uuid4()),'expectedRevision':self.call()['revision'],'name':name})
    def change(self,bid,action,input,revision=None,rid=None):
        data={'requestId':rid or str(uuid.uuid4()),'expectedRevision':revision if revision is not None else self.call('get',boardId=bid)['board']['revision'],'action':action,'input':input}
        return self.call('mutate',boardId=bid,input=data),data
    def card(self,bid,cid):return self.call('card',boardId=bid,cardId=cid)['card']

    def test_column_card_crud_and_original_replay_preserve_details_and_positions(self):
        bid=self.create()['boardId'];column=self.call('get',boardId=bid)['columns'][0]
        renamed,_=self.change(bid,'update_column',{'columnId':column['id'],'expectedColumnRevision':column['revision'],'title':'Ready work'})
        self.assertEqual(self.call('get',boardId=bid)['columns'][0]['title'],'Ready work')
        first,original=self.change(bid,'create_card',{'columnId':column['id'],'title':'First','description':'Own\nUTF8 😀 notes'})
        replay=self.call('mutate',boardId=bid,input=original);self.assertEqual(replay,first)
        cid=first['cardId'];before=self.card(bid,cid)
        self.change(bid,'update_card',{'cardId':cid,'expectedCardRevision':before['revision'],'title':'Renamed'})
        after=self.card(bid,cid);self.assertEqual(after['id'],cid);self.assertEqual(after['description'],before['description'])
        with self.assertRaises(ProjectFault):self.change(bid,'update_card',{'cardId':cid,'expectedCardRevision':before['revision'],'title':'Stale'})
        second,_=self.change(bid,'create_card',{'columnId':column['id'],'title':'Second'})
        self.change(bid,'delete_card',{'cardId':cid,'expectedCardRevision':after['revision'],'confirm':True})
        cards=self.call('get',boardId=bid)['cards'];self.assertEqual([c['id'] for c in cards],[second['cardId']]);self.assertEqual(cards[0]['position'],0)

    def test_occupied_column_requires_valid_target_and_preserves_archived_cards_and_notes(self):
        bid=self.create()['boardId'];data=self.call('get',boardId=bid);source,target=data['columns'][:2]
        first,_=self.change(bid,'create_card',{'columnId':source['id'],'title':'Active','description':'Keep active notes'})
        hidden,_=self.change(bid,'create_card',{'columnId':source['id'],'title':'Archived fixture','description':'Keep archived notes'})
        existing,_=self.change(bid,'create_card',{'columnId':target['id'],'title':'Already there'})
        with connection(self.projects,self.pid) as db,db:db.execute("UPDATE cards SET archived=1,priority='high',due_date='2026-12-31' WHERE id=?",(hidden['cardId'],))
        args={'columnId':source['id'],'expectedColumnRevision':source['revision'],'confirm':True}
        before=self.call('get',boardId=bid)
        with self.assertRaises(ProjectFault):self.change(bid,'delete_column',args)
        self.assertEqual(self.call('get',boardId=bid),before)
        other=self.create('Other board')['boardId'];foreign=self.call('get',boardId=other)['columns'][0]['id']
        with self.assertRaises(ProjectFault):self.change(bid,'delete_column',{**args,'targetColumnId':foreign})
        result,_=self.change(bid,'delete_column',{**args,'targetColumnId':target['id']});self.assertEqual(result['movedCards'],2)
        saved=self.call('get',boardId=bid);cards=saved['cards'];self.assertEqual([c['id'] for c in cards],[existing['cardId'],first['cardId'],hidden['cardId']])
        self.assertEqual([c['position'] for c in cards],[0,1,2]);self.assertTrue(cards[-1]['archived'])
        card=self.card(bid,hidden['cardId']);self.assertEqual(card['description'],'Keep archived notes');self.assertEqual(card['priority'],'high');self.assertEqual(card['dueDate'],'2026-12-31')
        self.assertEqual([c['position'] for c in saved['columns']],[0,1])

    def test_failure_inside_transfer_rolls_back_source_target_revisions_and_receipt(self):
        bid=self.create()['boardId'];source,target=self.call('get',boardId=bid)['columns'][:2]
        self.change(bid,'create_card',{'columnId':source['id'],'title':'Keep me'})
        before=self.call('get',boardId=bid)
        rid=str(uuid.uuid4())
        with patch('board_entries.normalize',side_effect=OSError('own interrupted transaction')):
            with self.assertRaises(OSError):self.change(bid,'delete_column',{'columnId':source['id'],'expectedColumnRevision':source['revision'],'targetColumnId':target['id'],'confirm':True},rid=rid)
        self.assertEqual(self.call('get',boardId=bid),before)
        with self.assertRaises(ProjectFault):self.call('receipt',requestId=rid)

    def test_last_column_foreign_card_and_invalid_text_do_not_change_data(self):
        bid=self.create()['boardId']
        for _ in range(2):
            col=self.call('get',boardId=bid)['columns'][-1]
            self.change(bid,'delete_column',{'columnId':col['id'],'expectedColumnRevision':col['revision'],'confirm':True})
        current=self.call('get',boardId=bid);col=current['columns'][0]
        with self.assertRaises(ProjectFault):self.change(bid,'delete_column',{'columnId':col['id'],'expectedColumnRevision':col['revision'],'confirm':True})
        for title in ('','new\nline','x'*241,'\ud800'):
            with self.assertRaises(ProjectFault):self.change(bid,'create_card',{'columnId':col['id'],'title':title})
        with self.assertRaises(ProjectFault):self.change(bid,'update_card',{'cardId':str(uuid.uuid4()),'expectedCardRevision':1,'title':'Foreign'})
        self.assertEqual(self.call('get',boardId=bid),current)

    def test_new_card_data_blocks_older_reader_and_older_browser_without_replacing_bytes(self):
        bid=self.create()['boardId'];col=self.call('get',boardId=bid)['columns'][0]
        self.change(bid,'create_card',{'columnId':col['id'],'title':'Requires a card-aware reader'})
        path=self.projects/self.pid/'Boards/Boards.sqlite';before=hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(ProjectFault):fixtures.Boards.call(self,'get',boardId=bid,clientLevel=1)
        with patch('board_store.SUPPORTED_FEATURE_LEVEL',1):
            with self.assertRaises(ProjectFault):fixtures.Boards.call(self,'list')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)

if __name__=='__main__':unittest.main()
