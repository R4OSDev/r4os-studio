"""OpenRouter config isolation, original revisions and capability gates, no inference."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from api_provider_store import ApiProviders
from api_catalog import Catalogs
from openrouter_policy import policy
from provider_errors import describe
from store import ProjectFault

def request():return str(uuid.uuid4())

class OpenRouter(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.api=ApiProviders(self.root);self.catalog=Catalogs(self.root)
        self.input={'requestId':request(),'name':'Own OpenRouter','kind':'openrouter','baseUrl':'https://openrouter.ai/api/v1',
            'protocol':'chat-completions','auth':'bearer','key':'fixture-only-openrouter-key',
            'openrouter':{'order':['owned/provider'],'only':['owned/provider'],'allowFallbacks':False,'attribution':None}}
        self.provider=self.api.mutate('create',None,self.input)['provider'];self.ident=self.provider['id']

    def test_policy_masking_original_revisions_and_metadata_binding(self):
        self.assertEqual(self.provider['openrouter'],policy(self.input['openrouter']))
        self.assertNotIn(self.input['key'],json.dumps(self.provider))
        data={'requestId':request(),'providerRevision':1};self.catalog.start_refresh(self.ident,data)
        self.assertEqual(self.catalog.binding(self.ident,data['requestId'])['openrouter'],self.provider['openrouter'])
        modified={'requestId':request(),'revision':1,'openrouter':{'only':['different'],'order':[],'allowFallbacks':True,'attribution':None}}
        current=self.api.mutate('update',self.ident,modified)['provider'];self.assertEqual(current['revision'],2)
        self.assertEqual(self.catalog.binding(self.ident,data['requestId'])['openrouter'],self.provider['openrouter'])
        self.assertEqual(self.catalog.finish(self.ident,data['requestId'],[])['state'],'failed')
        self.assertEqual(self.api.receipt(self.ident,modified['requestId'])['provider'],current)

    def test_invalid_policy_is_atomic_and_old_records_are_read_without_migration(self):
        for bad in [{'unexpected':'header'},{'only':['same','same']},{'order':['https://foreign.invalid']},{'allowFallbacks':'true'},
                {'attribution':{'url':'https://example.test?key=private','title':'Owned'}},
                {'attribution':{'url':'https://example.test','title':'Own\r\nHeader'}}]:
            with self.subTest(bad=bad),self.assertRaises(ProjectFault):self.api.mutate('update',self.ident,{'requestId':request(),'revision':1,'openrouter':bad})
            self.assertEqual(self.api.get(self.ident),self.provider)
        old=copy.deepcopy(self.provider);old.pop('openrouter')
        with self.api.connect(write=True) as db:db.execute('UPDATE providers SET data=? WHERE id=?',(json.dumps(old),self.ident))
        path=self.api.root/'Providers.sqlite';before=path.read_bytes()
        self.assertEqual(self.api.get(self.ident)['openrouter'],policy());self.assertEqual(path.read_bytes(),before)
        with self.assertRaises(ProjectFault):self.api.mutate('create',None,{**self.input,'requestId':request(),'kind':'local','baseUrl':'http://127.0.0.1:11434/v1'})

    def test_plain_chat_required_before_native_catalog_or_admission(self):
        facts={'id':'owned/exact','name':'Owned','contextWindow':8192,'maxOutputTokens':2048,
            'capabilities':{'text':'supported','functionTools':'supported','streaming':'supported','reasoning':'unsupported'}}
        self.catalog.save_model(self.ident,{'requestId':request(),'providerRevision':1,'catalogRevision':0,'model':facts})
        self.assertTrue(self.catalog.listing(self.ident)['models'][0]['available']);self.assertEqual(len(self.catalog.native_models(self.ident)),1)
        facts.update(capabilities={**facts['capabilities'],'reasoning':'supported'},efforts=['low'],defaultEffort='low')
        self.catalog.save_model(self.ident,{'requestId':request(),'providerRevision':1,'catalogRevision':1,'model':facts})
        self.assertEqual(self.catalog.native_models(self.ident),[])
        self.assertIn('reasoning tool-history',' '.join(self.catalog.listing(self.ident)['models'][0]['unavailableReasons']))
        self.api.mutate('update',self.ident,{'requestId':request(),'revision':1,'protocol':'responses'})
        self.assertEqual(self.catalog.native_models(self.ident),[])

    def test_safe_api_errors_do_not_change_subscription_messages_or_authorize_replay(self):
        for status,word in [(401,'API key'),(402,'billing'),(403,'access'),(429,'rate'),(503,'unavailable')]:
            error={'codexErrorInfo':{'httpConnectionFailed':{'httpStatusCode':status}},'message':'fixture-only-private-text'}
            result=describe(error,api=True);self.assertIn(word,result['text']);self.assertNotIn('private-text',result['text'])
            if status!=503:self.assertFalse(result['transientCandidate'])
        self.assertIn('sign in',describe({'codexErrorInfo':'unauthorized'},api=False)['text'])
        for code in ['api_account_required','api_access_denied','api_service_unavailable']:
            result=describe({'codexErrorInfo':'other','message':json.dumps({'error':{'code':code}})},api=True)
            self.assertFalse(result['transientCandidate']);self.assertNotEqual(result['code'],'unknown')

if __name__=='__main__':unittest.main()
