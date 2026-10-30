"""Owned retirement, original receipts and native credential interlocks."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from claude_auth import ClaudeAuth,auth_home,status_result
from claude_auth_store import AuthStore
from claude_provider_store import account_identity
from claude_run_leases import ClaudeRunLeases
from claude_runtime import profile
from store import ProjectFault

OWNER='a'*64;OTHER='b'*64
SIGNED_OUT=b'{"loggedIn":false,"authMethod":"none"}'
SIGNED_IN={'loggedIn':True,'authMethod':'claude.ai','apiProvider':'firstParty','configDirectory':'/config',
    'subscriptionType':'pro','email':'own@example.test','orgId':'own-org','orgName':'Own account'}
def rid():return str(uuid.uuid4())


class ClaudeRemoval(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.manager=ClaudeAuth(Path(self.temp.name));self.addAsyncCleanup(self.manager.close)
        self.create={'requestId':rid(),'name':'Own Claude'}
        with patch('claude_provider_store.installed',return_value={'id':profile()['id']}):
            self.provider=self.manager.store.create(self.create)['provider']
        self.ident=self.provider['id'];self.input={'requestId':rid(),'revision':1,'action':'remove','confirmName':'Own Claude'}

    async def finished(self):
        async with asyncio.timeout(2):
            while self.manager.busy:await asyncio.sleep(.005)

    async def test_empty_home_removal_original_creation_and_auth_cannot_resurrect(self):
        earlier={'requestId':rid(),'revision':1,'action':'status'}
        self.manager.store.begin(self.ident,earlier,OWNER)
        self.manager.store.finish(self.ident,earlier['requestId'],'complete')
        with patch('claude_auth.installed',side_effect=AssertionError('Removal of an unused identity must not create a native home')):
            await self.manager.start(self.ident,self.input,OWNER);await self.finished()
            original=self.manager.view(self.ident,self.input['requestId'],OWNER)
            self.assertEqual(original['state'],'removed')
            self.manager.jobs={'own-capacity-one':{},'own-capacity-two':{}}
            try:self.assertEqual(await self.manager.start(self.ident,self.input,OWNER),original)
            finally:self.manager.jobs={}
        self.assertFalse((self.manager.store.root/self.ident).exists())
        self.assertEqual(self.manager.store.listing(),[])
        self.assertEqual(self.manager.store.receipt(self.create['requestId'])['state'],'deleted')
        with patch('claude_provider_store.installed',side_effect=AssertionError('Old creation must not verify/create a runtime')):
            self.assertEqual(self.manager.store.create(self.create)['state'],'deleted')
        for action in (lambda:self.manager.store.get(self.ident),
                lambda:self.manager.store.operation(self.ident,earlier['requestId'],OWNER),
                lambda:self.manager.store.begin(self.ident,earlier,OWNER)):
            with self.assertRaises(ProjectFault) as caught:action()
            self.assertEqual(caught.exception.code,410)
        with self.assertRaises(ProjectFault):self.manager.view(self.ident,self.input['requestId'],OTHER)

    async def test_exact_revision_name_and_capacity_leave_no_phantom_operation(self):
        for extra in ({'revision':2},{'confirmName':'Different provider'},{'confirmName':'Own Claude '}):
            with self.assertRaises(ProjectFault):self.manager.store.begin(self.ident,self.input|extra,OWNER)
        with self.assertRaises(ProjectFault) as caught:self.manager.store.begin(self.ident,self.input,OWNER,allow_new=False)
        self.assertEqual(caught.exception.code,429)
        with self.assertRaises(ProjectFault):self.manager.store.operation(self.ident,self.input['requestId'],OWNER)
        self.assertEqual(self.manager.store.get(self.ident),self.provider)
        result,_=self.manager.store.begin(self.ident,self.input,OWNER)
        self.assertEqual(self.manager.store.begin(self.ident,self.input,OWNER,allow_new=False),(result,False))
        self.manager.store.recover()
        with self.assertRaises(ProjectFault):self.manager.store.begin(self.ident,self.input|{'requestId':rid()},OWNER)
        check={'requestId':rid(),'revision':1,'action':'status'};self.manager.store.begin(self.ident,check,OWNER)
        self.manager.store.finish(self.ident,check['requestId'],'complete',status='not-connected')
        self.assertEqual(self.manager.store.operation(self.ident,self.input['requestId'],OWNER)['state'],'reconciled')
        self.assertEqual(self.manager.store.get(self.ident)['revision'],2)

    async def test_native_logout_evidence_retains_history_and_ignores_foreign_credentials(self):
        root=auth_home(self.manager.store,self.ident);history=root/'Home'/'own-history';history.write_text('original native UUID/history');history.chmod(0o600)
        foreign=Path(self.temp.name)/'OtherNativeLogin';foreign.write_text('own foreign credential fixture');foreign.chmod(0o600)
        calls=[]
        async def native(job,args,login=False):
            self.assertNotIn('--share-net',args);self.assertNotIn(str(foreign),args)
            calls.append(args[-2:]);return (b'Logged out',0) if args[-1]=='logout' else (SIGNED_OUT,1)
        with patch('claude_auth.installed',return_value={'native':'/owned/pinned/claude'}),patch.object(self.manager,'execute',side_effect=native):
            await self.manager.start(self.ident,self.input,OWNER);await self.finished()
        self.assertEqual(self.manager.view(self.ident,self.input['requestId'],OWNER)['state'],'removed')
        self.assertEqual(calls,[['status','--json'],['auth','logout'],['status','--json']])
        self.assertEqual(history.read_text(),'original native UUID/history');self.assertEqual(foreign.read_text(),'own foreign credential fixture')

    async def test_stale_connected_native_status_and_unconfirmed_logout_preserve_provider(self):
        auth_home(self.manager.store,self.ident)
        for raw,code in ((json.dumps(SIGNED_IN).encode(),0),(b'private malformed response',1)):
            request=self.input|{'requestId':rid()};calls=[]
            async def native(job,args,login=False):calls.append(args[-1]);return raw,code
            with patch('claude_auth.installed',return_value={'native':'/owned/pinned/claude'}),patch.object(self.manager,'execute',side_effect=native):
                await self.manager.start(self.ident,request,OWNER);await self.finished()
            result=self.manager.view(self.ident,request['requestId'],OWNER)
            self.assertEqual(result['state'],'failed');self.assertEqual(calls,['--json'])
            self.assertEqual(self.manager.store.get(self.ident),self.provider)
            self.assertNotIn('private malformed',json.dumps(result))

    async def test_original_worker_or_queue_lease_blocks_changes_until_confirmed_end(self):
        store=self.manager.store;check={'requestId':rid(),'revision':1,'action':'status'};store.begin(self.ident,check,OWNER)
        status,account,_=status_result(json.dumps(SIGNED_IN),0)
        provider=store.finish(self.ident,check['requestId'],'complete',status=status,account=account)['provider']
        leases=ClaudeRunLeases(self.temp.name)
        binding={key:rid() for key in ('studioSessionId','ownerId','runId','requestId','nativeSessionId')}
        binding.update(providerId=self.ident,providerRevision=provider['revision'],runtimeProfileId=provider['runtimeProfileId'],
            ownerType='project',accountIdentity=account_identity(provider['account']))
        leases.reserve(binding);worker={'release':'owned-release','pid':12345,'birth':'owned-birth'}
        for lease_state in ('reserved','active','unknown'):
            if lease_state=='active':leases.claim(binding,worker)
            if lease_state=='unknown':leases.finish_lease(binding,worker,False)
            for action in ('connect','disconnect','status'):
                with self.assertRaises(ProjectFault):store.begin(self.ident,{'requestId':rid(),'revision':provider['revision'],'action':action},OWNER)
        leases.finish_lease(binding,worker,True)
        disconnect={'requestId':rid(),'revision':provider['revision'],'action':'disconnect'};store.begin(self.ident,disconnect,OWNER)
        provider=store.finish(self.ident,disconnect['requestId'],'complete',status='not-connected')['provider']
        with self.assertRaises(ProjectFault):leases.reserve(binding|{'runId':rid()})
        await self.manager.start(self.ident,self.input|{'revision':provider['revision']},OWNER);await self.finished()
        self.assertEqual(self.manager.view(self.ident,self.input['requestId'],OWNER)['state'],'removed')
        with self.assertRaises(ProjectFault):leases.reserve(binding|{'runId':rid()})
        with leases.leases() as db:self.assertEqual(json.loads(db.execute('SELECT binding FROM claude_run_leases').fetchone()[0]),binding)

    async def test_auth_deadline_requires_explicit_status_without_relogin_or_losing_original_outcome(self):
        data={'requestId':rid(),'revision':1,'action':'connect'};calls=[]
        async def deadline(job,args,login=False):calls.append(args[-1]);raise asyncio.TimeoutError()
        with patch('claude_auth.installed',return_value={'native':'/owned/pinned/claude'}),patch.object(self.manager,'execute',side_effect=deadline):
            await self.manager.start(self.ident,data,OWNER);await self.finished()
            original=self.manager.view(self.ident,data['requestId'],OWNER)
            self.assertEqual(original['state'],'expired');self.assertEqual(len(calls),1)
            self.assertEqual(await self.manager.start(self.ident,data,OWNER),original)
            revision=original['provider']['revision']
            for action in ('connect','disconnect'):
                with self.assertRaises(ProjectFault):await self.manager.start(self.ident,{'requestId':rid(),'revision':revision,'action':action},OWNER)
            self.assertEqual(len(calls),1)
        check={'requestId':rid(),'revision':revision,'action':'status'}
        self.manager.store.begin(self.ident,check,OWNER);self.manager.store.finish(self.ident,check['requestId'],'complete',status='not-connected')
        reconciled=self.manager.view(self.ident,data['requestId'],OWNER)
        self.assertEqual(reconciled['state'],'expired');self.assertEqual(reconciled['reconciledBy'],check['requestId'])
        # A fresh explicit request is admitted only after that status observation.
        pending,_=self.manager.store.begin(self.ident,{'requestId':rid(),'revision':revision+1,'action':'connect'},OWNER)
        self.assertEqual(pending['state'],'pending')
        self.manager.store.finish(self.ident,pending['requestId'],'cancelled')
