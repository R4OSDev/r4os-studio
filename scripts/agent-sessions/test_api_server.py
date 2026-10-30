"""Isolated server-profile admission and metadata compatibility, no inference."""
from contextlib import closing
import json
import sqlite3
import tempfile
from pathlib import Path
import unittest
import uuid

from api_catalog import Catalogs
from api_provider_store import ApiProviders
from api_server import server
from store import ProjectFault

def request():return str(uuid.uuid4())


class ServerProfiles(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.api=ApiProviders(self.root);self.catalog=Catalogs(self.root)

    def create(self,**extra):
        return self.api.mutate('create',None,{'requestId':request(),'name':'Own server','kind':'local',
            'baseUrl':'http://127.0.0.1:11434/reverse/proxy/v1','protocol':'responses','auth':'none',**extra})['provider']

    def test_old_records_read_as_custom_without_rewriting_original_revisions(self):
        provider=self.create()
        with closing(sqlite3.connect(self.api.root/'Providers.sqlite')) as db,db:
            data=json.loads(db.execute('SELECT data FROM providers').fetchone()[0]);data.pop('server')
            db.execute('UPDATE providers SET data=?',(json.dumps(data),))
        before=(self.api.root/'Providers.sqlite').read_bytes()
        self.assertEqual(self.api.get(provider['id'])['server'],'custom')
        self.assertEqual((self.api.root/'Providers.sqlite').read_bytes(),before)

    def test_profiles_and_optional_auth_use_original_revision_receipts(self):
        for profile in ('custom','ollama','lm-studio'):
            provider=self.create(server=profile,auth='bearer',key='only-owned-fixture')
            self.assertEqual(self.api.get(provider['id'])['server'],profile)
            self.assertNotIn('only-owned-fixture',json.dumps(provider))
            data={'requestId':request(),'revision':1,'auth':'none','key':None}
            updated=self.api.mutate('update',provider['id'],data)
            self.assertEqual(updated,self.api.receipt(provider['id'],data['requestId']))
            self.assertFalse(updated['provider']['keyConfigured']);self.assertTrue(updated['provider']['enabled'])

    def test_invalid_profile_or_cross_provider_fields_refused(self):
        for value in (None,1,{},'Ollama',''):
            with self.assertRaises(ProjectFault):server(value)
            with self.assertRaises(ProjectFault):self.create(server=value)
        with self.assertRaises(ProjectFault):self.create(kind='openrouter',baseUrl='https://openrouter.ai/api/v1',server='ollama')
        from provider_errors import describe
        error={'codexErrorInfo':{'httpConnectionFailed':{'httpStatusCode':404}}}
        self.assertEqual(describe(error,api=True)['code'],'apiModelOrRouteUnavailable')
        self.assertEqual(describe(error,api=False)['code'],'httpConnectionFailed')

    def test_metadata_only_ids_do_not_qualify_unconfirmed_server_model(self):
        for profile in ('ollama','lm-studio'):
            provider=self.create(server=profile)
            facts={'id':'owned/exact:tag','capabilities':{'text':'supported','functionTools':'supported','streaming':'supported'}}
            revision=0
            for patch,available in (({},False),({'capabilities':{**facts['capabilities'],'reasoning':'unsupported'}},False),
                ({'contextWindow':8192,'capabilities':{**facts['capabilities'],'reasoning':'unsupported'}},True),
                ({'contextWindow':8192,'capabilities':{**facts['capabilities'],'functionTools':'unsupported','reasoning':'unsupported'}},False)):
                self.catalog.save_model(provider['id'],{'requestId':request(),'providerRevision':1,'catalogRevision':revision,'model':{**facts,**patch}})
                revision+=1
                self.assertEqual(self.catalog.listing(provider['id'])['models'][0]['available'],available)
                self.assertEqual(bool(self.catalog.native_models(provider['id'])),available)

    def test_metadata_binding_freezes_exact_profile_and_reverse_proxy_path(self):
        provider=self.create(server='ollama')
        data={'requestId':request(),'providerRevision':1}
        result,fresh=self.catalog.start_refresh(provider['id'],data)
        self.assertTrue(fresh);binding=self.catalog.binding(provider['id'],data['requestId'])
        self.assertEqual(binding['server'],'ollama');self.assertTrue(binding['baseUrl'].endswith('/reverse/proxy/v1'))
        self.api.mutate('update',provider['id'],{'requestId':request(),'revision':1,'server':'lm-studio'})
        self.assertEqual(self.catalog.binding(provider['id'],data['requestId']),binding)
        self.assertEqual(self.catalog.start_refresh(provider['id'],data),(result,False))
