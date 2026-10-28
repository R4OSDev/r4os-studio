"""Typed local observations, revision races and content-free deletion receipts."""
import json
import unittest
import uuid
from run_store import admit,transition
from environment_notes import Notes,hashed
from store import ProjectFault
import test_runs as fixtures

class EnvironmentNotes(unittest.TestCase):
    setUp=fixtures.Runs.setUp
    tearDown=fixtures.Runs.tearDown
    open=fixtures.Runs.open
    def ready(self,store):
        run,_=admit(store,self.sid,self.data,self.providers);transition(store,run['id'],'running',turn_id='own-turn')
        return run['id']
    def call(self,store,rid,call,tool):
        with store.db:store.db.execute('INSERT INTO tools VALUES (?,?,?,?,?,?,NULL)',(rid,call,'studio_'+tool,call,'intent','{}'))
    def read(self,store,rid,call='read'):
        self.call(store,rid,call,'read_environment_notes');return Notes(store).read_tool(self.sid,rid,call,{})
    def value(self,revision=0,**changes):return {'revision':revision,'kind':'problem','category':'tools','title':'Tool contract mismatch','description':'A documented argument was rejected by the Studio adapter.',**changes}
    def test_read_then_record_exact_duplicate_and_original_deleted_replay(self):
        with self.open() as store:
            rid=self.ready(store);notes=Notes(store);self.call(store,rid,'write','record_environment_note')
            with self.assertRaises(ProjectFault):notes.record(self.sid,rid,'write',self.value(),'0.7.19')
            self.read(store,rid);value=self.value();first=notes.record(self.sid,rid,'write',value,'0.7.19')
            self.assertEqual(notes.record(self.sid,rid,'write',value,'0.7.19'),first)
            current=self.read(store,rid,'read2');self.call(store,rid,'duplicate','record_environment_note')
            same=notes.record(self.sid,rid,'duplicate',self.value(current['revision'],title='  TOOL CONTRACT MISMATCH  '),'0.7.19');self.assertEqual(same['id'],first['id']);self.assertEqual(notes.current(self.sid)[1],1)
            row=notes.listing(self.sid)['entries'][0];deleted=notes.delete(self.sid,{'requestId':str(uuid.uuid4()),'collectionRevision':current['revision'],'revision':row['revision']},row['id'])
            self.assertEqual(deleted['count'],0);self.assertEqual(notes.record(self.sid,rid,'write',value,'0.7.19')['state'],'deleted')
            raw=store.db.execute('SELECT data FROM environment_notes WHERE id=?',(row['id'],)).fetchone()[0];self.assertIsNone(raw)
    def test_stale_delete_all_read_write_stop_and_foreign_scope_are_rejected(self):
        with self.open() as store:
            rid=self.ready(store);notes=Notes(store);self.read(store,rid);self.call(store,rid,'first','record_environment_note');notes.record(self.sid,rid,'first',self.value(),'0.7.19')
            self.call(store,rid,'stale','record_environment_note')
            with self.assertRaises(ProjectFault):notes.record(self.sid,rid,'stale',self.value(title='Another useful report'),'0.7.19')
            before=notes.listing(self.sid);self.read(store,rid,'newread');self.call(store,rid,'second','record_environment_note');notes.record(self.sid,rid,'second',self.value(before['revision'],kind='suggestion',title='Better adapter help'),'0.7.19')
            request={'requestId':str(uuid.uuid4()),'collectionRevision':before['revision'],'confirmName':store.row(self.sid)['name'],'count':before['count']}
            with self.assertRaises(ProjectFault):notes.delete(self.sid,request)
            request.update(collectionRevision=notes.current(self.sid)[0],count=2);result=notes.delete(self.sid,request);self.assertEqual(notes.delete(self.sid,request),result)
            with self.assertRaises(ProjectFault):notes.delete(self.sid,{**request,'count':0})
            transition(store,rid,'stopping');self.call(store,rid,'stopped','record_environment_note')
            with self.assertRaises(ProjectFault):notes.record(self.sid,rid,'stopped',self.value(notes.current(self.sid)[0]),'0.7.19')
            with self.assertRaises(ProjectFault):notes.listing(str(uuid.uuid4()))
    def test_bounded_values_private_data_and_safe_text_are_preserved(self):
        with self.open() as store:
            rid=self.ready(store);notes=Notes(store);self.read(store,rid);self.call(store,rid,'write','record_environment_note')
            for bad in [self.value(title='x'*161),self.value(description='/root/private/credentials'),self.value(description='Bearer '+('a'*24)),self.value(category='project-bug')]:
                with self.assertRaises(ProjectFault):notes.record(self.sid,rid,'write',bad,'0.7.19')
            value=self.value(title='<script>plain text</script>');notes.record(self.sid,rid,'write',value,'0.7.19');page=notes.listing(self.sid,{'query':'plain text','limit':1})
            self.assertEqual(page['entries'][0]['title'],value['title']);self.assertNotIn('fingerprint',json.dumps(page));self.assertEqual(page['count'],1)

    def test_full_collection_preserves_entries_and_read_pages_are_bounded(self):
        from unittest.mock import patch
        with self.open() as store,patch('environment_notes.MAX_NOTES',1):
            rid=self.ready(store);notes=Notes(store);self.read(store,rid);self.call(store,rid,'first','record_environment_note');first=notes.record(self.sid,rid,'first',self.value(),'0.7.19')
            current=self.read(store,rid,'again');self.call(store,rid,'full','record_environment_note')
            with self.assertRaises(ProjectFault):notes.record(self.sid,rid,'full',self.value(current['revision'],title='Another actionable observation'),'0.7.19')
            self.assertEqual(notes.listing(self.sid)['entries'][0]['id'],first['id'])
