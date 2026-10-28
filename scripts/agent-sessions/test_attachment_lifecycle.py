"""Reference-aware deletion, crash recovery, history and offline restore."""
from contextlib import closing
import errno
import io
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid
from attachment_store import Attachments
from image_inputs import history,mounts,frozen
from run_store import admit,get_run,transition,item
from session_store import SessionStore,encode
from store import ProjectFault
import test_image_inputs as images


class Lifecycle(unittest.TestCase):
    setUp=images.ImageInputs.setUp
    tearDown=images.ImageInputs.tearDown
    open=images.ImageInputs.open
    upload=images.ImageInputs.upload
    message=images.ImageInputs.message

    def test_sent_or_unknown_run_survives_draft_removal_reopen_and_download(self):
        with self.open() as store:
            meta=self.upload(store);attachments=Attachments(store,self.sid)
            data=self.message([meta['id']]);run,_=admit(store,self.sid,data,self.providers)
            transition(store,run['id'],'unknown')
            before=attachments.usage();result=attachments.remove(meta['id'])
            self.assertTrue(result['retainedForHistory']);self.assertEqual(attachments.usage(),before)
            original=Path(attachments.preview(meta['id'])['path']).read_bytes()
            self.assertEqual(store.history(self.sid)['items'][0]['attachments'][0]['sha256'],meta['sha256'])
        with self.open() as store:
            attachments=Attachments(store,self.sid)
            self.assertEqual(Path(attachments.access(meta['id'])['path']).read_bytes(),original)
            self.assertEqual(history(store,self.sid),[frozen(meta)])
            self.assertEqual(len(mounts(store,self.sid,json.loads(get_run(store,run['id'])['config']))),1)
            self.assertFalse(admit(store,self.sid,data,self.providers)[1])

    def test_removal_crash_preserves_quota_and_retries_only_proven_unused_identity(self):
        with self.open() as store:
            meta=self.upload(store);attachments=Attachments(store,self.sid);before=attachments.usage()
            with patch('attachment_store.sync',side_effect=OSError(errno.ENOSPC,'own full fixture')):
                with self.assertRaises(ProjectFault):attachments.remove(meta['id'])
            self.assertEqual(attachments.row(meta['id'])['state'],'removing')
            self.assertEqual(attachments.usage(),before)
            self.assertEqual(attachments.listing()['cleanupPending'],[{'id':meta['id'],'name':meta['name']}])
            with self.assertRaises(ProjectFault):admit(store,self.sid,self.message([meta['id']]),self.providers)
        with self.open() as store:
            attachments=Attachments(store,self.sid);self.assertFalse(attachments.remove(meta['id'])['retainedForHistory'])
            self.assertEqual(attachments.usage()['sessionFiles'],0)
            self.assertEqual(attachments.receipt(attachments.row(meta['id'])['request_id'])['state'],'removed')

    def test_old_config_or_history_reference_without_ref_table_is_conservatively_retained(self):
        with self.open() as store:
            meta=self.upload(store);run,_=admit(store,self.sid,self.message([meta['id']]),self.providers)
            with store.db:store.db.execute('DELETE FROM attachment_refs')
            self.assertTrue(Attachments(store,self.sid).remove(meta['id'])['retainedForHistory'])
            with store.db:store.db.execute("UPDATE runs SET config='{}'")
            self.assertTrue(Attachments(store,self.sid).remove(meta['id'])['retainedForHistory'])
            self.assertTrue(Path(Attachments(store,self.sid).access(meta['id'])['path']).exists())

    def test_corrupt_unrelated_metadata_blocks_cleanup_without_touching_bytes(self):
        with self.open() as store:
            meta=self.upload(store);run,_=admit(store,self.sid,{'requestId':str(uuid.uuid4()),'revision':1,'text':'Own text'},self.providers)
            with store.db:store.db.execute('UPDATE runs SET config=?',('{broken',))
            with self.assertRaises(ProjectFault):Attachments(store,self.sid).remove(meta['id'])
            self.assertEqual(Attachments(store,self.sid).row(meta['id'])['state'],'ready')
            self.assertTrue(Path(Attachments(store,self.sid).preview(meta['id'])['path']).exists())

    def test_unexpected_file_or_symlink_is_preserved_and_foreign_session_cannot_remove(self):
        with self.open() as store:
            meta=self.upload(store);attachments=Attachments(store,self.sid);parent=attachments.root()/meta['id']
            foreign=self.root/'foreign-keep';foreign.write_text('keep');(parent/'foreign-link').symlink_to(foreign)
            with self.assertRaises(ProjectFault):attachments.remove(meta['id'])
            self.assertEqual(foreign.read_text(),'keep');self.assertTrue((parent/'original.png').exists())
            (parent/'foreign-link').unlink();attachments.remove(meta['id'])
            self.assertFalse(parent.exists())

    def test_upload_disk_full_has_no_ready_file_and_no_run(self):
        with self.open() as store:
            attachments=Attachments(store,self.sid)
            from test_attachments import Uploads
            data=Uploads.upload_data(self,b'own')
            with patch('attachment_store.os.fsync',side_effect=OSError(errno.ENOSPC,'own full fixture')):
                result=attachments.upload(data,io.BytesIO(b'own'))
            self.assertEqual(result['state'],'unknown');self.assertFalse(store.db.execute('SELECT 1 FROM runs').fetchone())
            self.assertEqual(attachments.usage()['sessionBytes'],3)
            with self.assertRaises(ProjectFault):attachments.remove(attachments.row(data['requestId'],True)['id'])

    def test_offline_copy_restore_has_portable_hashes_and_preserves_owner_bound_native_mount(self):
        with self.open() as store:
            meta=self.upload(store);run,_=admit(store,self.sid,self.message([meta['id']]),self.providers)
            transition(store,run['id'],'completed');source=Path(Attachments(store,self.sid).access(meta['id'])['path']).read_bytes()
        restored=self.root/'RestoredProjects';shutil.copytree(self.projects,restored)
        with closing(SessionStore(restored,self.r4os,self.pid)) as store:
            self.assertEqual(Path(Attachments(store,self.sid).access(meta['id'])['path']).read_bytes(),source)
            self.assertEqual(history(store,self.sid)[0]['sha256'],meta['sha256'])
            self.assertIn(str(restored),mounts(store,self.sid,json.loads(get_run(store,run['id'])['config']))[0][0])
            self.assertNotIn(str(self.projects),encode(store.history(self.sid)))

    @unittest.skipIf(os.getuid()!=0,'Host backup source is intentionally root-readable; run this isolated fixture separately as root.')
    def test_actual_existing_backup_and_isolated_restore_preserve_files_refs_and_sources(self):
        sys.path.insert(1,str(Path(__file__).resolve().parents[3]/'Tools/Backup'))
        import backup
        from restore import restore
        with self.open() as store:
            meta=self.upload(store);run,_=admit(store,self.sid,self.message([meta['id']]),self.providers)
            transition(store,run['id'],'completed')
            raw=Path(Attachments(store,self.sid).access(meta['id'])['path']).read_bytes()
        root=self.root/'own-backup-root';root.mkdir()
        for source in backup.SOURCES:
            path=root/source
            if source=='AGENTS.md':path.write_text('Own backup fixture')
            else:path.mkdir(parents=True,exist_ok=True)
        shutil.copytree(self.projects,root/'App/Data/Projects',dirs_exist_ok=True)
        excluded=root/'App/Data/Skills/own';excluded.mkdir(parents=True);(excluded/'keep.txt').write_text('excluded')
        paths=backup.Paths(root,self.root/'mount',self.root/'mount/backup',self.root/'backup-state',self.root/'backup.lock')
        paths.mount.mkdir()
        result=backup.run(paths,lambda _p:('own-fixture-mount',),datetime(2026,10,28,4,tzinfo=ZoneInfo('Europe/Berlin')))
        archive=paths.destination/result['archive'];restored=self.root/'isolated-zip-restore';restore(archive,restored)
        self.assertEqual(len(backup.SOURCES),7);self.assertNotIn('App/Data/Skills',backup.SOURCES)
        self.assertFalse((restored/'App/Data/Skills').exists())
        with closing(SessionStore(restored/'App/Data/Projects',self.r4os,self.pid)) as store:
            self.assertEqual(Path(Attachments(store,self.sid).access(meta['id'])['path']).read_bytes(),raw)
            self.assertEqual(history(store,self.sid),[frozen(meta)])
            self.assertFalse(get_run(store,run['id'])['busy'])

    def test_confirmed_project_deletion_removes_only_owned_session_attachments(self):
        import delete as deletion
        with self.open() as store:
            meta=self.upload(store)
            with self.assertRaises(sqlite3.IntegrityError),store.db:store.db.execute('DELETE FROM sessions WHERE id=?',(self.sid,))
        foreign=self.root/'foreign-attachment';foreign.write_text('keep')
        (self.projects/self.pid/'Sessions/foreign-link').symlink_to(foreign)
        with patch.object(deletion,'AGENT_RUNTIME',self.root/'own-agent-runtime'),patch.object(deletion,'DEVELOPMENT_RUNTIME',self.root/'own-dev-runtime'),patch.object(deletion,'worker_check'):
            result=deletion.delete(self.projects,self.pid,{'revision':1,'confirm':True},{'agents':True,'development':True})
        self.assertTrue(result['deleted']);self.assertFalse((self.projects/self.pid).exists())
        self.assertEqual(foreign.read_text(),'keep')
        with self.assertRaises(ProjectFault):
            with self.open():pass


if __name__=='__main__':unittest.main()
