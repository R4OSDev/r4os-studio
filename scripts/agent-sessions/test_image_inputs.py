"""Native image admission, mounts and immutable original Send identity."""
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import uuid
from PIL import Image
import test_runs
from attachment_store import Attachments
from image_inputs import selected,history,mounts,native_input,model_images
from launch import attachment_guard
from profile import CODEX_VERSION,CODEX_SHA256,LEGACY_PROFILE,prepare
from run_store import admit,get_run,transition
from session_store import encode,provider_models
from store import ProjectFault
from worker import Worker


class ImageInputs(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        test_runs.Runs.setUp(self)
        with self.open() as store,store.db:
            store.db.execute('UPDATE sessions SET engine=?',(encode({'profile':LEGACY_PROFILE,'version':CODEX_VERSION,'sha256':CODEX_SHA256}),))
    tearDown=test_runs.Runs.tearDown
    open=test_runs.Runs.open

    def upload(self,store,color='purple'):
        out=io.BytesIO();Image.new('RGB',(3,2),color).save(out,'PNG');raw=out.getvalue()
        result=Attachments(store,self.sid).upload({'requestId':str(uuid.uuid4()),'name':'Own picture.png','mediaType':'image/png',
            'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},io.BytesIO(raw))
        self.assertEqual(result['state'],'ready',result);return result['attachment']

    def message(self,ids,text=''):
        return {'requestId':str(uuid.uuid4()),'revision':1,'text':text,'attachments':ids,'nativeImageInputs':1}

    async def test_image_only_freezes_actual_metadata_and_has_one_original_user_identity(self):
        with self.open() as store:
            image=self.upload(store);data=self.message([image['id']]);run,fresh=admit(store,self.sid,data,self.providers)
            self.assertTrue(fresh);row=get_run(store,run['id']);config=json.loads(row['config'])
            self.assertEqual(config['attachments'][0]['sha256'],image['sha256']);self.assertEqual(config['attachments'][0]['mode'],'localImage')
            self.assertTrue(config['imageContext']);self.assertEqual(store.db.execute('PRAGMA user_version').fetchone()[0],1)
            messages=store.history(self.sid)['items'];self.assertEqual(len(messages),1)
            self.assertEqual(messages[0]['id'],'user-'+data['requestId']);self.assertEqual(messages[0]['text'],'')
            self.assertEqual(native_input(store,run['id'],config),[{'type':'localImage','path':'/attachments/'+image['id']+'.png'}])
            duplicate,fresh=admit(store,self.sid,data,self.providers);self.assertFalse(fresh);self.assertEqual(duplicate['id'],run['id'])
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],1)
            self.assertEqual(len(history(store,self.sid)),1)

    async def test_order_and_text_are_bound_to_original_frozen_send_and_draft_removal_keeps_reference(self):
        with self.open() as store:
            first=self.upload(store);second=self.upload(store,'blue');data=self.message([second['id'],first['id']],'Actual user request')
            run,_=admit(store,self.sid,data,self.providers);config=json.loads(get_run(store,run['id'])['config'])
            self.assertEqual([v['id'] for v in config['attachments']],[second['id'],first['id']])
            self.assertEqual(native_input(store,run['id'],config)[0],{'type':'text','text':'Actual user request'})
            for altered in ({**data,'text':'Changed text'},{**data,'attachments':list(reversed(data['attachments']))}):
                with self.assertRaises(ProjectFault):admit(store,self.sid,altered,self.providers)
            Attachments(store,self.sid).remove(first['id'])
            self.assertEqual(len(mounts(store,self.sid,config)),2)
            transition(store,run['id'],'completed')
            next_run,_=admit(store,self.sid,{'requestId':str(uuid.uuid4()),'revision':1,'text':'Next explicit text turn'},self.providers)
            self.assertTrue(json.loads(get_run(store,next_run['id'])['config'])['imageContext'])
            self.assertEqual(len(mounts(store,self.sid,json.loads(get_run(store,next_run['id'])['config']))),2)
            self.assertEqual(store.row(self.sid)['engine'],encode({'profile':LEGACY_PROFILE,'version':CODEX_VERSION,'sha256':CODEX_SHA256}))

    async def test_incompatible_or_unknown_model_metadata_rejects_before_admission_and_preserves_uploads(self):
        with self.open() as store:
            image=self.upload(store);data=self.message([image['id']])
            cache=self.providers/self.provider/'models_cache.json';catalog=json.loads(cache.read_text())
            for raw in (['text'],[],['audio'],'image',None,['invalid']):
                catalog['models'][0]['input_modalities']=raw;cache.write_text(encode(catalog))
                with self.assertRaises(ProjectFault):admit(store,self.sid,data,self.providers)
                self.assertFalse(store.db.execute('SELECT 1 FROM runs').fetchone())
                self.assertEqual(len(Attachments(store,self.sid).listing()['attachments']),1)
            catalog['models'][0].pop('input_modalities');cache.write_text(encode(catalog))
            self.assertEqual(provider_models(self.providers,self.provider)[0]['imageInputs'],'supported')
            self.assertTrue(admit(store,self.sid,data,self.providers)[1])

    async def test_changed_image_is_detected_before_any_native_worker_process(self):
        with self.open() as store:
            image=self.upload(store);run,_=admit(store,self.sid,self.message([image['id']]),self.providers)
            path=store.directory/self.sid/'Attachments'/image['id']/'original.png';path.write_bytes(b'changed after Send')
        w=Worker({'projects':str(self.projects),'r4os':str(self.r4os),'providers':str(self.providers),'projectId':self.pid,'runId':run['id'],'release':'own'})
        with patch('worker.prepare') as prepare,patch('worker.CodexRPC') as native:
            await w.run();prepare.assert_not_called();native.assert_not_called()
        with self.open() as store:
            self.assertEqual(get_run(store,run['id'])['state'],'failed')
            self.assertIn('missing or changed',get_run(store,run['id'])['error'])
            self.assertEqual(store.history(self.sid)['items'][0]['attachments'][0]['sha256'],image['sha256'])

    async def test_native_namespace_has_only_sent_images_readonly_without_other_private_files(self):
        with self.open() as store:
            image=self.upload(store);unsent=self.upload(store,'red')
            run,_=admit(store,self.sid,self.message([image['id']]),self.providers);config=json.loads(get_run(store,run['id'])['config'])
            approved=mounts(store,self.sid,config);self.assertEqual(len(approved),1)
            home=self.root/'own-native-home';home.mkdir();(home/'models_cache.json').write_text(encode({'models':[{'slug':'fixture'}]}))
            dummy=self.root/'dummy-codex';dummy.write_text('not executed')
            with patch('profile.digest',return_value=CODEX_SHA256):
                args,_=prepare(dummy,home,self.root/'own-native-state',json.loads(Path(__file__).with_name('features.json').read_text()),attachment_mounts=approved)
            args.insert(1,'--unshare-net');index=args.index('/bin/codex',args.index('--clearenv'))
            check='''import os,json
path=os.listdir('/attachments');assert len(path)==1
assert not os.path.exists(%r)
assert not os.path.exists('/attachments/%s.png')
try:open('/attachments/'+path[0],'wb');raise RuntimeError('image was writable')
except OSError:pass
print(json.dumps({'readonly':True,'onlySentImage':True}))
'''%(str(store.directory/self.sid/'Attachments'),unsent['id'])
            result=subprocess.run(args[:index]+['/usr/bin/python3','-I','-c',check],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr.decode());self.assertTrue(json.loads(result.stdout)['readonly'])

    async def test_current_uploads_need_explicit_qualified_send_and_goal_play_cannot_attach_drafts(self):
        with self.open() as store:
            first=self.upload(store);second=self.upload(store,'red');data=self.message([first['id']])
            with self.assertRaises(ProjectFault):admit(store,self.sid,{k:v for k,v in data.items() if k!='nativeImageInputs'},self.providers)
            self.assertFalse(store.db.execute('SELECT 1 FROM runs').fetchone());self.assertEqual(history(store,self.sid),[])
            with self.assertRaises(ProjectFault):admit(store,self.sid,{'mode':'goal','goalRequestId':str(uuid.uuid4()),'requestId':str(uuid.uuid4()),'revision':1,'attachments':[second['id']]},self.providers)
            with self.assertRaises(ProjectFault):admit(store,self.sid,self.message([first['id'],first['id']]),self.providers)
            with patch('image_inputs.MAX_RUN',1):
                with self.assertRaises(ProjectFault):admit(store,self.sid,data,self.providers)

    async def test_old_release_guard_blocks_image_conversation_and_preserves_other_text_sessions(self):
        with self.open() as store:
            release=self.root/'old-release';(release/'scripts/agent-sessions').mkdir(parents=True)
            meta={'projects':str(self.projects),'projectId':self.pid,'sessionId':self.sid}
            attachment_guard(meta,release)
            image=self.upload(store);admit(store,self.sid,self.message([image['id']]),self.providers)
            with self.assertRaises(SystemExit):attachment_guard(meta,release)
            attachment_guard({**meta,'sessionId':str(uuid.uuid4())},release)
            (release/'scripts/agent-sessions/image_inputs.py').write_text('qualified file presence fixture')
            attachment_guard(meta,release)
            self.assertEqual(Attachments(store,self.sid).listing()['attachments'][0]['sha256'],image['sha256'])

    async def test_explicit_native_modality_default_and_audio_enum_are_qualified_without_model_names(self):
        self.assertEqual(model_images({}),'supported')
        self.assertEqual(model_images({'input_modalities':['audio','image']}),'supported')
        self.assertEqual(model_images({'input_modalities':['text']}),'unsupported')
        self.assertEqual(model_images({'input_modalities':'image'}),'unknown')

    async def test_native_catalog_modalities_match_frozen_admission_and_refresh_stale_public_metadata(self):
        home=self.root/'own-provider-home';home.mkdir();model={'slug':'fixture','input_modalities':['text']}
        source=home/'models_cache.json';source.write_text(encode({'models':[model]}));state=self.root/'native-state'
        dummy=self.root/'not-executed';dummy.write_text('fixture')
        features=json.loads(Path(__file__).with_name('features.json').read_text())
        with patch('profile.digest',return_value=CODEX_SHA256):
            prepare(dummy,home,state,features,model='fixture')
            model['input_modalities']=['text','image'];source.write_text(encode({'models':[model]}))
            prepare(dummy,home,state,features,model='fixture',image_modalities=['text','image'])
            self.assertEqual(json.loads((state/'models.json').read_text())['models'][0]['input_modalities'],['text','image'])
            with self.assertRaises(ValueError):prepare(dummy,home,state,features,model='fixture',image_modalities=['image'])
