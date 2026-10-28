"""Frozen note admission and recovery of only the local atomic effect."""
import asyncio
import json
import unittest
import uuid
from unittest.mock import patch
from contextlib import closing
import test_runs as fixtures
from session_store import encode
from profile import PROFILE,NOTES_SKILL_PROFILE,permission_tools,CODEX_VERSION,CODEX_SHA256
from run_store import admit,transition,get_run
from worker import Worker
from environment_notes import Notes
from environment_note_tools import instructions

class NoteTools(unittest.TestCase):
    setUp=fixtures.Runs.setUp
    tearDown=fixtures.Runs.tearDown
    open=fixtures.Runs.open
    def current(self,store):
        settings={**self.settings,'permissions':{'studio.'+v:True for v in permission_tools(PROFILE)}}
        with store.db:store.db.execute('UPDATE sessions SET engine=?,settings=? WHERE id=?',(encode({'profile':PROFILE,'version':CODEX_VERSION,'sha256':CODEX_SHA256}),encode(settings),self.sid))
    def worker(self):
        with self.open() as store:
            self.current(store);run,_=admit(store,self.sid,{**self.data,'environmentNotesSettings':1},self.providers)
            transition(store,run['id'],'running',turn_id='turn')
        w=Worker({'projects':str(self.projects),'r4os':str(self.r4os),'projectId':self.pid,'runId':run['id'],'version':'0.7.20'});w.thread_id='thread';w.turn_id='turn';return w
    def call(self,w,name,args,call):
        value=asyncio.run(w.tool({'namespace':None,'threadId':'thread','turnId':'turn','tool':'studio_'+name,'callId':call,'arguments':args}))
        payload=json.loads(value['contentItems'][0]['text'])
        return value,json.loads(payload['output']) if payload.get('success') else payload
    def note(self,revision=0):return {'revision':revision,'kind':'problem','category':'tools','title':'Adapter contract mismatch','description':'The documented option is rejected by the Studio adapter.'}
    def test_default_settings_off_frozen_and_legacy_without_migration(self):
        with self.open() as store:
            old=tuple(store.row(self.sid));self.assertFalse(store.get(self.sid)['environmentNotesAccess']['available']);self.assertEqual(tuple(store.row(self.sid)),old)
            self.current(store);self.assertTrue(store.get(self.sid)['environmentNotesEnabled'])
            run,_=admit(store,self.sid,{**self.data,'environmentNotesSettings':1},self.providers);config=json.loads(get_run(store,run['id'])['config']);self.assertTrue(config['environmentNotesEnabled'])
            self.assertIn('no reporting quota',instructions(config));self.assertIn('normal compiler diagnostics',instructions(config))
            transition(store,run['id'],'completed');selected=store.update(self.sid,{'revision':1,'environmentNotesEnabled':False},self.providers)
            run,_=admit(store,self.sid,{**self.data,'requestId':str(uuid.uuid4()),'revision':selected['revision'],'environmentNotesSettings':1},self.providers);off=json.loads(get_run(store,run['id'])['config']);self.assertFalse(off['environmentNotesEnabled']);self.assertEqual(instructions(off),'');self.assertTrue(config['environmentNotesEnabled'])
            self.assertNotIn('studio.read_environment_notes',selected['permissions'])
            from session_store import SessionStore
            import test_skills
            fixture=test_skills.Skills();fixture.setUp()
            try:
                with closing(SessionStore(fixture.projects,fixture.r4os,fixture.ids[0],'skill')) as skills,patch('session_store.engine',return_value={'profile':NOTES_SKILL_PROFILE,'available':True}):
                    new=skills.create({'name':'Notes','providerId':fixture.provider,'model':'fixture','effort':'low','requestId':str(uuid.uuid4())},fixture.providers)
                    self.assertTrue(new['environmentNotesAccess']['available']);self.assertTrue(new['environmentNotesEnabled'])
            finally:fixture.tearDown()
    def test_read_create_duplicate_lost_generic_receipt_deleted_replay_off_and_stop(self):
        w=self.worker()
        try:
            response,value=self.call(w,'record_environment_note',self.note(),'before-read');self.assertFalse(response['success']);self.assertEqual(value['error'],'noteRejected');self.assertFalse(w.uncertain_effect)
            _,page=self.call(w,'read_environment_notes',{},'read');self.assertEqual(page['count'],0)
            response,first=self.call(w,'record_environment_note',self.note(),'write');self.assertTrue(response['success'])
            with w.store.db:w.store.db.execute("UPDATE tools SET state='intent',result=NULL WHERE call_id='write'")
            _,recovered=self.call(w,'record_environment_note',self.note(),'write');self.assertEqual(recovered['id'],first['id']);self.assertFalse(w.uncertain_effect)
            _,page=self.call(w,'read_environment_notes',{},'read2');_,duplicate=self.call(w,'record_environment_note',self.note(page['revision']),'duplicate');self.assertEqual(duplicate['id'],first['id'])
            notes=Notes(w.store);entry=notes.listing(self.sid)['entries'][0];notes.delete(self.sid,{'requestId':str(uuid.uuid4()),'collectionRevision':page['revision'],'revision':entry['revision']},entry['id'])
            _,deleted=self.call(w,'record_environment_note',self.note(),'write');self.assertEqual(deleted['state'],'deleted');self.assertEqual(notes.current(self.sid)[1],0)
            _,stale=self.call(w,'record_environment_note',self.note(page['revision']),'stale');self.assertEqual(stale['error'],'noteRejected')
            w.config['environmentNotesEnabled']=False;_,off=self.call(w,'record_environment_note',self.note(),'write');self.assertEqual(off['error'],'disabled')
            w.config['environmentNotesEnabled']=True;transition(w.store,w.run_id,'stopping');_,stopped=self.call(w,'read_environment_notes',{},'stopped');self.assertEqual(stopped['error'],'disabled');self.assertFalse(w.uncertain_effect)
        finally:w.store.close()
