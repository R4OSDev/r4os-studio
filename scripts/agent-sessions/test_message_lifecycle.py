"""Queue/steering recovery and the existing real backup/delete boundaries."""
import asyncio
from contextlib import closing
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import AsyncMock, patch
import uuid
from zoneinfo import ZoneInfo

import test_runs as fixtures
from attachment_store import Attachments
from host import Host
from message_store import Messages
from run_store import admit, get_run, transition
from session_store import SessionStore
from store import ProjectFault


class MessageLifecycle(unittest.TestCase):
    setUp=fixtures.Runs.setUp
    tearDown=fixtures.Runs.tearDown
    open=fixtures.Runs.open

    def message(self, text='Queued human input', **changes):
        return {'requestId':str(uuid.uuid4()),'revision':1,'mode':'queue','text':text,**changes}

    def test_crash_after_admission_is_not_replayed_and_only_explicit_resume_advances(self):
        with self.open() as store:
            predecessor,_=admit(store,self.sid,self.data,self.providers)
            inbox=Messages(store)
            first,_=inbox.accept(self.sid,self.message('Original uncertain input'),self.providers)
            second,_=inbox.accept(self.sid,self.message('Separate later input'),self.providers)
            transition(store,predecessor['id'],'completed')
            frozen=json.loads(inbox.row(self.sid,first['requestId'])['frozen'])
            run,_=admit(store,self.sid,frozen['runInput'],self.providers,frozen['config'].get('imageGenerationCapability'),frozen['config'])
        host=Host({'projects':str(self.projects),'r4os':str(self.r4os),'providers':str(self.providers),'uid':os.getuid()})
        control=AsyncMock(return_value='')
        with patch('host.systemctl',control):asyncio.run(host.recover());asyncio.run(host.dispatch_queues())
        self.assertFalse(any(call.args[0] in ('start','stop') for call in control.call_args_list))
        with self.open() as store:
            inbox=Messages(store);self.assertTrue(inbox.snapshot(self.sid)['held'])
            self.assertEqual(inbox.receipt(self.sid,first['requestId'])['state'],'unknown')
            self.assertEqual(inbox.receipt(self.sid,first['requestId'])['text'],'Original uncertain input')
            self.assertEqual(get_run(store,run['id'])['state'],'unknown')
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],2)
            inbox.control(self.sid,{'requestId':str(uuid.uuid4()),'revision':inbox.snapshot(self.sid)['revision'],'action':'resume'})
            self.assertEqual(inbox.first(self.sid)['request_id'],second['requestId'])
            later=json.loads(inbox.first(self.sid)['frozen'])
            next_run,_=admit(store,self.sid,later['runInput'],self.providers,later['config'].get('imageGenerationCapability'),later['config'])
            self.assertNotEqual(next_run['id'],run['id'])

    def test_empty_stop_hold_does_not_block_a_new_explicit_chain_and_revisions_advance(self):
        with self.open() as store:
            inbox=Messages(store);inbox.hold(self.sid,'Earlier user Stop')
            run,_=admit(store,self.sid,self.data,self.providers)
            self.assertFalse(inbox.snapshot(self.sid)['held'])
            value,_=inbox.accept(self.sid,self.message(),self.providers)
            accepted_revision=inbox.snapshot(self.sid)['revision']
            transition(store,run['id'],'completed')
            frozen=json.loads(inbox.row(self.sid,value['requestId'])['frozen'])
            next_run,_=admit(store,self.sid,frozen['runInput'],self.providers,frozen['config'].get('imageGenerationCapability'),frozen['config'])
            self.assertGreater(inbox.snapshot(self.sid)['revision'],accepted_revision)
            started_revision=inbox.snapshot(self.sid)['revision']
            transition(store,next_run['id'],'running',turn_id='confirmed-native-turn')
            self.assertGreater(inbox.snapshot(self.sid)['revision'],started_revision)

    def test_old_worker_rejects_direct_input_but_keeps_its_own_history_and_queue(self):
        with self.open() as store:
            run,_=admit(store,self.sid,self.data,self.providers)
            thread=str(uuid.uuid4())
            with store.db:store.db.execute('UPDATE sessions SET thread_id=? WHERE id=?',(thread,self.sid))
            transition(store,run['id'],'running',turn_id='old-turn',worker={'release':'old-immutable-release'})
            inbox=Messages(store)
            with self.assertRaises(ProjectFault) as old:
                inbox.accept(self.sid,self.message(mode='steer',target={'runId':run['id'],'threadId':thread,'turnId':'old-turn'}),self.providers)
            self.assertEqual(old.exception.code,503)
            original=get_run(store,run['id'])['config']
            inbox.accept(self.sid,self.message(),self.providers)
            self.assertEqual(store.row(self.sid)['thread_id'],thread)
            self.assertEqual(get_run(store,run['id'])['config'],original)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],1)

    @unittest.skipIf(os.getuid()!=0,'The existing host backup source is root-readable.')
    def test_actual_backup_restore_then_recovery_holds_inputs_and_delete_keeps_foreign_data(self):
        sys.path.insert(1,str(Path(__file__).resolve().parents[3]/'Tools/Backup'))
        import backup
        from restore import restore
        with self.open() as store:
            raw=b'Owned queued document'
            meta=Attachments(store,self.sid).upload({'requestId':str(uuid.uuid4()),'name':'own.txt','size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'mediaType':'text/plain'},io.BytesIO(raw))['attachment']
            message,_=Messages(store).accept(self.sid,self.message(attachments=[meta['id']]),self.providers,{'nativeImageInputs':1,'documentInputs':1})
        root=self.root/'own-backup-root';root.mkdir()
        for source in backup.SOURCES:
            path=root/source
            if source=='AGENTS.md':path.write_text('Owned backup fixture')
            else:path.mkdir(parents=True,exist_ok=True)
        shutil.copytree(self.projects,root/'App/Data/Projects',dirs_exist_ok=True)
        excluded=root/'App/Data/Skills/own';excluded.mkdir(parents=True);(excluded/'keep.txt').write_text('excluded')
        paths=backup.Paths(root,self.root/'mount',self.root/'mount/backup',self.root/'backup-state',self.root/'backup.lock');paths.mount.mkdir()
        result=backup.run(paths,lambda _:('owned-fixture-mount',),datetime(2026,10,28,4,tzinfo=ZoneInfo('Europe/Berlin')))
        restored=self.root/'isolated-restore';restore(paths.destination/result['archive'],restored)
        project_root=restored/'App/Data/Projects'
        self.assertEqual(len(backup.SOURCES),7);self.assertFalse((restored/'App/Data/Skills').exists())
        host=Host({'projects':str(project_root),'r4os':str(self.r4os),'providers':str(self.providers),'uid':os.getuid()})
        with patch('host.systemctl',AsyncMock(return_value='')):asyncio.run(host.recover())
        with closing(SessionStore(project_root,self.r4os,self.pid)) as store:
            inbox=Messages(store);self.assertEqual(inbox.receipt(self.sid,message['requestId'])['attachments'],message['attachments'])
            self.assertTrue(inbox.snapshot(self.sid)['held'])
            self.assertEqual(Path(Attachments(store,self.sid).access(meta['id'])['path']).read_bytes(),raw)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],0)
        import delete as deletion
        foreign=self.root/'foreign-file';foreign.write_text('keep foreign bytes')
        (project_root/self.pid/'Sessions/foreign-link').symlink_to(foreign)
        with patch.object(deletion,'AGENT_RUNTIME',self.root/'own-agent-runtime'),patch.object(deletion,'DEVELOPMENT_RUNTIME',self.root/'own-dev-runtime'),patch.object(deletion,'worker_check'):
            result=deletion.delete(project_root,self.pid,{'revision':1,'confirm':True},{'agents':True,'development':True})
        self.assertTrue(result['deleted']);self.assertFalse((project_root/self.pid).exists())
        self.assertEqual(foreign.read_text(),'keep foreign bytes')
        self.assertTrue((self.projects/self.pid/'Sessions/Sessions.sqlite').exists())


if __name__=='__main__':unittest.main()
