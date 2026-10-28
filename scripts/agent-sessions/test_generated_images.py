import base64
import hashlib
import io
import json
import unittest
import uuid
from unittest.mock import patch
from PIL import Image
import test_runs
from run_store import admit,item
from generated_images import GeneratedImages,presentation,MAX_IMAGE,RPC_IMAGE_LIMIT
from store import ProjectFault

class Generated(unittest.TestCase):
    setUp=test_runs.Runs.setUp
    tearDown=test_runs.Runs.tearDown
    open=test_runs.Runs.open
    def png(self):
        out=io.BytesIO();Image.new('RGBA',(48,32),(3,77,200,120)).save(out,format='PNG');return out.getvalue()
    def native(self,raw=None):return {'id':'own-image','status':'completed','savedPath':'/codex/generated_images/own-thread/own-image.png','result':base64.b64encode(self.png() if raw is None else raw).decode()}
    def test_immutable_original_metadata_transparency_dedup_and_changed_item(self):
        with self.open() as store:
            run,_=admit(store,self.sid,self.data,self.providers);images=GeneratedImages(store,self.sid)
            first=images.accept(run['id'],'own-thread',self.native());self.assertEqual((first['width'],first['height'],first['transparent']),(48,32,True));self.assertEqual(first['sha256'],hashlib.sha256(self.png()).hexdigest())
            self.assertEqual(first,images.accept(run['id'],'own-thread',self.native()));self.assertEqual(len(images.list()),1);self.assertEqual(images.path(first['id']).read_bytes(),self.png());self.assertEqual(images.path(first['id']).stat().st_mode&0o777,0o600)
            with self.assertRaises(ProjectFault):images.accept(run['id'],'own-thread',self.native(b'changed'))
            images.path(first['id']).write_bytes(b'changed')
            with self.assertRaises(ProjectFault):images.path(first['id'])
    def test_foreign_identity_path_links_corruption_and_quota_preserve_data(self):
        with self.open() as store:
            run,_=admit(store,self.sid,self.data,self.providers);images=GeneratedImages(store,self.sid)
            for native in ({**self.native(),'savedPath':'/codex/auth.json'},{**self.native(),'result':'not base64'},self.native(b'not a png')):
                with self.assertRaises(ProjectFault):images.accept(run['id'],'own-thread',native)
            with self.assertRaises(ProjectFault):images.accept(str(uuid.uuid4()),'own-thread',self.native())
            with self.assertRaises(ProjectFault):images.get(str(uuid.uuid4()))
            with patch('generated_images.MAX_SESSION',1):
                with self.assertRaises(ProjectFault):images.accept(run['id'],'own-thread',self.native())
            external=self.root/'secret';external.write_bytes(b'untouched');(images.native_root()/'linked').symlink_to(external)
            with self.assertRaises((ProjectFault,ValueError)):images.check_capacity()
            self.assertEqual(external.read_bytes(),b'untouched')
    def test_published_orphan_reconciles_same_id_after_lost_database_receipt(self):
        with self.open() as store:
            run,_=admit(store,self.sid,self.data,self.providers);images=GeneratedImages(store,self.sid)
            first=images.accept(run['id'],'own-thread',self.native());path=images.path(first['id']);inode=path.stat().st_ino
            with store.db:store.db.execute('DELETE FROM generated_images')
            second=images.accept(run['id'],'own-thread',self.native());self.assertEqual(first['id'],second['id']);self.assertEqual(path.stat().st_ino,inode)
    def test_public_event_contains_only_validated_metadata_and_failure_is_bounded(self):
        with self.open() as store:
            run,_=admit(store,self.sid,self.data,self.providers)
            class Worker:pass
            worker=Worker();worker.store=store;worker.session_id=self.sid;worker.run_id=run['id'];worker.thread_id='own-thread'
            value=presentation(worker,self.native(),True);item(store,self.sid,run['id'],value)
            raw=json.dumps(store.history(self.sid));self.assertNotIn(self.native()['result'],raw);self.assertNotIn('/codex/',raw);self.assertEqual(value['generatedImage']['width'],48)
            failure=presentation(worker,{'id':'failed','status':'failed','failure':{'type':'usageLimitExceeded','opaque':'must not leak'},'result':'opaque'},True);self.assertEqual(failure['error'],'usageLimitExceeded');self.assertNotIn('opaque',json.dumps(failure))
    def test_storage_failure_retains_original_and_reconciles_without_regeneration(self):
        with self.open() as store:
            run,_=admit(store,self.sid,self.data,self.providers);images=GeneratedImages(store,self.sid)
            with patch('generated_images.sync',side_effect=OSError('owned failure')):
                with self.assertRaises(OSError):images.accept(run['id'],'own-thread',self.native())
            self.assertEqual(len(list(images.root().glob('*.image'))),1);self.assertFalse(images.list())
            meta=images.accept(run['id'],'own-thread',self.native());self.assertEqual(images.path(meta['id']).read_bytes(),self.png())
    def test_large_rpc_is_opt_in_and_outgoing_stays_bounded(self):
        from codex_rpc import CodexRPC
        rpc=CodexRPC([],None,None);self.assertEqual(rpc.inbound_limit,1048576);rpc.inbound_limit=RPC_IMAGE_LIMIT
        self.assertGreater(RPC_IMAGE_LIMIT,4*((MAX_IMAGE+2)//3));self.assertLessEqual(RPC_IMAGE_LIMIT,32*1024*1024)

if __name__=='__main__':unittest.main()
