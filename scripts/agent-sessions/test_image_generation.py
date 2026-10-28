"""Bound policy, readonly native RPC and additive setting; no paid inference."""
import json
import unittest
from unittest.mock import patch
import uuid
import test_runs
from image_generation import evaluate,inspect,freeze
from profile import CODEX_VERSION,CODEX_SHA256,IMAGE_PROFILE,IMAGE_SKILL_PROFILE,tools_for,permission_tools
from run_store import admit,get_run,transition
from session_store import encode
from store import ProjectFault

class ImageGeneration(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        test_runs.Runs.setUp(self)
        with self.open() as store,store.db:
            settings=json.loads(store.row(self.sid)['settings']);settings['permissions']={'studio.'+tool:True for tool in permission_tools(IMAGE_PROFILE)}
            store.db.execute('UPDATE sessions SET settings=?,engine=?',(encode(settings),encode({'profile':IMAGE_PROFILE,'version':CODEX_VERSION,'sha256':CODEX_SHA256})))
    tearDown=test_runs.Runs.tearDown
    open=test_runs.Runs.open
    def supported(self,session,bridge=True):return evaluate(session,{'imageInputs':'supported','inputModalities':['text','image']},{'imageGeneration':True},{'account':{'type':'chatgpt','planType':'plus'}},session['engine'],bridge)
    async def test_account_provider_modality_runtime_unknown_and_output_adapter_are_separate_gates(self):
        with self.open() as store:
            session=store.get(self.sid);model={'imageInputs':'supported','inputModalities':['text','image']};provider={'imageGeneration':True};account={'account':{'type':'chatgpt','planType':'plus'}}
            self.assertTrue(self.supported(session)['available']);self.assertTrue(self.supported(session,False)['qualified']);self.assertFalse(self.supported(session,False)['available'])
            for m,p,a,e in (({'imageInputs':'unsupported'},provider,account,session['engine']),(model,{'imageGeneration':False},account,session['engine']),(model,provider,{'account':{'type':'chatgpt','planType':'free'}},session['engine']),(model,provider,{'account':{'type':'apiKey'}},session['engine']),(model,provider,account,{'version':'other','sha256':CODEX_SHA256})):
                self.assertFalse(evaluate(session,m,p,a,e,True)['available'])
            self.assertEqual(evaluate(session,model,{},account,session['engine'],True)['state'],'unknown')
            legacy={**session,'engine':{**session['engine'],'profile':'studio-tools-v10'}};self.assertIn('New session required',self.supported(legacy)['reason'])
            self.assertNotIn('email',encode(self.supported(session)))
            changed=evaluate(session,model,provider,{'account':{'type':'chatgpt','planType':'plus','email':'other@example.invalid'}},session['engine'],True)
            self.assertNotEqual(changed['accountSha256'],self.supported(session)['accountSha256'])
    async def test_missing_setting_defaults_on_explicit_off_survives_name_edit_and_invalid_types_reject(self):
        with self.open() as store:
            original=store.row(self.sid)['settings'];self.assertTrue(store.get(self.sid)['imageGenerationEnabled']);self.assertEqual(store.row(self.sid)['settings'],original)
            changed=store.update(self.sid,{'revision':1,'imageGenerationEnabled':False},self.providers);self.assertFalse(changed['imageGenerationEnabled'])
            changed=store.update(self.sid,{'revision':changed['revision'],'name':'Own renamed'},self.providers);self.assertFalse(changed['imageGenerationEnabled'])
            for value in ('true',1,None):
                with self.assertRaises(ProjectFault):store.update(self.sid,{'revision':changed['revision'],'imageGenerationEnabled':value},self.providers)
    async def test_frozen_binding_off_and_original_retry_do_not_requalify_or_change_history(self):
        with self.open() as store:
            session=store.get(self.sid);cap=self.supported(session);data={'requestId':str(uuid.uuid4()),'revision':session['revision'],'text':'Own explicit request','imageGenerationSettings':1}
            run,fresh=admit(store,self.sid,data,self.providers,cap);self.assertTrue(fresh);config=get_run(store,run['id'])['config'];self.assertTrue(json.loads(config)['nativeImageGeneration'])
            old,fresh=admit(store,self.sid,data,self.providers,{**cap,'available':False});self.assertFalse(fresh);self.assertEqual(get_run(store,run['id'])['config'],config)
            transition(store,run['id'],'completed');session=store.update(self.sid,{'revision':1,'imageGenerationEnabled':False},self.providers)
            second,_=admit(store,self.sid,{**data,'requestId':str(uuid.uuid4()),'revision':session['revision']},self.providers,self.supported(session));self.assertFalse(json.loads(get_run(store,second['id'])['config'])['nativeImageGeneration'])
            self.assertFalse(freeze(session,{**cap,'model':'another'})['available']);self.assertEqual(len([item for item in store.history(self.sid)['items'] if item['type']=='user']),2)
    async def test_foreign_session_provider_and_skill_profile_do_not_grant_project_access(self):
        self.assertIn('list_generated_images',tools_for(IMAGE_SKILL_PROFILE));self.assertNotIn('import_generated_image',tools_for(IMAGE_SKILL_PROFILE));self.assertNotIn('build_project',tools_for(IMAGE_SKILL_PROFILE))
        with self.open() as store,patch('image_generation.prepare') as native:
            with self.assertRaises(ProjectFault):await inspect(store,str(uuid.uuid4()),self.providers)
            with self.assertRaises(ProjectFault):await inspect(store,self.sid,self.providers,{'providerId':str(uuid.uuid4())})
            native.assert_not_called()

    async def test_unavailable_worker_output_adapter_fails_before_any_native_process(self):
        with self.open() as store:
            session=store.get(self.sid);run,_=admit(store,self.sid,{'requestId':str(uuid.uuid4()),'revision':1,'text':'Own fixture','imageGenerationSettings':1},self.providers,self.supported(session))
        from worker import Worker
        worker=Worker({'projects':str(self.projects),'r4os':str(self.r4os),'providers':str(self.providers),'projectId':self.pid,'runId':run['id'],'release':'own'})
        with patch('worker.prepare') as native_prepare,patch('worker.CodexRPC') as native:
            await worker.run();native_prepare.assert_not_called();native.assert_not_called()
        with self.open() as store:self.assertEqual(get_run(store,run['id'])['state'],'failed')

    async def test_capability_reader_uses_only_initialize_account_and_provider_rpcs_no_thread_or_turn(self):
        calls=[]
        class Native:
            def __init__(self,*args):pass
            async def start(self):calls.append('initialize')
            async def request(self,method,params,**kwargs):
                calls.append(method)
                if method=='modelProvider/capabilities/read':return {'imageGeneration':True,'webSearch':True}
                assert method=='account/read' and params=={'refreshToken':False};return {'account':{'type':'chatgpt','planType':'plus','email':'must-not-leak@example.invalid'}}
            async def close(self):calls.append('close')
        with self.open() as store,patch('image_generation.prepare',return_value=([],{'version':CODEX_VERSION,'sha256':CODEX_SHA256})):
            before=store.row(self.sid)['thread_id'];cap=await inspect(store,self.sid,self.providers,rpc_factory=Native,bridge=True)
            self.assertTrue(cap['available']);self.assertEqual(store.row(self.sid)['thread_id'],before);self.assertNotIn('must-not-leak',encode(cap));self.assertFalse(store.db.execute('SELECT 1 FROM runs').fetchone())
            self.assertEqual(calls,['initialize','modelProvider/capabilities/read','account/read','close'])
            self.assertFalse(list((store.directory/self.sid).glob('.image-capability-*')))

if __name__=='__main__':unittest.main()
