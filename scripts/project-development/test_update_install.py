"""VERIFY gates, native live/batch outcomes, durable ownership and one-shot COMMIT."""
from contextlib import asynccontextmanager
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import uuid
from unittest.mock import AsyncMock,patch
from contracts import DevelopmentFault,UnconfirmedGuestEffect
from sysupd_text import parse
from test_sysupd import IDLE,capture
from update_install import Installation,Commit,component_proof
import update_state as state

def ident():return str(uuid.uuid4())

class NativeInstallation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.vm=ident();self.project=ident()
        class Store:
            root=self.root;projects=self.root/'Projects';r4os=self.root/'R4OS';id=self.project
            def update(this,job,state=None,**fields):return {'state':state,**fields}
        self.store=Store();self.job={'id':ident(),'projectRevision':1,'updateId':ident(),'binding':{'id':self.vm,'revision':'rev','imageId':'image','imageSha256':'a'*64}}
        self.target={'vmId':self.vm,'vmRevision':'rev','imageId':'image','imageSha256':'a'*64,'systemGeneration':None,'bootId':'boot'}
        self.component={'kind':'R4X','name':'DEMO','version':'1.0.0','target':'/SOFTWARE/DEMO/DEMO.R4X'}
        self.package={'id':ident(),'bytes':100,'sha256':'b'*64,'plan':{'metadata':{'packageId':'PKG','packageVersion':'2.0.0','targetRelease':'0.87.14'},'payloads':[{'component':self.component}],'requirements':[]}}
        self.item={'jobId':ident(),'package':self.package,'transfer':{'hostKeyFingerprint':'key','final':'/C/R4OS/UPDATE/INBOX/U123ABCD.R4U','guestPath':r'C:\R4OS\UPDATE\INBOX\U123ABCD.R4U'}}
        self.job['updateTransfers']=[self.item];self.current=IDLE;self.commands=[]
    def tearDown(self):self.temp.cleanup()
    async def run_stage(self,mode='live',count=1):
        test=self
        items=[self.item]
        if count==2:
            second=json.loads(json.dumps(self.item));second['jobId']=ident();second['package']['id']=ident()
            second['package']['plan']['metadata']['packageId']='PKG2';second['package']['plan']['payloads'][0]['component']['name']='DEMO2';items.append(second)
        self.job['updateTransfers']=items
        class SSH:
            def __init__(this,*args):pass
            async def __aenter__(this):return this
            async def __aexit__(this,*args):pass
            async def exec(this,command,**kw):
                test.commands.append(command)
                if command=='SYSUPD STATUS':
                    return capture(test.current if mode!='foreign' else IDLE.replace('dirs=ok','dirs=missing'))
                pkg=items[1 if command.endswith('SECOND.R4U') else 0]['package']
                meta=pkg['plan']['metadata']
                if command.startswith('SYSUPD VERIFY'):
                    if mode=='incompatible':return capture('SYSUPD VERIFY result: INCOMPATIBLE reason=requirement-missing',2)
                    return capture('SYSUPD VERIFY result: OK package='+meta['packageId']+' package-version=2.0.0 release=0.87.14 payloads=1 components=1 requires=0')
                if command.startswith('SYSUPD STAGE'):
                    if mode=='lost':return capture('',255)
                    if mode=='live':
                        test.current='SYSUPD STATUS: journal state=cleanup transaction=9 generation=9 release=0.87.14 package-version=2.0.0 components=1 priority=normal applied=1/1 reboot=no source=- dirs=ok'
                        return capture('SYSUPD APPLY result: OK package=PKG package-version=2.0.0 release=0.87.14 reboot=no transaction=9')
                    n=sum(x.startswith('SYSUPD STAGE') for x in test.commands)
                    test.current=r'SYSUPD STATUS: batch state=staged batch=7 progress=0/'+str(n)+r' release=0.87.14 inbox=C:\R4OS\UPDATE\INBOX staged=C:\R4OS\UPDATE\STAGED dirs=ok'
                    return capture('SYSUPD STAGE result: OK state=Staged package='+meta['packageId']+' batch=7 packages='+str(n)+' release=0.87.14')
                raise AssertionError(command)
        class Wire(SSH):
            exit_code=0
            async def get_hash(this,*args):return {'bytes':100,'sha256':'0'*64 if mode=='corrupt' else 'b'*64}
        if count==2:items[1]['transfer']['guestPath']=r'C:\R4OS\UPDATE\INBOX\SECOND.R4U'
        runner=Installation(self.store,self.job);observation={'hostKeyFingerprint':'key','status':parse('STATUS',capture(IDLE))}
        with patch('access.Access'),patch('update_install.capture_previous',new_callable=AsyncMock,return_value=[]),patch('access.SshTransport',SSH),patch('update_install.InboxSftp',Wire),patch('update_jobs.transfers',return_value=items),patch('vm_worker.guard'),patch('update_install.full_inventory',new_callable=AsyncMock,return_value=({'entries':[self.component]},[{'sha256':'x'}])),patch('update_verify.Observation.in_lease',new_callable=AsyncMock,return_value={'state':'completed','phase':'live_installed'}):
            error=None
            try:result=await runner.stage(None,self.target,observation)
            except DevelopmentFault as caught:error=caught;result=None
        return result,error,runner
    async def test_effective_apply_requires_terminal_transaction_and_exact_components(self):
        result,error,runner=await self.run_stage()
        self.assertIsNone(error);self.assertEqual(result['phase'],'live_installed');self.assertTrue(runner.value['installationConfirmed'])
        self.assertEqual(runner.value['transactions'],['9']);self.assertEqual(len(runner.value['liveProofs']),1)
        self.assertTrue(next(c for c in runner.value['commands'] if c['mutating'])['sent'])
    async def test_restart_stage_is_owned_awaiting_commit_without_install_success(self):
        result,error,runner=await self.run_stage('stage')
        self.assertIsNone(error);self.assertEqual(result['phase'],'awaiting_commit');self.assertEqual(runner.value['batchId'],'7')
        self.assertFalse(runner.value['installationConfirmed'])
        with self.assertRaises(DevelopmentFault):state.idle(self.store.projects,self.vm)
    async def test_explicit_two_package_group_uses_one_owned_native_batch(self):
        result,error,runner=await self.run_stage('stage',2)
        self.assertIsNone(error);self.assertEqual(len(runner.value['stagedPackageIds']),2);self.assertEqual(runner.value['batchId'],'7')
        self.assertEqual(sum(c.startswith('SYSUPD STAGE') for c in self.commands),2)
        self.assertTrue(all('VERIFY-BATCH' not in c for c in self.commands))
    async def test_incompatible_corrupt_and_foreign_state_never_stage(self):
        for mode in ['incompatible','corrupt','foreign']:
            result,error,runner=await self.run_stage(mode)
            self.assertIsInstance(error,DevelopmentFault);self.assertFalse(any(c.startswith('SYSUPD STAGE') for c in self.commands))
            self.assertEqual(runner.value['phase'],'rejected');self.commands=[]
    async def test_lost_stage_ack_keeps_original_intent_and_blocks_new_work(self):
        result,error,runner=await self.run_stage('lost')
        self.assertIsInstance(error,UnconfirmedGuestEffect);self.assertEqual(runner.value['phase'],'recovery_required')
        self.assertEqual(sum(c.startswith('SYSUPD STAGE') for c in self.commands),1)
        with self.assertRaises(DevelopmentFault):state.idle(self.store.projects,self.vm)
    async def test_foreign_latest_owner_cannot_be_committed(self):
        result,error,runner=await self.run_stage('stage')
        other={**runner.value,'id':ident()};state.write(self.store,other)
        with self.assertRaises(DevelopmentFault):state.read(self.store,runner.value['id'],current=True)
    async def test_commit_requires_fresh_exact_batch_and_sends_only_once(self):
        _,error,runner=await self.run_stage('stage');self.assertIsNone(error)
        job={**self.job,'kind':'update_commit','updateRevision':runner.value['revision']}
        lease=SimpleNamespace(root=self.root,id=ident(),value={},token='token');(self.root/'leases').mkdir()
        @asynccontextmanager
        async def reserve(*args):yield lease
        test=self
        class SSH:
            def __init__(this,*args):pass
            async def __aenter__(this):return this
            async def __aexit__(this,*args):pass
            async def exec(this,command,**kw):
                test.commands.append(command)
                if command=='SYSUPD STATUS':return capture(test.current)
                return capture('SYSUPD COMMIT result: OK state=Pending restart batch=7 packages=1 release=0.87.14')
        with patch('queue_lease.reserve',reserve),patch('vm_worker.broker_call',new_callable=AsyncMock,return_value=self.target),patch('vm_worker.guard'),patch('access.Access',return_value=SimpleNamespace(record=lambda vm:{'hostKeyFingerprint':'key'},save_record=lambda *args:None)),patch('access.SshTransport',SSH),patch('update_verify.Observation.in_lease',new_callable=AsyncMock,side_effect=UnconfirmedGuestEffect('post-boot proof pending')):
            with self.assertRaises(UnconfirmedGuestEffect):await Commit(self.store,job).run()
            with self.assertRaises(DevelopmentFault):await Commit(self.store,job).run()
        self.assertEqual(self.commands.count('SYSUPD COMMIT'),1)
        latest=state.read(self.store,job['updateId'],current=True);self.assertTrue(latest['rebootAuthorized'])
        self.assertEqual(latest['phase'],'reconnecting')
    def test_inventory_proof_never_accepts_wrong_version_or_target(self):
        for change in [{'version':'0.0.1'},{'target':'/SOFTWARE/OTHER.R4X'}]:
            with self.assertRaises(DevelopmentFault):component_proof({'entries':[{**self.component,**change}]},[self.package])


class Admission(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from test_sysupd import ProbeAdmission
        self.fixture=ProbeAdmission();self.fixture.setUp();self.store=self.fixture.store;self.vm=self.fixture.vm
    def tearDown(self):self.fixture.tearDown()
    async def test_commit_requires_current_revision_exact_reboot_confirmation_and_original_replay(self):
        from update_jobs import admit
        record=state.write(self.store,{'schema':1,'id':ident(),'projectId':self.store.id,'vmId':self.vm['id'],
            'vmRevision':self.vm['revision'],'imageSha256':self.vm['imageSha256'],'systemGeneration':None,
            'phase':'awaiting_commit','batchId':'9007199254740993','targetRelease':'0.87.14','packageArtifactIds':[self.fixture.package['id']]})
        request={'requestId':ident(),'projectRevision':1,'updateId':record['id'],'updateRevision':record['revision'],
            'batchId':record['batchId'],'targetRelease':'0.87.14','vmRevision':self.vm['revision'],'confirmReboot':True}
        with patch('update_jobs.artifact',return_value=self.fixture.package):
            for changes in [{'confirmReboot':False},{'updateRevision':record['revision']+1},{'batchId':'1'},{'command':'SYSUPD COMMIT'}]:
                with self.assertRaises(DevelopmentFault):admit(self.store,'update_commit',{**request,**changes},None,self.vm)
            job,fresh=admit(self.store,'update_commit',request,None,self.vm);self.assertTrue(fresh)
            record['phase']='commit_unconfirmed';state.write(self.store,record)
            self.assertEqual(admit(self.store,'update_commit',request,None,None),(job,False))

if __name__=='__main__':unittest.main()

