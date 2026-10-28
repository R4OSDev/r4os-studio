"""Actual seven-source backup/restore and confirmed owner deletion, no inference."""
from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
import test_generated_images
from generated_images import GeneratedImages
from run_store import admit,transition
from session_store import SessionStore
from store import ProjectFault

class Lifecycle(unittest.TestCase):
    setUp=test_generated_images.Generated.setUp
    tearDown=test_generated_images.Generated.tearDown
    open=test_generated_images.Generated.open
    png=test_generated_images.Generated.png
    native=test_generated_images.Generated.native

    def seed(self):
        with self.open() as store:
            run,_=admit(store,self.sid,self.data,self.providers)
            image=GeneratedImages(store,self.sid).accept(run['id'],'own-thread',self.native())
            transition(store,run['id'],'completed')
            root=store.directory/self.sid/'GeneratedImages/Imports';root.mkdir();(root/('a'*64+'.json')).write_text('{"own":"original publication receipt"}')
            (store.workspace/'assets').mkdir();(store.workspace/'assets/original.png').write_bytes(self.png())
            return image

    @unittest.skipIf(os.getuid()!=0,'Existing backup configuration is root-readable.')
    def test_actual_zip_restore_retains_private_original_and_receipt_but_not_skill_scope(self):
        self.seed();sys.path.insert(1,str(Path(__file__).resolve().parents[3]/'Tools/Backup'))
        import backup
        from restore import restore
        root=self.root/'own-backup-root';root.mkdir()
        for source in backup.SOURCES:
            path=root/source
            if source=='AGENTS.md':path.write_text('Own backup fixture')
            else:path.mkdir(parents=True,exist_ok=True)
        shutil.copytree(self.projects,root/'App/Data/Projects',dirs_exist_ok=True)
        excluded=root/'App/Data/Skills/own';excluded.mkdir(parents=True);(excluded/'keep.txt').write_text('outside existing scope')
        paths=backup.Paths(root,self.root/'mount',self.root/'mount/backup',self.root/'backup-state',self.root/'backup.lock');paths.mount.mkdir()
        result=backup.run(paths,lambda _p:('own-fixture-mount',),datetime(2026,10,28,4,tzinfo=ZoneInfo('Europe/Berlin')))
        restored=self.root/'restored';restore(paths.destination/result['archive'],restored)
        self.assertEqual(len(backup.SOURCES),7);self.assertFalse((restored/'App/Data/Skills').exists())
        with closing(SessionStore(restored/'App/Data/Projects',self.r4os,self.pid)) as store:
            images=GeneratedImages(store,self.sid);image=images.list()[0];self.assertEqual(images.path(image['id']).read_bytes(),self.png())
            self.assertEqual((images.root()/'Imports'/('a'*64+'.json')).read_text(),'{"own":"original publication receipt"}')
            self.assertEqual((store.workspace/'assets/original.png').read_bytes(),self.png())

    def test_only_confirmed_project_delete_removes_owned_media_and_preserves_foreign_links(self):
        image=self.seed()
        with self.open() as store:
            with self.assertRaises(sqlite3.IntegrityError),store.db:store.db.execute('DELETE FROM sessions WHERE id=?',(self.sid,))
        foreign=self.root/'foreign-keep';foreign.write_text('preserve')
        (self.projects/self.pid/'Sessions/foreign-link').symlink_to(foreign)
        import delete as deletion
        with patch.object(deletion,'AGENT_RUNTIME',self.root/'own-agent-runtime'),patch.object(deletion,'DEVELOPMENT_RUNTIME',self.root/'own-dev-runtime'),patch.object(deletion,'worker_check'):
            result=deletion.delete(self.projects,self.pid,{'revision':1,'confirm':True},{'agents':True,'development':True})
        self.assertTrue(result['deleted']);self.assertFalse((self.projects/self.pid).exists());self.assertEqual(foreign.read_text(),'preserve')

if __name__=='__main__':unittest.main()
