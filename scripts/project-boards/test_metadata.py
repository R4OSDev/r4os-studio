import unittest
import uuid
import hashlib
import test_entries as fixtures
import test_boards as base
from store import ProjectFault

class Metadata(unittest.TestCase):
    setUp=fixtures.Entries.setUp
    tearDown=fixtures.Entries.tearDown
    create=fixtures.Entries.create
    change=fixtures.Entries.change
    card=fixtures.Entries.card
    def call(self,op='list',**args):return base.Boards.call(self,op,clientLevel=3,**args)
    def seed(self):
        bid=self.create()['boardId'];col=self.call('get',boardId=bid)['columns'][0]['id'];cid=self.change(bid,'create_card',{'columnId':col,'title':'Own card','description':'First preview. '+'x'*300+' Find Straße 😀 here.'})[0]['cardId'];return bid,cid
    def edit(self,bid,cid,**input):return self.change(bid,'update_card',{'cardId':cid,'expectedCardRevision':self.card(bid,cid)['revision'],**input})
    def item(self,text,checked=False):return {'id':str(uuid.uuid4()),'text':text,'checked':checked,'revision':0}
    def checks(self,bid,cid):return [{k:v for k,v in item.items() if k!='position'} for item in self.card(bid,cid)['checklist']]
    def test_checklist_stable_ids_edits_order_progress_removal_and_replay(self):
        bid,cid=self.seed();one,two=self.item('First'),self.item('Second',True)
        result,original=self.edit(bid,cid,checklist=[one,two]);self.assertEqual(self.call('mutate',boardId=bid,input=original),result)
        checks=self.checks(bid,cid);checks[0]['text']='Renamed';checks[0]['checked']=True
        self.edit(bid,cid,checklist=list(reversed(checks)))
        current=self.card(bid,cid);self.assertEqual([r['id'] for r in current['checklist']],[two['id'],one['id']]);self.assertEqual([r['position'] for r in current['checklist']],[0,1])
        summary=self.call('get',boardId=bid)['cards'][0];self.assertEqual((summary['checked'],summary['checklistCount']),(2,2))
        self.edit(bid,cid,checklist=self.checks(bid,cid)[1:]);self.assertEqual([r['id'] for r in self.card(bid,cid)['checklist']],[one['id']])
    def test_label_rename_keeps_relations_and_delete_keeps_cards_and_checks(self):
        bid,cid=self.seed();label=self.change(bid,'create_label',{'name':'Important','color':'purple'})[0]['labelId'];self.edit(bid,cid,labelIds=[label],checklist=[self.item('Keep')])
        current=self.call('get',boardId=bid)['labels'][0];before=self.card(bid,cid)
        self.change(bid,'update_label',{'labelId':label,'expectedLabelRevision':current['revision'],'name':'Ready','color':'green'})
        self.assertEqual(self.card(bid,cid)['labelIds'],[label]);self.assertEqual(self.call('get',boardId=bid)['labels'][0]['name'],'Ready')
        with self.assertRaises(ProjectFault):self.change(bid,'create_label',{'name':'READY','color':'blue'})
        current=self.call('get',boardId=bid)['labels'][0];self.change(bid,'delete_label',{'labelId':label,'expectedLabelRevision':current['revision'],'confirm':True})
        after=self.card(bid,cid);self.assertEqual(after['labelIds'],[]);self.assertEqual(after['checklist'],before['checklist']);self.assertEqual(after['description'],before['description']);self.assertGreater(after['revision'],before['revision'])
    def test_calendar_dates_no_timezone_and_invalid_metadata_roll_back(self):
        bid,cid=self.seed();self.edit(bid,cid,priority='high',dueDate='2028-02-29');self.assertEqual(self.card(bid,cid)['dueDate'],'2028-02-29')
        before=self.call('get',boardId=bid)
        for args in ({'dueDate':'2027-02-29'},{'dueDate':'2026-10-28T00:00:00Z'},{'dueDate':'2026-1-01'},{'dueDate':False},{'priority':'urgent'},{'priority':[]},{'checklist':[self.item('')]}):
            with self.assertRaises(ProjectFault):self.edit(bid,cid,**args)
        self.assertEqual(self.call('get',boardId=bid),before)
        self.edit(bid,cid,priority='normal',dueDate=None);self.assertIsNone(self.card(bid,cid)['dueDate'])
    def test_foreign_labels_items_duplicates_and_stale_revisions_preserve_all(self):
        bid,cid=self.seed();other=self.create('Other')['boardId'];col=self.call('get',boardId=other)['columns'][0]['id'];foreign=self.change(other,'create_card',{'columnId':col,'title':'Foreign'})[0]['cardId'];foreign_label=self.change(other,'create_label',{'name':'Foreign','color':'gray'})[0]['labelId']
        self.edit(other,foreign,checklist=[self.item('Foreign item')]);item=self.checks(other,foreign)[0];item['revision']=0
        own=self.change(bid,'create_label',{'name':'Own','color':'pink'})[0]['labelId'];self.edit(bid,cid,labelIds=[own],checklist=[self.item('Own')]);before=self.call('get',boardId=bid);detail=self.card(bid,cid)
        for args in ({'labelIds':[foreign_label]},{'labelIds':[own,own]},{'checklist':[item]},{'checklist':[self.item('A')]*2},{'checklist':[self.item('x') for _ in range(101)]},{'checklist':[{**self.checks(bid,cid)[0],'revision':999}]}):
            with self.assertRaises(ProjectFault):self.edit(bid,cid,labelIds=[],**args) if 'labelIds' not in args else self.edit(bid,cid,**args)
        self.assertEqual(self.call('get',boardId=bid),before);self.assertEqual(self.card(bid,cid),detail)
    def test_full_description_unicode_search_old_reader_guard_and_original_bytes(self):
        bid,cid=self.seed();self.assertEqual(self.call('search',boardId=bid,query='STRASSE 😀')['cardIds'],[cid]);self.assertEqual(self.call('search',boardId=bid,query='absent')['cardIds'],[])
        self.edit(bid,cid,priority='low');path=self.projects/self.pid/'Boards/Boards.sqlite';before=hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(ProjectFault):base.Boards.call(self,'get',boardId=bid,clientLevel=2)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)

if __name__=='__main__':unittest.main()
