"""Owned auth protocol cases; no real account, token or model invocation."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
import uuid

from claude_auth import ClaudeAuth,auth_home,command,native_url,status_result
from claude_auth_store import AuthStore
from claude_runtime import profile
from store import ProjectFault

OWNER='a'*64;OTHER='b'*64;STATE='original-native-sign-in-state'
URL='https://claude.com/cai/oauth/authorize?'+urlencode({'client_id':'owned-client','code':'true','response_type':'code',
    'code_challenge':'owned-challenge','code_challenge_method':'S256','redirect_uri':'https://platform.claude.com/oauth/code/callback',
    'scope':'user:profile user:inference','state':STATE})
STATUS={'loggedIn':True,'authMethod':'claude.ai','apiProvider':'firstParty','configDirectory':'/config',
    'subscriptionType':'pro','email':'owned@example.test','orgId':'owned-org','orgName':'Own account'}
def rid():return str(uuid.uuid4())


class AuthProtocol(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=AuthStore(self.root)
        with patch('claude_provider_store.installed',return_value={'id':profile()['id']}):
            self.provider=self.store.create({'requestId':rid(),'name':'Own plan'})['provider']
        self.ident=self.provider['id']

    def test_plan_requires_native_auth_method_backend_plan_and_exact_config(self):
        status,account,_=status_result(json.dumps(STATUS),0)
        self.assertEqual(status,'connected');self.assertEqual(account['plan'],'pro')
        for change in ({'authMethod':'api_key'},{'authMethod':'oauth_token'},{'apiProvider':'bedrock'},
                {'apiKeySource':'ANTHROPIC_API_KEY'},{'subscriptionType':'team'},{'subscriptionType':None},{'configDirectory':'/foreign'},
                {'forcedLoginMethod':'console'}):
            self.assertEqual(status_result(json.dumps(STATUS|change),0)[0],'unsupported')
        self.assertEqual(status_result(json.dumps({'loggedIn':False,'authMethod':'none','apiProvider':'firstParty'}),1)[0],'not-connected')
        self.assertEqual(status_result(json.dumps(STATUS),1)[0],'unsupported')
        for raw,code in [('not json',0),(json.dumps(STATUS|{'orgId':None}),0)]:
            with self.assertRaises(ProjectFault):status_result(raw,code)

    def test_native_url_is_ephemeral_fixed_origin_pkce_and_code_binding(self):
        self.assertEqual(native_url('Native sign-in: '+URL),(URL,STATE))
        for value in (URL.replace('claude.com','example.test'),URL.replace('/cai/oauth/authorize','/other'),
                URL.replace('S256','plain'),URL.replace('https%3A%2F%2Fplatform.claude.com','https%3A%2F%2Fevil.test'),URL+'#fragment'):
            self.assertIsNone(native_url(value))

    def test_original_owner_revision_replay_recovery_and_no_secret_receipts(self):
        data={'requestId':rid(),'revision':1,'action':'connect'}
        value,fresh=self.store.begin(self.ident,data,OWNER);self.assertTrue(fresh)
        self.assertEqual(self.store.begin(self.ident,data,OWNER),(value,False))
        for owner in (OTHER,'not-owner'):
            with self.assertRaises(ProjectFault):self.store.operation(self.ident,data['requestId'],owner)
        with self.assertRaises(ProjectFault):self.store.begin(self.ident,data|{'action':'disconnect'},OWNER)
        with self.assertRaises(ProjectFault):self.store.begin(self.ident,{'requestId':rid(),'revision':1,'action':'status'},OWNER)
        self.store.recover();self.assertEqual(self.store.operation(self.ident,data['requestId'],OWNER)['state'],'unconfirmed')
        with self.assertRaises(ProjectFault):self.store.begin(self.ident,{'requestId':rid(),'revision':1,'action':'connect'},OWNER)
        check,_=self.store.begin(self.ident,{'requestId':rid(),'revision':1,'action':'status'},OWNER)
        self.store.finish(self.ident,check['requestId'],'complete',status='not-connected')
        self.assertEqual(self.store.operation(self.ident,data['requestId'],OWNER)['state'],'reconciled')
        self.assertEqual(self.store.get(self.ident)['revision'],2)
        self.assertEqual(list(self.store.root.iterdir()),[self.store.root/'Providers.sqlite'])
        raw=(self.store.root/'Providers.sqlite').read_bytes()
        for forbidden in (URL.encode(),STATE.encode(),b'accessToken',b'refreshToken',b'authorizationUrl'):self.assertNotIn(forbidden,raw)

    def test_private_home_refuses_links_and_native_environment_replaces_overrides(self):
        root=auth_home(self.store,self.ident)
        self.assertEqual(root.stat().st_mode&0o777,0o700)
        foreign=self.root/'foreign';foreign.write_text('owned fixture');foreign.chmod(0o600)
        (root/'Config/link').symlink_to(foreign)
        with self.assertRaises(ProjectFault):auth_home(self.store,self.ident)
        self.assertEqual(foreign.read_text(),'owned fixture')
        args=command({'native':'/owned/pinned/claude'},root,'connect')
        self.assertIn('--clearenv',args);self.assertIn('--claudeai',args);self.assertNotIn('--console',args)
        self.assertEqual(args[-6:],['/claude','--setting-sources','','auth','login','--claudeai'])
        for forbidden in ('ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_PROFILE','CLAUDE_CODE_OAUTH_TOKEN','HTTPS_PROXY'):
            self.assertNotIn(forbidden,args)
        self.assertNotIn('/etc/claude-code',args);self.assertNotIn(str(foreign),args)


class AuthLifecycle(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.manager=ClaudeAuth(Path(self.temp.name));self.addAsyncCleanup(self.manager.close)
        with patch('claude_provider_store.installed',return_value={'id':profile()['id']}):
            self.provider=self.manager.store.create({'requestId':rid(),'name':'Own native fixture'})['provider']
        self.ident=self.provider['id'];self.native=patch('claude_auth.installed',return_value={'native':'/owned/pinned/claude'})
        self.native.start();self.addCleanup(self.native.stop)

    async def until(self,condition):
        async with asyncio.timeout(2):
            while not condition():await asyncio.sleep(.005)

    async def test_code_and_cancel_are_bound_once_and_never_persisted(self):
        class Input:
            def write(self,value):self.value=value
            async def drain(self):pass
        class Child:returncode=0;stdin=Input()
        async def controlled(job,args,login=False):
            if login:
                job.update(child=Child(),url=URL,state=STATE)
                await self.until(lambda:job['submitted'] or job['cancel'])
                if job['cancel']:raise asyncio.CancelledError()
                self.assertEqual(job['child'].stdin.value,('own-once-code#'+STATE+'\n').encode())
                return b'Login successful.',0
            return json.dumps(STATUS).encode(),0
        with patch.object(self.manager,'execute',side_effect=controlled):
            op=await self.manager.start(self.ident,{'requestId':rid(),'revision':1,'action':'connect'},OWNER);request=op['requestId']
            await self.until(lambda:self.manager.jobs[self.ident]['url'] is not None)
            self.assertEqual(self.manager.view(self.ident,request,OWNER)['authorizationUrl'],URL)
            for code,owner in [('own-once-code#'+STATE,OTHER),('wrong#'+'x'*30,OWNER)]:
                with self.assertRaises(ProjectFault):await self.manager.submit(self.ident,request,owner,code)
            await self.manager.submit(self.ident,request,OWNER,'own-once-code#'+STATE)
            with self.assertRaises(ProjectFault):await self.manager.submit(self.ident,request,OWNER,'own-once-code#'+STATE)
            await self.until(lambda:not self.manager.busy)
            result=self.manager.view(self.ident,request,OWNER)
            self.assertEqual(result['state'],'complete');self.assertEqual(result['provider']['status'],'connected');self.assertFalse(result['provider']['enabled'])
            self.assertNotIn('authorizationUrl',result)
            raw=(self.manager.store.root/'Providers.sqlite').read_bytes()
            for secret in (b'own-once-code',STATE.encode(),URL.encode()):self.assertNotIn(secret,raw)
            next_op=await self.manager.start(self.ident,{'requestId':rid(),'revision':2,'action':'connect'},OWNER)
            await self.until(lambda:self.manager.jobs[self.ident]['url'] is not None)
            cancelled=await self.manager.cancel(self.ident,next_op['requestId'],OWNER)
            self.assertEqual(cancelled['state'],'cancelled');self.assertEqual(cancelled['provider']['status'],'reauthentication-required')
            self.assertFalse(self.manager.busy)

    async def test_failure_never_reports_a_connection_or_restarts_a_request(self):
        calls=[]
        async def fail(job,args,login=False):calls.append(args);return b'private native failure details',1
        with patch.object(self.manager,'execute',side_effect=fail):
            data={'requestId':rid(),'revision':1,'action':'connect'}
            await self.manager.start(self.ident,data,OWNER);await self.until(lambda:not self.manager.busy)
            result=self.manager.view(self.ident,data['requestId'],OWNER)
            self.assertEqual(result['state'],'failed');self.assertIsNone(result['provider']['account'])
            again=await self.manager.start(self.ident,data,OWNER)
            self.assertEqual(again,result);self.assertEqual(len(calls),1)
            self.assertNotIn('private native failure',json.dumps(result))
