"""Provenance, replay, strict targets/requirements and failed-plan preservation."""
import json
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch
import test_jobs
from contracts import DevelopmentFault,digest,hash_value
from snapshot import capture
from layout import save
import update_plans as plans

class PackagePlans(unittest.TestCase):
    def setUp(self):
        self.fixture=test_jobs.JobsTest();self.fixture.setUp();self.store=self.fixture.store
        self.store.project['pins']={'sdk':{'revision':'f'*40}}
        job,_=self.store.admit('build',self.fixture.input());source,path=capture(self.store,job);self.store.update(job['id'],source=source)
        ident=str(uuid.uuid4());parent=self.store.root/'Artifacts'/ident;parent.mkdir(parents=True)
        binary=parent/'FIXTURE.R4X';binary.write_bytes(b'confirmed-test-artifact')
        proof=parent/'build-proof.json';save(proof,{'nativeFixture':True})
        files=[{'path':binary.name,'sha256':digest(binary),'bytes':binary.stat().st_size}]
        identity={'schema':1,'kind':'R4X','name':'FIXTURE','version':'0.1.0','target':'/R4OS/SOFTWARE/FIXTURE/FIXTURE.R4X','activation':'live','priority':'normal'}
        metadata={'available':True,'identity':identity,'payloadKind':'software','manifest':{'kind':'R4X','name':'FIXTURE','module_version':'0.1.0','target':identity['target']},'sdkRevision':'f'*40,'inspectorSha256':'a'*64,'adapterSha256':'b'*64}
        record={'id':ident,'projectId':self.store.id,'buildId':job['id'],'entry':binary.name,'kind':'R4X','role':'terminal','pins':self.store.project['pins'],
            'files':files,'packageSha256':hash_value(files),'sourceSha256':source['sha256'],'manifestSha256':source['manifestSha256'],
            'buildProof':{'format':'fixture','sha256':digest(proof),'bytes':proof.stat().st_size},'updateMetadata':metadata}
        save(parent/'artifact.json',record);self.store.publish(job['id'],record);self.artifact=record;self.parent=parent
        self.packer={'id':'qualified','version':'1.0.0','revision':'c'*40,'sdkRevision':'d'*40,'host':'x86_64-linux','sha256':'e'*64,'profileSha256':'0'*64}
        self.pinning=patch('update_plans.pin_packer',return_value=self.packer);self.pinning.start()

    def tearDown(self):self.pinning.stop();self.fixture.tearDown()
    def request(self,**values):
        return {'requestId':str(uuid.uuid4()),'projectRevision':1,'configurationRevision':1,'artifactIds':[self.artifact['id']],
            'metadata':{'packageId':'TEST','packageVersion':'2.3.4','targetRelease':'0.87.14','title':'Test package','description':'Concrete proposal.'},'requirements':[],**values}

    def test_plan_replay_native_identity_and_stale_revision(self):
        request=self.request();value=plans.create(self.store,request)
        self.assertEqual(value['payloads'][0]['target'],r'C:\R4OS\SOFTWARE\FIXTURE\FIXTURE.R4X')
        self.assertEqual(value['metadata']['packageVersion'],'2.3.4');self.assertEqual(value['payloads'][0]['component']['version'],'0.1.0')
        self.assertEqual(value['packer'],self.packer);self.assertEqual(plans.create(self.store,request),value)
        self.assertEqual(plans.settings(self.store)['revision'],2)
        with self.assertRaises(DevelopmentFault):plans.create(self.store,{**request,'metadata':{**request['metadata'],'title':'changed'}})
        with self.assertRaisesRegex(DevelopmentFault,'configuration changed'):plans.create(self.store,self.request())
        self.assertEqual(plans.read(self.store,value['id']),value)

    def test_changed_input_and_missing_native_receipt_preserve_settings(self):
        manifest=self.store.root/'Inputs'/self.artifact['buildId']/'module.R4MF';manifest.chmod(0o600);manifest.write_text('changed')
        with self.assertRaisesRegex(DevelopmentFault,'manifest is missing or changed'):plans.create(self.store,self.request())
        self.assertEqual(plans.settings(self.store)['revision'],1);manifest.write_text('fixture')
        (self.parent/self.artifact['entry']).write_bytes(b'corrupted')
        with self.assertRaisesRegex(DevelopmentFault,'checksum changed'):plans.create(self.store,self.request())
        with patch.object(self.store,'artifact',return_value={**self.artifact,'updateMetadata':{'available':False}}):
            with self.assertRaisesRegex(DevelopmentFault,'native update identity'):plans.create(self.store,self.request())

    def test_wrong_native_identity_and_foreign_artifact(self):
        for replacement in [{'projectId':str(uuid.uuid4())},{'pins':{}},
            {'updateMetadata':{**self.artifact['updateMetadata'],'identity':{**self.artifact['updateMetadata']['identity'],'version':'9.9.9'}}}]:
            with patch.object(self.store,'artifact',return_value={**self.artifact,**replacement}):
                with self.assertRaises(DevelopmentFault):plans.create(self.store,self.request())
        with self.assertRaises(DevelopmentFault):plans.create(self.store,self.request(artifactIds=[str(uuid.uuid4())]))
        self.assertEqual(plans.settings(self.store)['revision'],1)

    def test_exact_five_field_requirements_and_metadata(self):
        requirement={'kind':'R4L','name':'LIB','target':'/R4OS/LIBS/LIB.R4L','minVersion':'1.2.3','state':'installed'}
        value=plans.create(self.store,self.request(requirements=[requirement]))
        self.assertEqual(value['requirements'][0]['spec'],'R4L|LIB|/R4OS/LIBS/LIB.R4L|1.2.3|installed')
        for bad in [{**requirement,'state':'active'},{**requirement,'extra':'installed'},{**requirement,'name':'OTHER'},
                    {**requirement,'target':'D:/R4OS/LIBS/LIB.R4L'},{**requirement,'minVersion':'01.2.3'}]:
            with self.assertRaises(DevelopmentFault):plans.requirement(bad)
        for bad in ['C:/R4OS/CONFIG/MODULES.JSON','/R4OS/CONFIG/VERSION.R4S','/R4OS/../bad','C:/bad|pipe','/bad.']:
            with self.assertRaises(DevelopmentFault):plans.target(bad)
        with self.assertRaises(DevelopmentFault):plans.plain('bad\nmultiline',2048,'description')
        with self.assertRaises(DevelopmentFault):plans.version('4294967296.0.0')

    def test_quotas_batch_conflicts_and_tampered_plan(self):
        for ids in [[],[{}],[self.artifact['id']]*33]:
            with self.assertRaises(DevelopmentFault):plans.create(self.store,self.request(artifactIds=ids))
        oversized={**plans.payload(self.store,self.artifact['id']),'file':{'path':'FIXTURE.R4X','bytes':128*1024*1024,'sha256':'a'*64}}
        with patch('update_plans.payload',return_value=oversized):
            with self.assertRaisesRegex(DevelopmentFault,'quota'):plans.create(self.store,self.request())
        first=plans.create(self.store,self.request());second=plans.create(self.store,self.request(configurationRevision=2))
        with self.assertRaisesRegex(DevelopmentFault,'same target twice'):plans.batch(self.store,[first['id'],second['id']])
        with self.assertRaises(DevelopmentFault):plans.batch(self.store,[first['id']]*17)
        changed={**first,'activation':'restart'}
        with self.store.db:self.store.db.execute('UPDATE update_plans SET payload=? WHERE id=?',(json.dumps(changed),first['id']))
        with self.assertRaisesRegex(DevelopmentFault,'identity changed'):plans.read(self.store,first['id'])
