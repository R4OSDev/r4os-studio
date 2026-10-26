"""Frozen v5 permissions, recovery effect separation and session provenance."""
import json,os,unittest,uuid
from unittest.mock import patch
import test_authorization
from authorization import authorize,authorize_job
from update_authorization import parent,filtered_options
from contracts import DevelopmentFault

class Updates(unittest.TestCase):
 def setUp(self):
  self.f=test_authorization.AuthorizationTest();self.f.setUp();self.store=self.f.store;self.owner=self.f.owner
  self.f.config['engine']['profile']='studio-tools-v5'
  for name in ('resume_update','abort_update','rollback_update','cleanup_update_transport','commit_update'):
   self.f.config['permissions']['studio.'+name]=True
  self.f.save()
 def tearDown(self):self.f.tearDown()
 def test_v4_cannot_gain_update_declarations_from_an_active_skill(self):
  self.f.config['engine']['profile']='studio-tools-v4';self.f.save()
  with self.assertRaises(DevelopmentFault):authorize(self.store,self.owner,'update_plan',os.getpid())
  self.assertEqual(self.store.db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)
 def test_disabled_commit_and_rollback_are_denied_before_admission(self):
  for op,name,action in [('update_commit','commit_update',None),('update_recovery','rollback_update','rollback-last')]:
   self.f.config['permissions']['studio.'+name]=False;self.f.save()
   with self.assertRaises(DevelopmentFault):authorize(self.store,self.owner,op,os.getpid(),recovery_action=action)
   self.f.config['permissions']['studio.'+name]=True;self.f.save()
  self.assertEqual(self.store.db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)
 def test_batch_resume_requires_commit_in_addition_to_resume(self):
  self.f.config['permissions']['studio.commit_update']=False;self.f.save()
  authorize(self.store,self.owner,'update_recovery',os.getpid(),recovery_action='resume')
  with self.assertRaises(DevelopmentFault):authorize(self.store,self.owner,'update_recovery',os.getpid(),recovery_action='resume-batch')
  job={**self.f.job,'kind':'update_recovery','recoveryAction':'resume-batch'}
  with self.assertRaises(DevelopmentFault):authorize_job(self.store,job)
 def test_wait_uses_original_effect_permission_instead_of_a_read_permission(self):
  self.f.config['permissions']['studio.read_update_package']=False;self.f.save()
  job={**self.f.job,'kind':'package'}
  authorize(self.store,self.owner,'wait_update',os.getpid(),job)
  self.f.config['permissions']['studio.build_update_package']=False;self.f.save()
  with self.assertRaises(DevelopmentFault):authorize(self.store,self.owner,'wait_update',os.getpid(),job)
 def test_foreign_and_operator_inputs_are_not_agent_session_inputs(self):
  value={'id':str(uuid.uuid4()),'owner':dict(self.owner)}
  with patch('update_plans.read',return_value=value):
   parent(self.store,'plan',value['id'],self.owner)
   with self.assertRaises(DevelopmentFault):parent(self.store,'plan',value['id'],{**self.owner,'sessionId':str(uuid.uuid4())})
  with patch('update_state.read',return_value={'sessionId':None}):
   with self.assertRaises(DevelopmentFault):parent(self.store,'update',str(uuid.uuid4()),self.owner)
  parent(self.store,'update','unused',None)  # Browser operator scope remains unchanged.
 def test_metadata_options_expose_only_own_session_plans(self):
  own={'id':'own','owner':self.owner};foreign={'id':'foreign','owner':{'sessionId':str(uuid.uuid4())}}
  value={'artifacts':[],'plans':[own,foreign,{'id':'operator'}]}
  self.assertEqual(filtered_options(self.store,value,self.owner)['plans'],[own])

if __name__=='__main__':unittest.main()
