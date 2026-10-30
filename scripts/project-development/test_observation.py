import base64
from pathlib import Path
import struct
import tempfile
import unittest
import uuid

from checks import evaluate
from contracts import DevelopmentFault, LIMITS, encode
from evidence import png, publish, read, history
from jobs import Jobs, now
from store import connect
from settings import validate

class CriteriaTest(unittest.TestCase):
    def settings(self, **fields):
        return {'revision': 1, 'arguments': '', 'workingDirectory': '.', 'timeoutSeconds': 60,
            'expectedExitCode': None, 'outputContains': [], 'visualCriteria': '', 'outputFiles': [],
            'serviceResponseContains': None, **fields}

    def test_start_and_window_alone_never_pass(self):
        running = {'state': 'running', 'windowVisible': True}
        self.assertEqual(evaluate(self.settings(), running, b'OK')['state'], 'not-run')
        self.assertEqual(evaluate(self.settings(expectedExitCode=0), running, b'OK')['state'], 'inconclusive')
        self.assertEqual(evaluate(self.settings(visualCriteria='Button is blue'), running, b'OK')['state'], 'inconclusive')

    def test_lost_output_and_unknown_exit_do_not_certify_success(self):
        criteria = self.settings(expectedExitCode=0, outputContains=['OK'])
        self.assertEqual(evaluate(criteria, {'state': 'completed', 'exitCode': 0}, b'OK')['state'], 'passed')
        self.assertEqual(evaluate(criteria, {'state': 'completed', 'exitCode': 0, 'outputIncomplete': True}, b'OK')['state'], 'inconclusive')
        self.assertEqual(evaluate(criteria, {'state': 'completed', 'exitCode': None}, b'OK')['state'], 'inconclusive')
        self.assertEqual(evaluate(criteria, {'state': 'completed', 'exitCode': 7}, b'OK')['state'], 'failed')

    def test_service_and_visual_assessments_have_actual_criteria_and_sources(self):
        state = {'state': 'running', 'serviceEndpointReady': True}
        criteria = self.settings(serviceResponseContains='READY')
        self.assertEqual(evaluate(criteria, state, b'')['state'], 'inconclusive')
        state.update(serviceCheckPassed=True, serviceResponseBase64=base64.b64encode(b'NOT READY YET').decode())
        self.assertEqual(evaluate(self.settings(serviceResponseContains='EXACT_OK'), state, b'')['state'], 'failed')
        result = evaluate(self.settings(visualCriteria='Blue button'), state, b'', visual={
            'state': 'passed', 'notes': 'Blue rectangle is visible.', 'evidenceId': str(uuid.uuid4()), 'actor': 'agent'})
        self.assertEqual(result['assessment'], 'agent'); self.assertEqual(result['state'], 'passed')

    def test_settings_reject_path_escape_and_control_file_outputs(self):
        valid = self.settings(outputFiles=[{'name': 'RESULT.TXT', 'contains': 'OK', 'sha256': None}])
        self.assertEqual(validate(valid), valid)
        for name in ('../AUTH', 'C:\\SECRET', 'A123ABCD.JSN', 'STHELP.R4X'):
            with self.assertRaises(DevelopmentFault): validate(self.settings(outputFiles=[{'name': name, 'contains': None, 'sha256': None}]))
        with self.assertRaises(DevelopmentFault): validate(self.settings(timeoutSeconds=301))

    def test_png_budget_and_dimensions_are_enforced_before_storage(self):
        def data(width):
            return base64.b64encode(b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', width, 32) + b'\x08\x02\0\0\0' + b'\0'*4).decode()
        self.assertEqual(png({'base64': data(32)})[1:], (32, 32))
        for value in ({'base64': data(4096)}, {'base64': 'invalid'}, {'base64': base64.b64encode(b'x'*(LIMITS['screenshotBytes']+1)).decode()}):
            with self.assertRaises(DevelopmentFault): png(value)

class EvidenceTest(unittest.TestCase):
    def test_evidence_is_job_bound_and_tamper_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); project = str(uuid.uuid4()); (root/project/'Workspace').mkdir(parents=True); (root/project/'Workspace/module.R4MF').write_text('fixture')
            db = connect(root)
            with db: db.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (project, 'QA', '', 'Zig', 'terminal', 'QA', None, '{}', now(), now(), 1, 'ready'))
            db.close(); store = Jobs(root, root/'R4OS', project)
            try:
                job, _ = store.admit('build', {'requestId': str(uuid.uuid4()), 'projectRevision': 1, 'settingsRevision': 1})
                image = publish(store, job, 'file', b'own output', name='RESULT.TXT')
                self.assertEqual(read(store, job['id'], image['id'])['metadata']['sha256'], image['sha256'])
                self.assertEqual(history(store, job['id'])['items'][0]['id'], image['id'])
                for i in range(33): publish(store, job, 'file', str(i).encode(), name='RESULT.TXT')
                page = history(store, job['id']); self.assertEqual(len(page['items']), 32)
                older = history(store, job['id'], page['before']); self.assertEqual(len(older['items']), 2)
                self.assertEqual(older['items'][-1]['id'], image['id'])
                with self.assertRaises(DevelopmentFault): read(store, str(uuid.uuid4()), image['id'])
                (store.evidence(job['id'])/(image['id']+'.bin')).write_bytes(b'changed')
                with self.assertRaises(DevelopmentFault): read(store, job['id'], image['id'])
            finally: store.close()

class LiveFileTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import sqlite3
        from types import SimpleNamespace
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.work=self.root/'Work';self.work.mkdir()
        self.db=sqlite3.connect(':memory:');self.addCleanup(self.db.close)
        self.job={'id':str(uuid.uuid4()),'projectId':str(uuid.uuid4()),'kind':'execution','state':'running',
            'deploymentId':str(uuid.uuid4()),'target':{'bootId':str(uuid.uuid4())},'process':{'instanceId':7,'generation':'9007199254740993'},
            'package':{'guestDirectory':r'F:\Build\P123ABCD\D123ABCD'},'settings':CriteriaTest().settings(outputFiles=[{'name':'RESULT.TXT','contains':'OK','sha256':None}])}
        self.state={**self.job['process'],'state':'running','closeConfirmed':False}
        self.deployment={'id':self.job['deploymentId'],'projectId':self.job['projectId'],'target':self.job['target'],'guestDirectory':self.job['package']['guestDirectory']}
        self.store=SimpleNamespace(db=self.db,id=self.job['projectId'],evidence=lambda _id:self.root,get=lambda _id:self.job,observe=lambda _id,**fields:self.job.update(fields))
        self.copies=[]
    async def download(self,ssh,guest,local,**kwargs):
        self.assertTrue(guest.endswith('/RESULT.TXT'));self.assertEqual(kwargs['maximum'],65536)
        data=self.copies.pop(0)
        if data is None:return False
        local.write_bytes(data);return True
    async def test_stable_deduplicated_changed_missing_and_later_files(self):
        from unittest.mock import patch
        from live_output_files import owned,read_registered,publish_observation
        owned(self.job,self.deployment,self.state)
        async def read(copies):
            self.copies=list(copies)
            with patch('live_output_files.download',self.download):return publish_observation(self.store,self.job,await read_registered(self.job,self.deployment,None,self.work))
        first=await read([b'OK',b'OK']);same=await read([b'OK',b'OK'])
        self.assertEqual(first[0]['id'],same[0]['id']);self.assertEqual(self.db.execute('SELECT count(*) FROM evidence').fetchone()[0],1)
        changing=await read([b'OK',b'changed']);self.assertEqual(changing[0]['state'],'unstable')
        self.assertEqual(evaluate(self.job['settings'],self.state,b'',changing)['state'],'inconclusive')
        missing=await read([None,None]);self.assertEqual(missing[0]['state'],'missing')
        appeared=await read([b'OK later',b'OK later']);self.assertNotEqual(first[0]['sha256'],appeared[0]['sha256']);self.assertEqual(list(self.work.iterdir()),[])
    async def test_rate_limit_fresh_completion_preflight_and_natural_end(self):
        from unittest.mock import patch,AsyncMock
        from types import SimpleNamespace
        from execution import Execution
        from completion import validate as preflight
        w=Execution.__new__(Execution);w.store=self.store;w.job=self.job;w.live_deployment=self.deployment;w.files_checked_at=float('-inf');w.work=self.work;w.output=lambda state:False
        c=SimpleNamespace(ssh=None,call=AsyncMock(return_value=dict(self.state)))
        with patch('live_output_files.download',self.download),patch('vm_worker.guard') as guard:
            self.copies=[b'OK',b'OK'];await w.observe_files(self.state,c,None)
            self.assertEqual(guard.call_count,2);await w.observe_files(self.state,c,None);self.assertEqual(c.call.await_count,1)
            self.copies=[b'bad',b'bad'];await w.observe_files(self.state,c,None,force=True)
            with self.assertRaises(DevelopmentFault):preflight(self.store,self.job,self.state,b'',self.job['outputFiles'])
            self.copies=[b'OK',b'OK'];await w.observe_files(self.state,c,None,force=True)
            self.assertEqual(preflight(self.store,self.job,self.state,b'',self.job['outputFiles'])['reason'],'criteria_complete')
            self.job['settings']['expectedExitCode']=0
            with self.assertRaises(DevelopmentFault):preflight(self.store,self.job,self.state,b'',self.job['outputFiles'])
            c.call.return_value={**self.state,'state':'completed','closeConfirmed':True};self.copies=[b'OK',b'OK']
            self.assertEqual((await w.observe_files(self.state,c,None,force=True))['state'],'completed')
            with self.assertRaises(DevelopmentFault):preflight(self.store,self.job,c.call.return_value,b'',self.job['outputFiles'])
            self.assertTrue(all(call.args[0]=='poll' for call in c.call.await_args_list))
            w.stop_requested=True;self.assertIs(await w.observe_files(self.state,c,None,force=True),self.state)
            self.assertEqual(self.copies,[])
    async def test_foreign_or_stale_identity_is_rejected_before_read(self):
        import copy
        from live_output_files import owned
        for field in ('generation','boot','deployment','path','ended'):
            j=copy.deepcopy(self.job);d=copy.deepcopy(self.deployment);s=dict(self.state)
            if field=='generation':s['generation']='1'
            if field=='boot':d['target']['bootId']=str(uuid.uuid4())
            if field=='deployment':d['id']=str(uuid.uuid4())
            if field=='path':d['guestDirectory']=r'F:\Build\P123ABCD\D9999999'
            if field=='ended':s['state']='completed'
            with self.assertRaises(DevelopmentFault):owned(j,d,s)
