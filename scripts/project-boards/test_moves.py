import unittest
import uuid
import test_entries as fixtures
from board_store import connection
from store import ProjectFault

class Moves(unittest.TestCase):
    setUp=fixtures.Entries.setUp
    tearDown=fixtures.Entries.tearDown
    call=fixtures.Entries.call
    create=fixtures.Entries.create
    change=fixtures.Entries.change
    card=fixtures.Entries.card
    def move(self,bid,action,input,order=None,revision=None,rid=None):
        board=self.call('get',boardId=bid)['board']
        body={'requestId':rid or str(uuid.uuid4()),'expectedRevision':revision or board['revision'],'expectedOrderRevision':order or board['orderRevision'],'action':action,'input':input}
        return self.call('mutate',boardId=bid,input=body),body
    def seed(self):
        bid=self.create()['boardId'];cols=self.call('get',boardId=bid)['columns'];ids=[]
        for col,title in ((cols[0],'A'),(cols[0],'Hidden'),(cols[0],'B'),(cols[1],'C'),(cols[1],'D')):
            result,_=self.change(bid,'create_card',{'columnId':col['id'],'title':title,'description':'Notes '+title});ids.append(result['cardId'])
        with connection(self.projects,self.pid) as db,db:db.execute("UPDATE cards SET archived=1,priority='high',due_date='2026-12-31' WHERE id=?",(ids[1],))
        return bid,cols,ids
    def test_exact_card_moves_replay_hidden_order_and_details(self):
        bid,cols,ids=self.seed();before=self.card(bid,ids[2]);args={'cardId':ids[2],'expectedCardRevision':before['revision'],'sourceColumnId':cols[0]['id'],'targetColumnId':cols[1]['id'],'position':1}
        result,body=self.move(bid,'move_card',args);self.assertEqual(self.call('mutate',boardId=bid,input=body),result)
        cards=self.call('get',boardId=bid)['cards'];self.assertEqual([c['id'] for c in cards],[ids[0],ids[1],ids[3],ids[2],ids[4]])
        self.assertEqual([c['position'] for c in cards],[0,1,0,1,2]);self.assertEqual(self.card(bid,ids[2])['description'],before['description'])
        hidden=self.card(bid,ids[1]);self.assertTrue(hidden['archived']);self.assertEqual(hidden['dueDate'],'2026-12-31')
        self.move(bid,'move_card',{'cardId':ids[0],'expectedCardRevision':self.card(bid,ids[0])['revision'],'sourceColumnId':cols[0]['id'],'targetColumnId':cols[0]['id'],'position':1})
        self.assertEqual([c['id'] for c in self.call('get',boardId=bid)['cards'] if c['columnId']==cols[0]['id']],[ids[1],ids[0]])
        body['input']['position']=0
        with self.assertRaises(ProjectFault):self.call('mutate',boardId=bid,input=body)
    def test_stale_order_foreign_target_bad_source_and_filtered_inventory_rejected(self):
        bid,cols,ids=self.seed();current=self.call('get',boardId=bid);card=self.card(bid,ids[0])
        args={'cardId':card['id'],'expectedCardRevision':card['revision'],'sourceColumnId':card['columnId'],'targetColumnId':cols[1]['id'],'position':0}
        other=self.create('Foreign')['boardId'];foreign=self.call('get',boardId=other)['columns'][0]['id'];current=self.call('get',boardId=bid)
        for bad in ({**args,'targetColumnId':foreign},{**args,'sourceColumnId':cols[2]['id']},{**args,'position':99},{**args,'ids':[ids[0]]},{**args,'expectedCardRevision':99}):
            with self.assertRaises(ProjectFault):self.move(bid,'move_card',bad)
        with self.assertRaises(ProjectFault):self.move(bid,'move_card',args,order=999)
        self.assertEqual(self.call('get',boardId=bid),current)
    def test_columns_move_preserves_cards_ids_and_checks_order_revision(self):
        bid,cols,ids=self.seed();before=self.call('get',boardId=bid)
        result,body=self.move(bid,'move_column',{'columnId':cols[0]['id'],'expectedColumnRevision':cols[0]['revision'],'position':2})
        saved=self.call('get',boardId=bid);self.assertEqual([c['id'] for c in saved['columns']],[cols[1]['id'],cols[2]['id'],cols[0]['id']]);self.assertEqual([c['position'] for c in saved['columns']],[0,1,2])
        self.assertEqual({c['id']:c for c in before['cards']},{c['id']:c for c in saved['cards']});self.assertEqual(saved['board']['orderRevision'],before['board']['orderRevision']+1)
        self.assertEqual(self.call('mutate',boardId=bid,input=body),result)
        self.assertEqual({c['id'] for c in saved['cards']},set(ids))

if __name__=='__main__':unittest.main()
