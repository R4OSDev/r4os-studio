"""Own isolated subscription credentials and routing, without any real account."""
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from api_endpoint import endpoint
from api_provider_store import ApiProviders
from store import ProjectFault
from zai_policy import BASE_URL


class ZaiProvider(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=ApiProviders(Path(self.temp.name))
        self.data={'requestId':str(uuid.uuid4()),'name':'Own subscription','kind':'zai-coding-plan',
                   'baseUrl':BASE_URL,'protocol':'chat-completions','auth':'bearer','key':'own-fixture-key'}

    def test_exact_subscription_target_and_no_account_fallback(self):
        self.assertEqual(endpoint(BASE_URL+'/', 'zai-coding-plan')['baseUrl'], BASE_URL)
        for url in ('https://api.z.ai/api/paas/v4','https://api.z.ai/api/v1',
                    'https://api.z.ai:444/api/coding/paas/v4','https://open.bigmodel.cn/api/coding/paas/v4'):
            with self.subTest(url=url),self.assertRaises(ProjectFault):endpoint(url,'zai-coding-plan')
        for field,value in (('protocol','responses'),('auth','none'),('server','ollama')):
            with self.subTest(field=field),self.assertRaises(ProjectFault):
                self.store.mutate('create',None,{**self.data,field:value})
        self.assertEqual(self.store.listing(),[])

    def test_masked_idempotent_create_rotation_and_original_disconnect(self):
        first=self.store.mutate('create',None,self.data)
        self.assertEqual(first,self.store.mutate('create',None,self.data))
        provider=first['provider'];ident=provider['id']
        self.assertNotIn('own-fixture-key',json.dumps(self.store.listing()))
        for field,value in (('protocol','responses'),('auth','none'),('baseUrl','https://api.z.ai/api/paas/v4')):
            with self.subTest(field=field),self.assertRaises(ProjectFault):
                self.store.mutate('update',ident,{'requestId':str(uuid.uuid4()),'revision':1,field:value})
        self.assertEqual(self.store.get(ident),provider)
        rotated=self.store.mutate('update',ident,{'requestId':str(uuid.uuid4()),'revision':1,'key':'own-second-key'})['provider']
        self.assertEqual(rotated['credentialRevision'],2)
        request={'requestId':str(uuid.uuid4()),'revision':2}
        self.assertEqual(self.store.mutate('disconnect',ident,request)['state'],'pending')
        self.assertEqual(self.store.mutate('disconnect',ident,request,finish=True)['state'],'complete')
        self.assertFalse(self.store.get(ident)['keyConfigured'])


if __name__=='__main__':unittest.main()
