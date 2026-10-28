"""Lost local projections are recovered from original bounded native receipts only."""
import json
import unittest
from unittest.mock import patch
import test_generated_images
from generated_images import GeneratedImages
from image_recovery import reconcile
from profile import CODEX_SHA256,CODEX_VERSION
from run_store import admit,transition,get_run
from session_store import encode

class Recovery(unittest.TestCase):
    setUp=test_generated_images.Generated.setUp
    tearDown=test_generated_images.Generated.tearDown
    open=test_generated_images.Generated.open
    png=test_generated_images.Generated.png
    native=test_generated_images.Generated.native

    def seed(self,store):
        run,_=admit(store,self.sid,self.data,self.providers)
        config=json.loads(get_run(store,run['id'])['config']);config.update(nativeImageGeneration=True,engine={'version':CODEX_VERSION,'sha256':CODEX_SHA256})
        with store.db:
            store.db.execute('UPDATE runs SET config=?,turn_id=? WHERE id=?',(encode(config),'own-turn',run['id']))
            store.db.execute('UPDATE sessions SET thread_id=? WHERE id=?',('own-thread',self.sid))
        transition(store,run['id'],'unknown')
        root=store.directory/self.sid/'Codex/native';root.mkdir(parents=True)
        path=root/'rollout.jsonl'
        meta={'type':'session_meta','payload':{'id':'own-thread','cli_version':CODEX_VERSION}}
        event={'type':'event_msg','payload':{'type':'item_completed','thread_id':'own-thread','turn_id':'own-turn','item':{'type':'Extension','kind':'image_gen.generation',**self.native()}}}
        path.write_text(encode(meta)+'\n'+encode(event)+'\n')
        return run,path,event

    def test_lost_registry_or_item_recovers_once_without_native_process_or_generation(self):
        with self.open() as store:
            run,path,event=self.seed(store);original=path.read_bytes()
            with patch('asyncio.create_subprocess_exec',side_effect=AssertionError('Recovery cannot start a process')):reconcile(store,self.sid)
            images=GeneratedImages(store,self.sid);meta=images.list()[0];inode=images.path(meta['id']).stat().st_ino
            cursor=store.history(self.sid)['cursor'];reconcile(store,self.sid)
            self.assertEqual(store.history(self.sid)['cursor'],cursor);self.assertEqual(images.path(meta['id']).stat().st_ino,inode)
            with store.db:store.db.execute("DELETE FROM items WHERE item_id='own-image'")
            reconcile(store,self.sid);self.assertTrue(any(i.get('generatedImage') for i in store.history(self.sid)['items']))
            self.assertEqual(path.read_bytes(),original)

    def test_foreign_turn_or_thread_and_partial_record_never_create_an_image(self):
        with self.open() as store:
            run,path,event=self.seed(store);lines=path.read_text().splitlines()
            event['payload']['turn_id']='foreign-turn';path.write_text(lines[0]+'\n'+encode(event)+'\n'+ '{"partial":')
            reconcile(store,self.sid);self.assertEqual(GeneratedImages(store,self.sid).list(),[])
            event['payload']['turn_id']='own-turn';event['payload']['thread_id']='foreign-thread';path.write_text(lines[0]+'\n'+encode(event)+'\n')
            reconcile(store,self.sid);self.assertEqual(GeneratedImages(store,self.sid).list(),[])

    def test_busy_run_waits_for_original_owner_and_unqualified_engine_is_preserved(self):
        with self.open() as store:
            run,path,event=self.seed(store)
            with store.db:store.db.execute('UPDATE runs SET busy=1 WHERE id=?',(run['id'],))
            reconcile(store,self.sid);self.assertFalse(GeneratedImages(store,self.sid).list())
            with store.db:
                store.db.execute('UPDATE runs SET busy=0 WHERE id=?',(run['id'],))
                config=json.loads(store.db.execute('SELECT config FROM runs WHERE id=?',(run['id'],)).fetchone()[0]);config['engine']['sha256']='0'*64
                store.db.execute('UPDATE runs SET config=? WHERE id=?',(encode(config),run['id']))
            reconcile(store,self.sid);self.assertFalse(GeneratedImages(store,self.sid).list());self.assertTrue(path.exists())

if __name__=='__main__':unittest.main()
