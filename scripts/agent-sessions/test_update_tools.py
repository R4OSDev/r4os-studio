"""V5 declarations/defaults and durable non-polling native harness outcomes."""
import json,unittest,uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from profile import PROFILE,COMPLETION_PROFILE,AUTHOR_PROFILE,UPDATE_TOOLS,tools_for,default_enabled
from tool_catalog import specifications,validate_arguments
from contracts import DevelopmentFault,UnconfirmedGuestEffect
from development_tools import DevelopmentTools

class Declarations(unittest.TestCase):
 def test_old_profiles_and_skill_context_keep_exact_declared_boundaries(self):
  self.assertEqual(len(specifications(PROFILE)),30);self.assertEqual(len(specifications(COMPLETION_PROFILE)),18)
  self.assertEqual(specifications(PROFILE)[:18],specifications(COMPLETION_PROFILE))
  self.assertTrue(set(UPDATE_TOOLS).isdisjoint(tools_for(AUTHOR_PROFILE)))
  self.assertFalse(default_enabled('commit_update'));self.assertFalse(default_enabled('rollback_update'))
  self.assertTrue(default_enabled('read_update_package'))
 def test_update_schema_has_no_arbitrary_command_path_or_vm(self):
  for name,body in [('upload_update_package',{'packageArtifactId':str(uuid.uuid4()),'path':'/outside'}),
      ('install_update_package',{'transferJobIds':[str(uuid.uuid4())],'vmId':str(uuid.uuid4())}),
      ('resume_update',{'command':'SYSUPD COMMIT'})]:
   with self.assertRaises(ValueError):validate_arguments(name,body)
  validate_arguments('read_update_package',{'action':'jobs'})
class Harness(unittest.IsolatedAsyncioTestCase):
 def worker(self):
  return SimpleNamespace(run_id=str(uuid.uuid4()),session_id=str(uuid.uuid4()),manifest={'projectId':str(uuid.uuid4())},
    store=SimpleNamespace(project={'revision':2}),items={},stopping=False)
 async def test_original_job_link_precedes_wait_and_only_reads_are_retried(self):
  worker=self.worker();tool=DevelopmentTools(worker);calls=[];job={'id':str(uuid.uuid4()),'kind':'package','state':'queued'}
  count=0
  async def request(operation,**fields):
   nonlocal count
   calls.append(operation)
   if operation=='package':return dict(job)
   self.assertEqual(fields,{'id':job['id']});count+=1
   if count==1:raise DevelopmentFault('Temporarily unavailable',503)
   return {'job':{**job,'state':'completed','packageArtifactId':str(uuid.uuid4())}}
  tool.request=AsyncMock(side_effect=request)
  with patch('vm_worker.broker_call',new_callable=AsyncMock,return_value={'features':{'updateAgentTools':1}}),patch('run_store.item',side_effect=lambda *args:calls.append('pending')),patch('update_tools.asyncio.sleep',new_callable=AsyncMock):
   result=await tool.call('build_update_package',{'planId':str(uuid.uuid4()),'planSha256':'a'*64},'call')
  self.assertTrue(result['success']);self.assertEqual(calls,['package','pending','wait_update','wait_update'])
  self.assertEqual(result['development']['jobId'],job['id'])
 async def test_lost_admission_is_unknown_and_never_replayed(self):
  tool=DevelopmentTools(self.worker());tool.request=AsyncMock(side_effect=UnconfirmedGuestEffect('Lost original receipt'))
  with patch('vm_worker.broker_call',new_callable=AsyncMock,return_value={'features':{'updateAgentTools':1}}):
   result=await tool.call('upload_update_package',{'packageArtifactId':str(uuid.uuid4())},'call')
  self.assertFalse(result['success']);self.assertEqual(result['error'],'unknown');self.assertEqual(tool.request.await_count,1)
  self.assertIn('Original request ID:',result['output'])
 async def test_prepared_batch_is_reported_without_claiming_installation(self):
  worker=self.worker();tool=DevelopmentTools(worker)
  job={'id':str(uuid.uuid4()),'kind':'update_install','state':'completed','updateInstallation':{'phase':'awaiting_commit','installationConfirmed':False}}
  tool.request=AsyncMock(return_value=job)
  with patch('vm_worker.broker_call',new_callable=AsyncMock,return_value={'features':{'updateAgentTools':1}}),patch('run_store.item'):
   result=await tool.call('install_update_package',{'transferJobIds':[str(uuid.uuid4())]},'call')
  self.assertTrue(result['success']);value=json.loads(result['output'])['job']['updateInstallation']
  self.assertEqual(value['phase'],'awaiting_commit');self.assertFalse(value['installationConfirmed'])

if __name__=='__main__':unittest.main()
