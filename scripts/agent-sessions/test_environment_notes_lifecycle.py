"""Private WAL backup/restore, real owner deletion and frozen execution bounds."""
import asyncio
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import AsyncMock,patch
import uuid
from zoneinfo import ZoneInfo
import test_environment_note_tools as fixtures
from environment_notes import Notes,hashed
from run_store import admit,transition,get_run
from session_store import SessionStore,encode
from message_store import Messages
from host import Host
from profile import NOTES_SKILL_PROFILE,CODEX_VERSION,CODEX_SHA256,permission_tools

class NoteLifecycle(unittest.TestCase):
    setUp=fixtures.NoteTools.setUp
    tearDown=fixtures.NoteTools.tearDown
    open=fixtures.NoteTools.open
    current=fixtures.NoteTools.current
    worker=fixtures.NoteTools.worker
    call=fixtures.NoteTools.call
    note=fixtures.NoteTools.note
    def test_note_errors_stop_and_changed_choice_preserve_original_queue(self):
        w=self.worker()
        try:
            inbox=Messages(w.store);value={'requestId':str(uuid.uuid4()),'revision':1,'mode':'queue','text':'Owned queued continuation'}
            inbox.accept(self.sid,value,self.providers,{'environmentNotesSettings':1});original=inbox.row(self.sid,value['requestId'])['frozen'];self.assertTrue(json.loads(original)['config']['environmentNotesEnabled'])
            before=inbox.snapshot(self.sid)
            self.call(w,'read_environment_notes',{},'read');_,failure=self.call(w,'record_environment_note',{**self.note(),'description':'/root/private/credentials'},'invalid');self.assertEqual(failure['error'],'noteRejected');self.assertFalse(w.uncertain_effect);self.assertFalse(w.stopping);self.assertEqual(inbox.snapshot(self.sid),before)
            # Large but valid entries force a bounded page without dropping data.
            for number in range(4):
                _,page=self.call(w,'read_environment_notes',{},'read-'+str(number))
                _,receipt=self.call(w,'record_environment_note',{**self.note(page['revision']),'title':'Owned large observation '+str(number),'description':'x'*3900,'impact':'y'*900,'workaround':'z'*900,'suggestion':'s'*900},'write-'+str(number));self.assertEqual(receipt['state'],'active')
            page=Notes(w.store).listing(self.sid);self.assertLessEqual(sum(len(encode(v).encode()) for v in page['entries']),24576);self.assertIsNotNone(page['nextBefore']);other=Notes(w.store).listing(self.sid,{'before':page['nextBefore']});self.assertEqual(len(page['entries'])+len(other['entries']),4)
            inbox.hold(self.sid,'User Stop. Continue explicitly.');transition(w.store,w.run_id,'stopping');_,stopped=self.call(w,'record_environment_note',self.note(page['revision']),'stopped');self.assertEqual(stopped['error'],'disabled');transition(w.store,w.run_id,'interrupted')
            w.store.update(self.sid,{'revision':1,'environmentNotesEnabled':False},self.providers)
            current=inbox.snapshot(self.sid);inbox.control(self.sid,{'requestId':str(uuid.uuid4()),'revision':current['revision'],'action':'resume'})
            host=Host({'projects':str(self.projects),'r4os':str(self.r4os),'providers':str(self.providers),'uid':0});host.inboxes.add(('project',self.pid,self.sid));host.launch_admitted=AsyncMock()
            asyncio.run(host.dispatch_queues());host.launch_admitted.assert_not_called();self.assertTrue(inbox.snapshot(self.sid)['held']);self.assertEqual(inbox.row(self.sid,value['requestId'])['frozen'],original);self.assertTrue(json.loads(get_run(w.store,w.run_id)['config'])['environmentNotesEnabled'])
        finally:w.store.close()
    def test_live_wal_backup_project_delete_and_isolated_restore_keep_note_receipts(self):
        sys.path.insert(1,str(Path(__file__).resolve().parents[3]/'Tools/Backup'))
        import backup
        from restore import restore
        import delete as project_delete
        source_root=self.root/'sources';target=source_root/'App/Data/Projects';target.parent.mkdir(parents=True);shutil.move(str(self.projects),target);self.projects=target
        for source in backup.SOURCES:
            path=source_root/source
            if source=='AGENTS.md':path.write_text('Owned note backup fixture')
            else:path.mkdir(parents=True,exist_ok=True)
        excluded=source_root/'App/Data/Skills';excluded.mkdir();(excluded/'own.txt').write_text('Excluded skill fixture')
        w=self.worker();originals={}
        try:
            w.store.db.execute('PRAGMA journal_mode=WAL');w.store.db.execute('PRAGMA wal_autocheckpoint=0')
            for key,title in [('removed','Original removed observation'),('kept','Original kept suggestion')]:
                _,page=self.call(w,'read_environment_notes',{},'read-'+key);payload={**self.note(page['revision']),'title':title,'kind':'suggestion' if key=='kept' else 'problem'};_,value=self.call(w,'record_environment_note',payload,key);originals[key]=(payload,value)
            notes=Notes(w.store);page=notes.listing(self.sid);entry=next(v for v in page['entries'] if v['id']==originals['removed'][1]['id']);request={'requestId':str(uuid.uuid4()),'collectionRevision':page['revision'],'revision':entry['revision']};deletion=notes.delete(self.sid,request,entry['id']);revision=notes.current(self.sid)[0]
            self.assertTrue((w.store.directory/'Sessions.sqlite-wal').exists())
            paths=backup.Paths(source_root,self.root/'mount',self.root/'mount/backup',self.root/'backup-state',self.root/'backup.lock');paths.mount.mkdir()
            result=backup.run(paths,lambda _:('owned-note-mount',),datetime(2026,10,28,4,tzinfo=ZoneInfo('Europe/Berlin')))
            archive=paths.destination/result['archive']
            import zipfile
            with zipfile.ZipFile(archive) as z:
                manifest=[json.loads(line) for line in z.read(backup.MANIFEST).splitlines()];db_entry=next(v for v in manifest if v.get('path')==f'App/Data/Projects/{self.pid}/Sessions/Sessions.sqlite');self.assertTrue(db_entry['sqliteOnlineBackup']);self.assertFalse(any(name.endswith(('-wal','-shm')) for name in z.namelist()))
            transition(w.store,w.run_id,'completed')
        finally:w.store.close()
        with patch.object(project_delete,'worker_check'),patch.object(project_delete,'AGENT_RUNTIME',self.root/'own-agent-runtime'),patch.object(project_delete,'DEVELOPMENT_RUNTIME',self.root/'own-development-runtime'):
            deleted=project_delete.delete(self.projects,self.pid,{'revision':1,'confirm':True},{'agents':True,'development':True})
        self.assertTrue(deleted['deleted']);self.assertFalse((self.projects/self.pid).exists());self.assertTrue(archive.exists())
        restored=self.root/'isolated-restore';restore(archive,restored);self.assertEqual(len(backup.SOURCES),7);self.assertFalse((restored/'App/Data/Skills').exists())
        with closing(SessionStore(restored/'App/Data/Projects',self.r4os,self.pid)) as store:
            notes=Notes(store);page=notes.listing(self.sid);self.assertEqual(page['revision'],revision);self.assertEqual(page['count'],1);self.assertEqual(page['entries'][0]['id'],originals['kept'][1]['id']);self.assertEqual(notes.deletion_receipt(self.sid,request['requestId']),deletion)
            receipt=notes.call_receipt(self.sid,w.run_id,'removed',hashed(originals['removed'][0]));self.assertEqual(receipt['state'],'deleted');self.assertEqual(notes.record(self.sid,w.run_id,'removed',originals['removed'][0],'0.7.22')['state'],'deleted');self.assertEqual(notes.current(self.sid)[1],1)
            self.assertIsNone(store.db.execute('SELECT data FROM environment_notes WHERE id=?',(entry['id'],)).fetchone()[0]);self.assertEqual(store.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],1)
            self.assertFalse(any('Original kept suggestion' in p.read_text(errors='replace') for p in store.workspace.rglob('*') if p.is_file()))
    def test_full_skill_deletion_includes_notes_and_rejects_changed_preview(self):
        import test_skills
        from skill_delete import preview,delete,resume
        from skill_application import packages
        f=test_skills.Skills();f.setUp()
        try:
            sid=f.session['id'];ident=f.ids[0]
            with f.open() as store:
                settings=json.loads(store.row(sid)['settings']);settings['permissions']={'studio.'+v:True for v in permission_tools(NOTES_SKILL_PROFILE)}
                with store.db:store.db.execute('UPDATE sessions SET engine=?,settings=? WHERE id=?',(encode({'profile':NOTES_SKILL_PROFILE,'version':CODEX_VERSION,'sha256':CODEX_SHA256}),encode(settings),sid))
                run,_=admit(store,sid,{**f.input(),'environmentNotesSettings':1},f.providers);transition(store,run['id'],'running',turn_id='owned')
                read,call='read','record'
                with store.db:store.db.execute('INSERT INTO tools VALUES (?,?,?,?,?,?,NULL)',(run['id'],read,'studio_read_environment_notes',read,'intent','{}'))
                Notes(store).read_tool(sid,run['id'],read,{})
                with store.db:store.db.execute('INSERT INTO tools VALUES (?,?,?,?,?,?,NULL)',(run['id'],call,'studio_record_environment_note',call,'intent','{}'))
                Notes(store).record(sid,run['id'],call,self.note(),'0.7.22');transition(store,run['id'],'completed')
            host=Host(f.config);host.active_unit=AsyncMock(return_value=False)
            view,_=asyncio.run(preview(host,ident));data={'requestId':str(uuid.uuid4()),'revision':view['revision'],'scopeHash':view['scopeHash'],'confirmName':view['name']}
            with f.open() as store:
                page=Notes(store).listing(sid);Notes(store).delete(sid,{'requestId':str(uuid.uuid4()),'collectionRevision':page['revision'],'revision':1},page['entries'][0]['id'])
            from store import ProjectFault
            with self.assertRaises(ProjectFault):asyncio.run(delete(host,ident,data))
            view,_=asyncio.run(preview(host,ident));data.update(requestId=str(uuid.uuid4()),scopeHash=view['scopeHash']);asyncio.run(delete(host,ident,data));asyncio.run(resume(host,data['requestId']))
            self.assertFalse((f.skills/ident).exists());self.assertTrue((f.skills/f.ids[1]).exists())
            with closing(packages.connect(f.skills)) as db:self.assertEqual(db.execute('SELECT phase FROM skill_deletions WHERE skill_id=?',(ident,)).fetchone()[0],'deleted')
        finally:f.tearDown()
