"""Exact own recovery gates, one-shot reboot effects and retained safe cleanup evidence."""
from contextlib import asynccontextmanager
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch
from contracts import DevelopmentFault,UnconfirmedGuestEffect
from test_sysupd import capture,IDLE
from test_update_verify import BATCH
import test_update_install as fixtures
from update_recovery import Recovery,permitted
from sysupd_text import parse
import update_state as state

class RecoveryTests(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.f=fixtures.NativeInstallation();self.f.setUp()
 def tearDown(self):self.f.tearDown()
 async def prepared(self):
  f=self.f;_,error,runner=await f.run_stage('stage');self.assertIsNone(error)
  runner.value['packages'][0]['transfer']['tmp']='/C/R4OS/UPDATE/INBOX/U123ABCD.TMP'
  runner.value=state.write(f.store,runner.value)
  return runner.value
 async def action(self,action,foreign=False,lost=False):
  f=self.f;record=await self.prepared()
  native=record['lastStatus']
  if action=='rollback-last':
   native=parse('STATUS',capture(BATCH));record.update(phase='installed',installationConfirmed=True,lastStatus=native)
   record=state.write(f.store,record)
  job={**f.job,'kind':'update_recovery','updateRevision':record['revision'],'recoveryAction':action,'confirmReboot':True}
  lease=SimpleNamespace(root=f.root,id=fixtures.ident(),token='token',value={});(f.root/'leases').mkdir(exist_ok=True)
  @asynccontextmanager
  async def reserve(*args):yield lease
  commands=[]
  class SSH:
   def __init__(self,*args):pass
   async def __aenter__(self):return self
   async def __aexit__(self,*args):pass
   async def exec(self,command,**kw):
    commands.append(command)
    if command=='SYSUPD STATUS':
     if foreign:return capture(native['rawLine'].replace('batch=7','batch=8'))
     if action=='abort-batch' and 'SYSUPD ABORT-BATCH' in commands:return capture(IDLE)
     return capture(native['rawLine'])
    if lost:return capture('',255)
    text={'rollback-last':'SYSUPD ROLLBACK-LAST result: OK state=Pending rollback; rebooting',
      'resume-batch':'SYSUPD COMMIT result: OK state=Pending restart batch=7 packages=1 release=0.87.14',
      'abort-batch':'SYSUPD ABORT-BATCH result: OK state=Idle packages=1 stages=2'}
    return capture(text[action])
  observer=AsyncMock(return_value={'state':'completed','phase':'proof-pending-in-separate-test'})
  access=SimpleNamespace(record=lambda vm:{'hostKeyFingerprint':'key'},save_record=lambda *args:None)
  with patch('queue_lease.reserve',reserve),patch('vm_worker.broker_call',new_callable=AsyncMock,return_value=f.target),patch('vm_worker.guard'),patch('access.Access',return_value=access),patch('access.SshTransport',SSH),patch('update_verify.Observation.in_lease',observer):
   caught=None;result=None
   try:result=await Recovery(f.store,job).run()
   except DevelopmentFault as error:caught=error
  return result,caught,commands,state.read(f.store,record['id']),observer
 async def test_prepared_resume_batch_can_execute_commit_and_requires_later_proof(self):
  result,error,commands,value,observer=await self.action('resume-batch')
  self.assertIsNone(error);self.assertEqual(commands.count('SYSUPD RESUME-BATCH'),1)
  call=value['commands'][-1];self.assertEqual(call['reply']['effectiveOperation'],'COMMIT');observer.assert_awaited_once()
  self.assertFalse(value['installationConfirmed'])
 async def test_lost_rollback_response_is_followed_only_by_read_only_observer(self):
  result,error,commands,value,observer=await self.action('rollback-last',lost=True)
  self.assertIsNone(error);self.assertEqual(commands.count('SYSUPD ROLLBACK-LAST'),1);observer.assert_awaited_once()
  self.assertEqual(value['rollbackTransactionId'],'10');self.assertTrue(value['recoveryIntent']['rebootAuthorized'])
 async def test_foreign_last_batch_rejects_before_any_native_write(self):
  _,error,commands,_,observer=await self.action('rollback-last',foreign=True)
  self.assertIsInstance(error,DevelopmentFault);self.assertEqual(commands,['SYSUPD STATUS']);observer.assert_not_awaited()
 async def test_abort_prepared_own_batch_requires_positive_reply_and_terminal_status(self):
  result,error,commands,value,observer=await self.action('abort-batch')
  self.assertIsNone(error);self.assertEqual(value['phase'],'aborted');self.assertTrue(value['abortConfirmed'])
  self.assertFalse(value['installationConfirmed']);observer.assert_not_awaited()
 async def test_changed_preparatory_batch_without_own_transition_is_not_adopted(self):
  record=await self.prepared()
  changed=parse('STATUS',capture(record['lastStatus']['rawLine'].replace('state=staged','state=committing')))
  self.assertFalse(permitted(changed,record,'resume-batch'))
  self.assertTrue(permitted(record['lastStatus'],record,'abort-batch'))
 async def test_pending_owner_survives_vm_stop_and_blocks_project_deletion(self):
  from quarantine import admission
  from project_maintenance import pending_update,busy
  from delete import collect
  from store import ProjectFault
  f=self.f;record=await self.prepared()
  admission(f.store.projects,f.vm,'stopped')
  with self.assertRaises(DevelopmentFault):state.idle(f.store.projects,f.vm)
  self.assertTrue(pending_update(f.store.projects,f.store.id));self.assertTrue(busy(f.store.projects,f.store.id))
  with self.assertRaises(ProjectFault):collect(f.store.projects,f.store.id,{'agents':True,'development':True})
 async def test_cleanup_removes_only_exact_own_hashes_after_terminal_proof(self):
  f=self.f;value=await self.prepared();value.update(phase='installed',installationConfirmed=True,lastStatus=parse('STATUS',capture(BATCH)))
  value=state.write(f.store,value);runner=Recovery(f.store,{**f.job,'kind':'update_recovery'});runner.value=value;runner.lease=None
  removed=[];final=value['packages'][0]['transfer']['final']
  class Wire:
   exit_code=0
   def __init__(self,*args):pass
   async def __aenter__(self):return self
   async def __aexit__(self,*args):pass
   async def get_hash(self,path,*a):return {'bytes':100,'sha256':'b'*64} if path==final else None
   async def remove(self,path):removed.append(path)
   async def stat(self,path):return None
  ssh=SimpleNamespace(exec=AsyncMock(return_value=capture(BATCH)))
  with patch('update_recovery.InboxSftp',Wire),patch('vm_worker.guard'):
   result=await runner.cleanup(ssh,parse('STATUS',capture(BATCH)))
  self.assertEqual(removed,[final]);self.assertTrue(runner.value['cleanupConfirmed']);self.assertEqual(result['phase'],'transport_cleanup_complete')
 async def test_cleanup_lost_remove_ack_is_unknown_and_retains_original_intent(self):
  f=self.f;value=await self.prepared();value.update(phase='installed',installationConfirmed=True,lastStatus=parse('STATUS',capture(BATCH)))
  value=state.write(f.store,value);runner=Recovery(f.store,{**f.job,'kind':'update_recovery'});runner.value=value;runner.lease=None
  calls=[]
  class Wire:
   exit_code=0
   def __init__(self,*args):pass
   async def __aenter__(self):return self
   async def __aexit__(self,*args):pass
   async def get_hash(self,path,*a):return {'bytes':100,'sha256':'b'*64} if path.endswith('.R4U') else None
   async def remove(self,path):calls.append(path);raise UnconfirmedGuestEffect('lost acknowledgement')
  ssh=SimpleNamespace(exec=AsyncMock(return_value=capture(BATCH)))
  with patch('update_recovery.InboxSftp',Wire),patch('vm_worker.guard'):
   with self.assertRaises(UnconfirmedGuestEffect):await runner.cleanup(ssh,parse('STATUS',capture(BATCH)))
  self.assertEqual(len(calls),1);self.assertEqual(runner.value['phase'],'cleanup_unconfirmed')
  self.assertTrue(runner.value['cleanupIntents'][0]['sent']);self.assertNotIn('acknowledged',runner.value['cleanupIntents'][0])


class Reconciliation(unittest.IsolatedAsyncioTestCase):
 setUp=RecoveryTests.setUp
 tearDown=RecoveryTests.tearDown
 prepared=RecoveryTests.prepared
 async def test_lost_cleanup_remove_ack_is_resolved_by_original_paths_only(self):
  from update_recovery import reconcile
  f=self.f;value=await self.prepared();final=value['packages'][0]['transfer']['final']
  value.update(phase='cleanup_unconfirmed',cleanupTerminalPhase='installed',cleanupJobId=f.job['id'],
      cleanupIntents=[{'path':final,'sent':True}],installationConfirmed=True,lastStatus=parse('STATUS',capture(BATCH)))
  value=state.write(f.store,value);f.store.project={'vmId':f.vm}
  f.store.recovered=lambda ident,state,receipt,**fields:{'state':state,'receipt':receipt,**fields}
  vm={'id':f.vm,'revision':'rev','imageId':'image','imageSha256':'a'*64}
  class Lease:
   root=f.root;id=fixtures.ident();token='token';value={}
   def __init__(self,*args):pass
   def __enter__(self):return self
   def __exit__(self,*args):pass
  (f.root/'leases').mkdir(exist_ok=True)
  commands=[];paths=[]
  class SSH:
   def __init__(self,*args):pass
   async def __aenter__(self):return self
   async def __aexit__(self,*args):pass
   async def exec(self,command,**kw):commands.append(command);return capture(BATCH)
  class ReadOnlyWire(SSH):
   exit_code=0
   async def stat(self,path):paths.append(path);return None
  access=SimpleNamespace(record=lambda vm:{'hostKeyFingerprint':'key'})
  host=SimpleNamespace(boots=SimpleNamespace(ensure=AsyncMock(return_value={'bootId':'boot'})))
  job={**f.job,'kind':'update_recovery','state':'unknown'}
  with patch('access.vm_config',return_value=vm),patch('lease.VmLease',Lease),patch('vm_client.vm_call',new_callable=AsyncMock,return_value={'vm':{'state':'running'},'invocationId':'i'}),patch('access.Access',return_value=access),patch('access.SshTransport',SSH),patch('update_recovery.InboxSftp',ReadOnlyWire):
   result=await reconcile(f.store,job,host)
  self.assertEqual(result['state'],'completed');self.assertEqual(paths,[final]);self.assertEqual(commands,['SYSUPD STATUS'])
  self.assertTrue(result['updateInstallation']['cleanupConfirmed'])
 async def test_terminal_history_of_explicitly_replaced_system_is_not_current_ownership(self):
  from update_probe import owned_record
  f=self.f;value=await self.prepared()
  changed={'id':f.vm,'systemGeneration':fixtures.ident(),'imageSha256':'a'*64}
  with self.assertRaises(DevelopmentFault):owned_record(f.store,changed,f.package)
  value.update(phase='installed',installationConfirmed=True);state.write(f.store,value)
  self.assertIsNone(owned_record(f.store,changed,f.package))
 async def test_source_dash_never_proves_live_ownership_but_exact_bound_source_can(self):
  from update_recovery import recover_live_identity
  value=await self.prepared();value.pop('batchId');value['transactions']=[];value['lastStatus']=parse('STATUS',capture(IDLE))
  source=value['packages'][0]['transfer']['guestPath']
  line='SYSUPD STATUS: journal state=commit transaction=9 generation=9 release=0.87.14 package-version=2.0.0 components=1 priority=normal applied=0/2 reboot=no source='+source+' dirs=ok'
  calls=[]
  class ReadOnlyWire:
   exit_code=0
   def __init__(self,*args):pass
   async def __aenter__(self):return self
   async def __aexit__(self,*args):pass
   async def get_hash(self,path,maximum):calls.append(path);return {'bytes':100,'sha256':'b'*64}
  with patch('update_recovery.InboxSftp',ReadOnlyWire):
   self.assertFalse(await recover_live_identity(None,parse('STATUS',capture(line.replace(source,'-'))),value,lambda:None))
   self.assertFalse(calls)
   self.assertTrue(await recover_live_identity(None,parse('STATUS',capture(line)),value,lambda:None))
  self.assertEqual(value['transactions'],['9']);self.assertEqual(calls,[value['packages'][0]['transfer']['final']])

if __name__=='__main__':unittest.main()

