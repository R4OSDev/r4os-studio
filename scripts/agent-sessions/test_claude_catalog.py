"""Canonical native facts never manufacture entitlement, context or image support."""
import unittest
import uuid
import json
from unittest.mock import patch

from claude_catalog import normalize
from store import ProjectFault
from claude_auth_store import AuthStore
from claude_auth import status_result
from claude_runtime import profile
import test_runs as fixtures


class NativeCatalog(unittest.TestCase):
    def test_resolved_identifiers_aliases_effort_and_missing_capabilities_stay_explicit(self):
        provider={'id':str(uuid.uuid4()),'revision':1,'account':None}
        native={'value':'default','resolvedModel':'claude-own-fixture','displayName':'Default','description':'Own metadata',
            'supportsEffort':True,'supportedEffortLevels':['low','high'],'supportsFastMode':True}
        value=normalize([native,{**native,'value':'own','displayName':'Own model'}],provider,str(uuid.uuid4()))
        self.assertEqual(len(value['models']),1);model=value['models'][0]
        self.assertEqual(model['id'],'claude-own-fixture');self.assertEqual(model['aliases'],['default','own'])
        self.assertEqual(model['name'],'Own model');self.assertEqual(model['efforts'],['','low','high'])
        self.assertIsNone(model['contextWindow']);self.assertEqual(model['imageInputs'],'unknown')
        self.assertFalse(model['available']);self.assertFalse(model['fastModeAvailable']);self.assertFalse(value['sessionModelsQualified'])
        self.assertEqual(model['entitlement'],'not-verified-by-model-advertisement')
        with self.assertRaises(ProjectFault):normalize([{**native,'supportedEffortLevels':['unlimited']}],provider,str(uuid.uuid4()))

    def test_authenticated_cache_is_original_account_bound_and_cannot_enable_execution(self):
        f=fixtures.Runs('test_concurrent_retry_snapshot_stop_and_replay');f.setUp();self.addCleanup(f.tearDown)
        f.providers.chmod(0o700);auth=AuthStore(f.providers)
        with patch('claude_provider_store.installed',return_value={'id':profile()['id']}):
            provider=auth.create({'requestId':str(uuid.uuid4()),'name':'Own native catalog'})['provider']
        self.assertIsNone(auth.latest_catalog(provider['id']))
        def connect(action,org='own-org',models=None):
            current=auth.get(provider['id']);rid=str(uuid.uuid4())
            auth.begin(provider['id'],{'requestId':rid,'revision':current['revision'],'action':action},'a'*64)
            status,account,_=status_result(json.dumps({'loggedIn':True,'authMethod':'claude.ai','apiProvider':'firstParty',
                'configDirectory':'/config','subscriptionType':'pro','email':'own@example.test','orgId':org,'orgName':'Own fixture'}),0)
            return auth.finish(provider['id'],rid,'complete',status=status,account=account,models=models)
        rows=[{'value':'own','resolvedModel':'claude-own','displayName':'Own','description':'Own native metadata'}]
        receipt=connect('catalog',models=rows);catalog=receipt['catalog']
        self.assertEqual(auth.latest_catalog(provider['id']),catalog)
        from session_store import providers,provider_models
        self.assertTrue(any(p['id']==provider['id'] for p in providers(f.providers)))
        selected=provider_models(f.providers,provider['id']);self.assertEqual(selected[0]['id'],'claude-own')
        self.assertFalse(selected[0]['available'])
        with f.open() as store,self.assertRaises(ProjectFault):
            store.create({'requestId':str(uuid.uuid4()),'name':'Cannot bypass unavailable model','providerId':provider['id'],
                'model':'claude-own','effort':''},f.providers)
        connect('status',org='different-org')
        self.assertIsNone(auth.latest_catalog(provider['id']))
        self.assertEqual(provider_models(f.providers,provider['id']),[])
