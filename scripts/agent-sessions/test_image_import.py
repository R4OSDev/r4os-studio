"""Actual isolated conversion and FD publication; fixed PNG bytes, no provider."""
import asyncio
import base64
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import unittest
import uuid
from unittest.mock import patch
from PIL import Image
import test_runs
from generated_images import GeneratedImages
from image_import import import_image,validate
from owner import open_lock
from profile import IMAGE_PROFILE,CODEX_VERSION,CODEX_SHA256,permission_tools
from run_store import admit,transition
from session_store import encode
from store import ProjectFault
from worker import Worker

class Imports(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        test_runs.Runs.setUp(self)
        with self.open() as store:
            settings=json.loads(store.row(self.sid)['settings']);settings['permissions']={'studio.'+n:True for n in permission_tools(IMAGE_PROFILE)}
            with store.db:store.db.execute('UPDATE sessions SET settings=?,engine=?',(encode(settings),encode({'profile':IMAGE_PROFILE,'version':CODEX_VERSION,'sha256':CODEX_SHA256})))
            run,_=admit(store,self.sid,self.data,self.providers)
        self.worker=Worker({'projects':str(self.projects),'r4os':str(self.r4os),'projectId':self.pid,'runId':run['id'],'release':'owned fixture'});self.worker.thread_id='owned-thread';self.worker.turn_id='owned-turn'
        self.worker.lease=open_lock(self.projects,'project',self.pid);fcntl.flock(self.worker.lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        transition(self.worker.store,run['id'],'running',turn_id=self.worker.turn_id)
        stream=io.BytesIO();Image.new('RGBA',(80,40),(10,40,230,128)).save(stream,format='PNG');self.png=stream.getvalue()
        self.images=GeneratedImages(self.worker.store,self.sid);self.image=self.images.accept(run['id'],self.worker.thread_id,{'id':'image','status':'completed','result':base64.b64encode(self.png).decode()})
        self.args={'imageId':self.image['id'],'path':'Assets/Image.png','format':'original'}
    open=test_runs.Runs.open
    async def asyncTearDown(self):
        self.worker.lease.close();self.worker.store.close();test_runs.Runs.tearDown(self)
    async def call(self,args=None,call='owned-import'):
        return await import_image(self.worker,args or self.args,call)
    async def test_actual_original_copy_and_tool_retry_have_one_effect(self):
        params={'threadId':self.worker.thread_id,'turnId':self.worker.turn_id,'namespace':None,'tool':'studio_import_generated_image','callId':'owned-import','arguments':self.args}
        first=await self.worker.tool(params);self.assertTrue(first['success']);path=self.worker.store.workspace/self.args['path'];inode=path.stat().st_ino
        second=await self.worker.tool(params);self.assertEqual(first,second);self.assertEqual(path.stat().st_ino,inode);self.assertEqual(path.read_bytes(),self.png)
        self.assertEqual(self.images.path(self.image['id']).read_bytes(),self.png);self.assertEqual(len(list((self.images.root()/'Imports').glob('*.json'))),1)
        self.images.check_capacity()
    async def test_actual_bitmap_ico_and_rgba_outputs_preserve_aspect_alpha_and_reproduce(self):
        ico={**self.args,'path':'Assets/Icon.ico','format':'ico','options':{'width':64,'height':64,'fit':'contain'}}
        first=await self.call(ico,'ico');path=self.worker.store.workspace/ico['path'];raw=path.read_bytes();self.assertEqual(struct.unpack_from('<I',raw,22)[0],40);self.assertEqual(struct.unpack_from('<H',raw,36)[0],32);self.assertNotIn(b'\x89PNG',raw[:70])
        with Image.open(path) as image:self.assertEqual(image.size,(64,64));self.assertEqual(image.convert('RGBA').getpixel((0,0))[3],0)
        other=await self.call({**ico,'path':'Assets/Icon2.ico'},'ico2');self.assertEqual(first['generatedAsset']['sha256'],other['generatedAsset']['sha256'])
        result=await self.call({**self.args,'path':'Assets/Scene.rgba','format':'rgba32','options':{'width':160,'background':'#00000000'}},'rgba');meta=result['generatedAsset'];self.assertEqual((meta['width'],meta['height'],meta['stride'],meta['pixelOrder']),(160,80,640,'RGBA'))
        self.assertEqual(len((self.worker.store.workspace/'Assets/Scene.rgba').read_bytes()),160*80*4)
        cover=await self.call({**self.args,'path':'Assets/Cover.png','format':'png','options':{'width':32,'height':32,'fit':'cover','background':'#ffffff'}},'cover');self.assertFalse(cover['generatedAsset']['transparent'])
    async def test_create_only_and_exact_target_hash_replace(self):
        await self.call();target=self.worker.store.workspace/self.args['path'];target.write_bytes(b'actual user change')
        with self.assertRaises(ProjectFault):await self.call(call='create-again')
        with self.assertRaises(ProjectFault):await self.call({**self.args,'expectedTargetHash':'0'*64},'wrong-hash')
        self.assertEqual(target.read_bytes(),b'actual user change')
        expected=hashlib.sha256(target.read_bytes()).hexdigest();result=await self.call({**self.args,'expectedTargetHash':expected},'replace');self.assertTrue(result['success']);self.assertEqual(target.read_bytes(),self.png)
    async def test_denied_write_foreign_image_traversal_links_and_active_terminal_leave_targets(self):
        self.worker.config['permissions']['studio.write_file']=False
        with self.assertRaises(ProjectFault):await self.call()
        self.worker.config['permissions']['studio.write_file']=True
        for value in ('../outside.png','Assets/../outside.png','/Assets/out.png','Assets/link\\out.png'):
            with self.assertRaises(ProjectFault):await self.call({**self.args,'path':value})
        with self.assertRaises(ProjectFault):await self.call({**self.args,'imageId':str(uuid.uuid4())})
        external=self.root/'external';external.mkdir();secret=external/'Image.png';secret.write_bytes(b'untouched');(self.worker.store.workspace/'Assets').symlink_to(external)
        with self.assertRaises(OSError):await self.call()
        self.assertEqual(secret.read_bytes(),b'untouched');(self.worker.store.workspace/'Assets').unlink();(self.worker.store.workspace/'Assets').mkdir();os.link(secret,self.worker.store.workspace/self.args['path'])
        with self.assertRaises(ProjectFault):await self.call({**self.args,'expectedTargetHash':hashlib.sha256(b'untouched').hexdigest()})
        self.assertEqual(secret.read_bytes(),b'untouched')
    async def test_concurrent_target_change_is_restored_and_publication_journal_preserved(self):
        await self.call();target=self.worker.store.workspace/self.args['path'];old=hashlib.sha256(target.read_bytes()).hexdigest()
        import image_import
        original=image_import.exchange;changed=False
        def raced(a,an,b,bn,flags):
            nonlocal changed
            if flags==2 and not changed:changed=True;target.write_bytes(b'concurrent user edit')
            return original(a,an,b,bn,flags)
        with patch('image_import.exchange',side_effect=raced):
            with self.assertRaises(ProjectFault):await self.call({**self.args,'expectedTargetHash':old},'race')
        self.assertEqual(target.read_bytes(),b'concurrent user edit');self.assertEqual(self.images.path(self.image['id']).read_bytes(),self.png)
        records=[json.loads(p.read_text()) for p in (self.images.root()/'Imports').glob('*.json')];self.assertTrue(any(p['phase']=='committing' for p in records))
    async def test_missing_folder_permission_and_invalid_options_do_not_publish(self):
        self.worker.config['permissions']['studio.create_directory']=False
        with self.assertRaises(ProjectFault):await self.call()
        self.assertFalse((self.worker.store.workspace/'Assets').exists())
        for options in ({'width':True},{'background':None},{'background':'url(http://invalid)'},{'fit':'stretch'}):
            with self.assertRaises(ProjectFault):validate({**self.args,'format':'png','options':options})

if __name__=='__main__':unittest.main()
