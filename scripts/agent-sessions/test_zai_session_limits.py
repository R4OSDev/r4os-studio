"""Owned project/skill views share actual quota and keep session boundaries."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import Mock
import json
from api_provider_store import ApiProviders
from zai_policy import BASE_URL
from zai_quota import Quota
from zai_session_limits import dispatch
from store import ProjectFault
from test_zai_quota import rid,body
import test_runs as project_fixtures
import test_skills as skill_fixtures


class SessionLimits(unittest.TestCase):
    def test_key_rotation_during_original_run_hides_new_account_but_preserves_original_receipt(self):
        import test_zai_quota as fixtures
        fixture=fixtures.ZaiQuota();fixture.setUp()
        try:
            request,_=fixture.start();fixture.store.finish(fixture.provider['id'],request['requestId'],body=body())
            selected={k:fixture.provider[k] for k in ('id','revision','credentialRevision')}
            fixture.api.mutate('update',fixture.provider['id'],{'requestId':rid(),'revision':1,'key':'own-rotated-view-key'})
            sid=rid();store=Mock();store.get.return_value={'providerId':fixture.provider['id'],'model':'glm-5.3','engine':{'api':{
                'providerId':fixture.provider['id'],'baseUrl':BASE_URL,'protocol':'chat-completions'}}}
            store.db.execute.return_value.fetchone.return_value={'config':json.dumps({'apiProvider':selected})}
            host=SimpleNamespace(config={'providers':str(fixture.api.parent)})
            with self.assertRaisesRegex(ProjectFault,'credentials changed'):
                asyncio.run(dispatch(host,store,sid,'session_zai_limits'))
            self.assertEqual(asyncio.run(dispatch(host,store,sid,'session_zai_limit_receipt',request_id=request['requestId']))['state'],'complete')
        finally:fixture.doCleanups()

    def test_both_owner_types_read_the_same_original_without_inference_or_cross_owner_access(self):
        for fixture_type in (project_fixtures.Runs,skill_fixtures.Skills):
            fixture=fixture_type();fixture.setUp()
            try:
                fixture.providers.chmod(0o700)
                api=ApiProviders(fixture.providers)
                provider=api.mutate('create',None,{'requestId':rid(),'name':'Own view','kind':'zai-coding-plan',
                    'baseUrl':BASE_URL,'protocol':'chat-completions','auth':'bearer','key':'own-view-key'})['provider']
                quota=Quota(fixture.providers);request={'requestId':rid(),'providerRevision':1}
                quota.start_refresh(provider['id'],request);quota.finish(provider['id'],request['requestId'],body=body())
                with fixture.open() as store,patch('session_store.engine',return_value={'available':True,'version':'own','sha256':'a'*64}):
                    session=store.create({'requestId':rid(),'name':'Own ZAI view','providerId':provider['id'],'model':'glm-5.3','effort':'low'},fixture.providers)
                    host=SimpleNamespace(config={'providers':str(fixture.providers)})
                    limits=asyncio.run(dispatch(host,store,session['id'],'session_zai_limits'))
                    self.assertEqual(limits,quota.listing(provider['id'],'glm-5.3'))
                    self.assertEqual(limits['limits'][1]['remaining'],0)
                    self.assertEqual(asyncio.run(dispatch(host,store,session['id'],'session_zai_limit_receipt',request_id=request['requestId']))['state'],'complete')
                    with self.assertRaises(ProjectFault):asyncio.run(dispatch(host,store,rid(),'session_zai_limits'))
                    with api.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM leases').fetchone()[0],0)
            finally:fixture.tearDown()


if __name__=='__main__':unittest.main()
