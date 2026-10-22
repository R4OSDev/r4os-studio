import json,hashlib,unittest,uuid
from unittest.mock import AsyncMock,patch
from contracts import DevelopmentFault,digest,hash_value,encode
from layout import save
from snapshot import capture
from recovery import local,reconcile
from quarantine import claim,path
import test_jobs

class RecoveryTest(unittest.TestCase):
    def setUp(self):self.f=test_jobs.JobsTest();self.f.setUp();self.store=self.f.store
    def tearDown(self):self.f.tearDown()
    def build(self,commit=True):
        job,_=self.store.admit('build',self.f.input());source,_=capture(self.store,job);self.store.update(job['id'],source=source)
        ident=str(uuid.uuid4());root=self.store.root/'Artifacts'/ident;root.mkdir(parents=True);(root/'TEST.R4X').write_bytes(b'qualified-test-fixture')
        files=[{'path':'TEST.R4X','bytes':22,'sha256':digest(root/'TEST.R4X')}];files[0]['bytes']=(root/'TEST.R4X').stat().st_size
        proof={'schema':1,'interface':'r4os-studio-sdk-build','status':'success','pins':{},'sourceSha256':source['sha256'],'artifact':files[0]};save(root/'build-proof.json',proof)
        artifact={'id':ident,'buildId':job['id'],'projectId':self.store.id,'pins':{},'sourceSha256':source['sha256'],'manifestSha256':source['manifestSha256'],'entry':'TEST.R4X','files':files,'packageSha256':hash_value(files),'buildProof':{'format':'r4os-studio-sdk-build-v1','bytes':(root/'build-proof.json').stat().st_size,'sha256':digest(root/'build-proof.json')}};save(root/'artifact.json',artifact)
        if commit:
            with self.store.db:self.store.db.execute('INSERT INTO artifacts VALUES(?,?,?)',(ident,job['id'],encode(artifact)))
        job=self.store.update(job['id'],'unknown');return job,root
    def test_only_committed_untampered_build_proofs_recover_without_recompile(self):
        job,root=self.build();result=local(self.store,job);self.assertEqual(result['state'],'completed');self.assertFalse(result['recovery']['replayed']);self.assertEqual(self.store.artifact(result['artifactId'])['buildId'],job['id'])
        previous=json.loads(self.store.db.execute('SELECT previous FROM recoveries').fetchone()[0]);self.assertEqual(previous['state'],'unknown')
        job,root=self.build(commit=False);self.assertIsNone(local(self.store,job));self.assertEqual(self.store.get(job['id'])['state'],'unknown')
        job,root=self.build();(root/'TEST.R4X').write_bytes(b'tampered')
        with self.assertRaises(DevelopmentFault):local(self.store,job)
        self.assertEqual((root/'TEST.R4X').read_bytes(),b'tampered');self.assertEqual(self.store.get(job['id'])['state'],'unknown')
    def execution(self,closed=True):
        job,_=self.store.admit('build',self.f.input());vm=str(uuid.uuid4());deployment=str(uuid.uuid4());execution=str(uuid.uuid4());target={'vmId':vm};settings={**job['settings'],'expectedExitCode':0,'outputContains':['EXPECTED']};process={'instanceId':12,'generation':'18446744073709551615','windowId':-1}
        job=self.store.update(job['id'],'unknown',kind='execution',deploymentId=deployment,target=target,settings=settings,process=process,binding={'id':vm})
        work=self.store.root/'ExecutionWork'/job['id'];work.mkdir(parents=True);intent={'schema':1,'jobId':job['id'],'executionId':execution,'deploymentId':deployment,'target':target,'settings':settings,'state':'intent'};save(work/'intent.json',intent);save(work/'started.json',{**intent,'process':process})
        data=b'EXPECTED';self.store.evidence(job['id']).joinpath('output.log').write_bytes(data)
        if closed:save(work/'closed.json',{**intent,'state':'closed','completion':{'state':'completed','closeConfirmed':True,'instanceId':12,'generation':process['generation'],'exitCode':0},'outputReceipt':{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}})
        claim(self.store.projects,vm,{'jobId':job['id']});return job,work,vm
    def test_private_close_proof_recovers_result_and_archives_quarantine(self):
        job,work,vm=self.execution();result=local(self.store,job);self.assertEqual(result['state'],'completed');self.assertEqual(result['check']['state'],'passed');self.assertFalse(path(self.store.projects,vm).exists());self.assertTrue((path(self.store.projects,vm).parent/'Resolved'/(job['id']+'.json')).exists())
    def test_foreign_generation_or_missing_host_receipt_cannot_certify_guest_end(self):
        job,work,vm=self.execution();value=json.loads((work/'closed.json').read_text());value['completion']['generation']='8';save(work/'closed.json',value)
        with self.assertRaises(DevelopmentFault):local(self.store,job)
        self.assertTrue(path(self.store.projects,vm).exists());(work/'closed.json').unlink();self.assertIsNone(local(self.store,job));self.assertEqual(self.store.get(job['id'])['state'],'unknown')

class VmRecoveryTest(unittest.IsolatedAsyncioTestCase):
    async def test_running_unknown_is_preserved_and_vm_stop_is_not_an_app_test_pass(self):
        f=RecoveryTest();f.setUp()
        try:
            job,work,vm=f.execution(closed=False);config={'id':vm,'revision':'revision','imageId':'image','imageSha256':'a'*64};call=AsyncMock(return_value={'vm':{'state':'running'},'invocationId':'a'*32})
            with patch('access.vm_config',return_value=config),patch('vm_client.vm_call',call):
                result=await reconcile(f.store,job);self.assertEqual(result['state'],'unknown');self.assertTrue(path(f.store.projects,vm).exists())
                call.return_value={'vm':{'state':'stopped'},'invocationId':''};result=await reconcile(f.store,f.store.get(job['id']));self.assertEqual(result['state'],'interrupted');self.assertEqual(result['check']['state'],'inconclusive');self.assertFalse(path(f.store.projects,vm).exists())
            self.assertTrue(all(c.args[1]=='info' for c in call.await_args_list))
        finally:f.tearDown()
