"""Post-boot correlation, full manifest-bound readback and no mutating recovery in observation."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch
from contracts import DevelopmentFault,UnconfirmedGuestEffect
from installed_sftp import InstalledRead
from sysupd_text import parse
from test_sysupd import capture
import test_update_install as fixtures
from update_verify import Observation,correlated
import update_state as state

BATCH=r'SYSUPD STATUS: journal state=cleanup transaction=10 generation=10 release=0.87.14 package-version=2.0.0 components=1 priority=normal applied=1/1 reboot=yes source=- batch-state=installed batch=7 batch-progress=1/1 dirs=ok'

class ReadPolicy(unittest.IsolatedAsyncioTestCase):
    async def test_manifest_targets_are_read_only_without_any_generic_path(self):
        path='/R4OS/SOFTWARE/DEMO/DEMO.R4X';payload={'canonicalTarget':path,'component':{'target':path},'file':{'bytes':100}}
        reader=InstalledRead(None,[payload]);reader.request=AsyncMock()
        for operation,args in [('stat',('/C/R4OS/CONFIG/MODULES.JSON',)),('open',('/C'+path,True)),('close',(b'h',True)),('write',(b'h',0,b'data')),('remove',('/C'+path,)),('rename',('anything','anything')),('put',('anything',None,{}))]:
            with self.assertRaises(DevelopmentFault):await getattr(reader,operation)(*args)
        reader.request.assert_not_awaited()
    async def test_managed_metadata_is_never_a_package_read_target(self):
        path='/R4OS/CONFIG/MODULES.JSON'
        with self.assertRaises(DevelopmentFault):InstalledRead(None,[{'canonicalTarget':path,'component':{'target':path},'file':{'bytes':1}}])

class Proof(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture=fixtures.NativeInstallation();self.fixture.setUp()
    def tearDown(self):self.fixture.tearDown()
    async def scenario(self,mode='finalized'):
        f=self.fixture;f.package['plan']['payloads'][0].update(canonicalTarget=f.component['target'],file={'bytes':100,'sha256':'b'*64})
        _,error,staging=await f.run_stage('stage');self.assertIsNone(error)
        record=staging.value;record['phase']='commit_unconfirmed';record['commands'].append({'operation':'COMMIT','mutating':True,'sent':True})
        if mode=='rollback':
            record.pop('previousFiles',None)
            f.store.get=lambda ident:{'updateProbe':{'inventory':{'entries':[]},'installedRelease':'0.87.14'}}
        record=state.write(f.store,record)
        lease=SimpleNamespace(root=f.root,id=fixtures.ident(),value={},scope={'bootId':'old'},token='token')
        (f.root/'leases').mkdir(exist_ok=True);lease.value['scope']=lease.scope
        commands=[];attempts=0;records=[]
        class Access:
            def __init__(self,*args):pass
            def record(self,ident):return {'hostKeyFingerprint':'wrong' if mode=='key' else 'key'}
            def save_record(self,ident,value):records.append(value)
        class SSH:
            def __init__(self,*args):pass
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def exec(self,command,**kw):
                nonlocal attempts
                commands.append(command)
                if command=='SYSUPD STATUS':
                    attempts+=1
                    if mode=='lost-first' and attempts==1:return capture('',255)
                    if mode=='pending':return capture(BATCH.replace('batch-state=installed','batch-state=pending-restart').replace('state=cleanup','state=post_boot'))
                    return capture(BATCH.replace('batch-state=installed','batch-state=rolled-back').replace('state=cleanup','state=rolled_back') if mode=='rollback' else BATCH.replace('batch=7','batch=8') if mode=='foreign' else BATCH)
                if command=='VER':return {'exitCode':0,'output':'R4OS Release 0.87.14\nKernel active 0.1.384'}
                if command.startswith('TYPE '):return capture('RELEASE_VERSION=0.87.14\n')
                raise AssertionError('No native mutation is permitted in observation')
            def publish_host_key(self):pass
        class Files(SSH):
            exit_code=0
            async def get_hash(self,path,maximum):return {'bytes':100,'sha256':'0'*64 if mode=='hash' else 'b'*64,'fullReadVerified':True}
        observation=Observation(f.store,f.job,record,seconds=.04 if mode in ('pending','hash') else 3,hashes=True)
        with patch('access.Access',Access),patch('access.SshTransport',SSH),patch('vm_worker.guard'),patch('vm_worker.broker_call',new_callable=AsyncMock,return_value=f.target),patch('package_jobs.artifact',return_value=f.package),patch('update_verify.full_inventory',new_callable=AsyncMock,return_value=({'entries':[] if mode=='rollback' else [f.component]},[{'sha256':'proof'}])),patch('update_verify.InstalledRead',Files):
            result=None;caught=None
            try:result=await observation.in_lease(lease)
            except DevelopmentFault as error:caught=error
        return result,caught,observation,commands,records
    async def test_already_finalized_by_native_service_has_exact_postboot_hash_proof(self):
        result,error,obs,commands,records=await self.scenario()
        self.assertIsNone(error);self.assertEqual(result['phase'],'installed');self.assertTrue(obs.value['installationConfirmed'])
        proof=obs.value['proof'];self.assertTrue(proof['fullArtifactHashesRequested']);self.assertEqual(proof['files'][0]['sha256'],'b'*64)
        self.assertTrue(proof['nativeServiceMayHaveFinalized']);self.assertEqual(records[-1]['readiness']['kernel'],'0.1.384')
        self.assertTrue(all(c in ['SYSUPD STATUS','VER',r'TYPE C:\R4OS\CONFIG\VERSION.R4S'] for c in commands))
        self.assertTrue(proof['commitNotRepeated']);self.assertTrue(proof['resumeNotIssued'])
    async def test_owned_terminal_rollback_has_prior_inventory_proof_and_no_install_success(self):
        result,error,obs,commands,_=await self.scenario('rollback')
        self.assertIsNone(error);self.assertEqual(result['phase'],'rolled_back')
        self.assertFalse(obs.value['installationConfirmed']);self.assertTrue(obs.value['rollbackConfirmed'])
        self.assertFalse(obs.value['proof']['previousArtifactBaselineAvailable'])
        self.assertFalse(obs.value['proof']['fullArtifactHashesComplete'])
    async def test_connection_loss_retries_reads_without_commit_or_resume(self):
        result,error,obs,commands,_=await self.scenario('lost-first')
        self.assertIsNone(error);self.assertTrue(obs.value['proof']['readOnly']);self.assertGreaterEqual(commands.count('SYSUPD STATUS'),3)
        self.assertFalse(any(c in ('SYSUPD COMMIT','SYSUPD RESUME-BATCH') for c in commands))
    async def test_deadline_or_hash_mismatch_remains_unknown(self):
        for mode in ('pending','hash'):
            result,error,obs,commands,_=await self.scenario(mode)
            self.assertIsInstance(error,UnconfirmedGuestEffect);self.assertFalse(obs.value['installationConfirmed'])
            self.assertEqual(obs.value['phase'],'recovery_required')
            # Reset fixture directories/owner for this independent scenario.
            self.fixture.tearDown();self.fixture.setUp()
    async def test_foreign_batch_or_changed_host_key_never_claim_success(self):
        for mode in ('foreign','key'):
            _,error,obs,commands,_=await self.scenario(mode)
            self.assertIsInstance(error,UnconfirmedGuestEffect);self.assertFalse(obs.value['installationConfirmed'])
            if mode=='key':self.assertFalse(commands)
            self.fixture.tearDown();self.fixture.setUp()
    def test_live_transaction_is_required_and_visible_release_is_not_used_as_proof(self):
        status=parse('STATUS',capture('SYSUPD STATUS: journal state=cleanup transaction=9 generation=9 release=0.87.15 package-version=2.0.0 components=1 priority=normal applied=1/1 reboot=no source=- dirs=ok'))
        self.assertTrue(correlated(status,{'targetRelease':'0.87.15','transactions':['9']}))
        self.assertFalse(correlated(status,{'targetRelease':'0.87.15','transactions':['8']}))
        self.assertFalse(correlated(status,{'targetRelease':'0.87.14','transactions':['9']}))


class Epoch(unittest.TestCase):
    def test_new_epoch_invalidates_old_deployment_and_readiness_without_changing_host_key(self):
        import tempfile
        from update_epoch import epoch,invalidate,require_deployment
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);vm=fixtures.ident();saved=[]
            store=SimpleNamespace(projects=root,r4os=root)
            record={'vmId':vm,'id':fixtures.ident()}
            old={'hostKeyFingerprint':'key','readiness':{'bootId':'old'}}
            with patch('access.Access',return_value=SimpleNamespace(record=lambda vm:dict(old),save_record=lambda vm,value:saved.append(value))):
                self.assertIsNone(epoch(root,vm))
                first=invalidate(store,record,'STAGE')
                self.assertEqual(epoch(root,vm),first);self.assertNotIn('readiness',saved[0]);self.assertEqual(saved[0]['hostKeyFingerprint'],'key')
                with self.assertRaises(DevelopmentFault):require_deployment(store,{'target':{'vmId':vm}})
                require_deployment(store,{'target':{'vmId':vm,'updateEpoch':first}})
                second=invalidate(store,record,'COMMIT');self.assertNotEqual(first,second)
                with self.assertRaises(DevelopmentFault):require_deployment(store,{'target':{'vmId':vm,'updateEpoch':first}})

class Admission(unittest.IsolatedAsyncioTestCase):
    async def test_verification_deadline_hash_flag_and_revision_are_explicit(self):
        import update_jobs
        from test_sysupd import ProbeAdmission
        fixture=ProbeAdmission();fixture.setUp()
        try:
            store=fixture.store;vm=fixture.vm
            record=state.write(store,{'schema':1,'id':fixtures.ident(),'projectId':store.id,'vmId':vm['id'],'vmRevision':vm['revision'],
                'imageSha256':vm['imageSha256'],'phase':'live_installed','transactions':['9'],'commands':[],'packageArtifactIds':[fixture.package['id']]})
            request={'requestId':fixtures.ident(),'projectRevision':1,'updateId':record['id'],'updateRevision':record['revision'],'deadlineSeconds':120,'fullArtifactHashes':True}
            with patch('update_jobs.artifact',return_value=fixture.package):
                for changes in [{'deadlineSeconds':True},{'deadlineSeconds':10000},{'fullArtifactHashes':'yes'},{'updateRevision':999}]:
                    with self.assertRaises(DevelopmentFault):update_jobs.admit(store,'update_verify',{**request,**changes},None,vm)
                job,fresh=update_jobs.admit(store,'update_verify',request,None,vm)
                self.assertTrue(fresh);self.assertEqual(job['verification'],{'seconds':120,'hashes':True})
                self.assertEqual(update_jobs.admit(store,'update_verify',request,None,None),(job,False))
        finally:fixture.tearDown()

if __name__=='__main__':unittest.main()

