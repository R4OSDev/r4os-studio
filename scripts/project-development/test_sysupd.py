"""Native text boundaries, complete channels, terminal history and safe metadata reads."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
from contextlib import closing
import unittest
from unittest.mock import AsyncMock,patch
from contracts import DevelopmentFault
from access import SshTransport
from sysupd_text import parse,ownership,release_file,inventory
import sftp

def capture(text,code=0,stderr=''):return {'exitCode':code,'stdout':text,'stderr':stderr}
IDLE=r'SYSUPD STATUS: idle inbox=C:\R4OS\UPDATE\INBOX staged=C:\R4OS\UPDATE\STAGED dirs=ok'

class Text(unittest.TestCase):
    def test_idle_and_terminal_journal_history_are_preserved(self):
        value=parse('STATUS',capture(IDLE));self.assertTrue(ownership(value)['mayUpload'])
        line='SYSUPD STATUS: journal state=cleanup transaction=18446744073709551615 generation=9007199254740993 release=0.87.14 package-version=0.1.1 components=1 priority=normal applied=2/2 reboot=no source=- dirs=ok'
        value=parse('STATUS',capture(line))
        self.assertEqual(value['status']['transactionId'],'18446744073709551615')
        self.assertTrue(ownership(value)['terminalHistoryRetained']);self.assertTrue(ownership(value)['mayUpload'])

    def test_foreign_failed_or_active_batch_is_blocked_and_rollback_is_not_install_success(self):
        for phase in ['staged','committing','failed','pending-restart','rolling-back']:
            value=parse('STATUS',capture('SYSUPD STATUS: batch state='+phase+r' batch=9007199254740993 progress=0/1 release=0.87.14 inbox=C:\R4OS\UPDATE\INBOX staged=C:\R4OS\UPDATE\STAGED dirs=ok'))
            self.assertFalse(ownership(value)['mayUpload'])
            self.assertTrue(ownership(value,{'batchId':'9007199254740993'})['matchesOwnRecord'])
            self.assertFalse(ownership(value,{'batchId':'other'})['matchesOwnRecord'])
        rolled=parse('STATUS',capture(r'SYSUPD STATUS: batch state=rolled-back batch=1 progress=1/1 release=0.87.14 inbox=C:\R4OS\UPDATE\INBOX staged=C:\R4OS\UPDATE\STAGED dirs=ok'))
        self.assertTrue(rolled['status']['historicalRollback'])

    def test_result_spaces_live_apply_and_actual_exit_agreement(self):
        value=parse('COMMIT',capture('SYSUPD COMMIT result: OK state=Pending restart batch=9007199254740993 packages=1 release=0.87.14\nSYSUPD I/O: payload-passes=1'))
        self.assertEqual(value['fields']['state'],'Pending restart')
        value=parse('STAGE',capture('SYSUPD APPLY result: OK package=DEMO package-version=0.1.1 release=0.87.14 payloads=2 applied=2 bytes=100 streamed=100 staged=100 reboot=no transaction=5 journal=SYSUPD0.JRN'))
        self.assertEqual(value['effectiveOperation'],'APPLY');self.assertTrue(value['success'])
        value=parse('VERIFY',capture('',2,'SYSUPD VERIFY result: INCOMPATIBLE reason=requirement-missing current=none required=LIB'))
        self.assertFalse(value['success']);self.assertEqual(value['result'],'INCOMPATIBLE')
        value=parse('RESUME-BATCH',capture('SYSUPD RESUME-BATCH result: OK state=installed'))
        self.assertNotIn('batch',value['fields'])  # Native terminal reply can omit identity.
        self.assertFalse(parse('COMMIT',capture('SYSUPD COMMIT result: OK state=Pending restart',255))['confirmed'])
        self.assertFalse(parse('APPLY',capture('SYSUPD APPLY result: INTERRUPTED phase=inventory',1))['success'])

    def test_resume_abort_and_rollback_outcomes_do_not_claim_installation(self):
        for command,body in [('RESUME','state=cleanup'),('ABORT-BATCH','state=Idle packages=2'),('ROLLBACK-LAST','state=Pending rollback; rebooting'),('RESUME-BATCH','state=rolled-back')]:
            value=parse(command,capture('SYSUPD '+command+' result: OK '+body))
            self.assertTrue(value['confirmed']);self.assertFalse(value['installationConfirmed'])
        self.assertEqual(value['reportedOutcome'],'rolled-back')
    def test_unknown_duplicate_contradictory_and_incomplete_responses_fail(self):
        for text,code in [(IDLE+' dirs=ok',0),(IDLE,1),(IDLE+'\n'+IDLE,0),
                          ('SYSUPD COMMIT result: OK state=Something invented',0),
                          ('SYSUPD VERIFY result: FAILED reason=bad',0),
                          ('SYSUPD VERIFY result: OK package=DEMO',7)]:
            with self.assertRaises(DevelopmentFault):parse('STATUS' if text.startswith('SYSUPD STATUS') else 'COMMIT' if 'COMMIT' in text else 'VERIFY',capture(text,code))
        with self.assertRaises(DevelopmentFault):parse('VERIFY-BATCH',capture('JSON is unavailable'))
        with self.assertRaises(DevelopmentFault):parse('STATUS',{**capture(IDLE),'truncated':True})
        with self.assertRaises(DevelopmentFault):parse('STATUS',capture(IDLE.replace('dirs=ok','dirs=missing')))

    def test_release_and_inventory_observation_rejects_duplicates_and_invalid_counts(self):
        self.assertEqual(release_file('\ufeffRELEASE_VERSION=0.87.14\r\n'),'0.87.14')
        with self.assertRaises(DevelopmentFault):release_file('RELEASE_VERSION=0.87.14\nRELEASE_VERSION=0.87.14')
        value={'schema':4,'profile':'full','count':1,'entries':[{'name':'KERNEL','kind':'KERNEL','version':'0.1.384','target':'/boot/r4os.elf'}]}
        self.assertEqual(inventory(json.dumps(value)),value)
        with self.assertRaises(DevelopmentFault):inventory(json.dumps({**value,'count':2}))
        with self.assertRaises(DevelopmentFault):inventory('{"schema":4,"schema":4}')

class Transport(unittest.IsolatedAsyncioTestCase):
    def fake(self,code=0,out=b'answer',error=b'diagnostic'):
        class Process:
            def __init__(self):
                self.returncode=code;self.stdout=asyncio.StreamReader();self.stderr=asyncio.StreamReader()
                self.stdout.feed_data(out);self.stdout.feed_eof();self.stderr.feed_data(error);self.stderr.feed_eof()
            async def wait(self):return self.returncode
            def kill(self):self.returncode=-9
        transport=object.__new__(SshTransport);transport.record={'username':'fixture'};transport.processes=set()
        transport.argv=lambda:[];transport.environment=lambda:{}
        return transport,Process()

    async def test_legacy_shape_preserved_and_complete_success_stderr_retained(self):
        transport,proc=self.fake();_,second=self.fake()
        with patch('access.asyncio.create_subprocess_exec',new_callable=AsyncMock,side_effect=[proc,second]):
            self.assertEqual(await transport.exec('fixed'),{'exitCode':0,'output':'answer'})
            value=await transport.exec('fixed',complete=True)
        self.assertEqual(value['stderr'],'diagnostic');self.assertEqual(value['stdout'],'answer');self.assertFalse(transport.processes)

    async def test_complete_ssh_failure_and_truncation_are_explicit(self):
        transport,proc=self.fake(255,error=b'connection lost')
        with patch('access.asyncio.create_subprocess_exec',new_callable=AsyncMock,return_value=proc):
            value=await transport.exec('fixed',complete=True);self.assertTrue(value['transportUncertain']);self.assertEqual(value['exitCode'],255)
        transport,proc=self.fake(out=b'over limit')
        with patch('access.asyncio.create_subprocess_exec',new_callable=AsyncMock,return_value=proc):
            value=await transport.exec('fixed',complete=True,limit=3);self.assertTrue(value['truncated']);self.assertEqual(value['stdout'],'ove')

    async def test_legacy_host_key_failure_and_complete_timeout_keep_their_distinct_contracts(self):
        transport,proc=self.fake(255,error=b'HOST IDENTIFICATION HAS CHANGED')
        with patch('access.asyncio.create_subprocess_exec',new_callable=AsyncMock,return_value=proc):
            with self.assertRaisesRegex(DevelopmentFault,'host key'):await transport.exec('fixed')
        transport,proc=self.fake()
        proc.returncode=None;proc.stdout=asyncio.StreamReader();proc.stderr=asyncio.StreamReader()
        proc.stdout.feed_data(b'partial')
        with patch('access.asyncio.create_subprocess_exec',new_callable=AsyncMock,return_value=proc):
            value=await transport.exec('fixed',timeout=.01,complete=True)
        self.assertTrue(value['timedOut']);self.assertTrue(value['transportUncertain'])
        self.assertIsNone(value['exitCode']);self.assertEqual(value['stdout'],'partial');self.assertEqual(proc.returncode,-9)
    async def test_metadata_sftp_has_only_fixed_read_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'inventory.json'
            async def received(ssh,lines,**kwargs):
                self.assertTrue(lines[0].startswith('get "/C/R4OS/CONFIG/MODULES.JSON" '));self.assertEqual(kwargs['maximum'],131072)
                path.write_text('{}');return True
            with patch('sftp.batch',side_effect=received):
                value=await sftp.download_update_metadata(None,'inventory',path)
                self.assertTrue(value['fullReadVerified'])
            with self.assertRaises(DevelopmentFault):await sftp.download_update_metadata(None,'/etc/passwd',Path(temp)/'other')

class ProbeAdmission(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import test_update_plans
        from store import connect
        self.fixture=test_update_plans.PackagePlans();self.fixture.setUp();self.store=self.fixture.store
        import uuid
        self.vm={'id':str(uuid.uuid4()),'revision':'revision','imageId':'99.99.99-full','imageSha256':'a'*64,'networkEnabled':True}
        self.store.project['vmId']=self.vm['id']
        with closing(connect(self.store.projects)) as db, db:db.execute('UPDATE projects SET vm_id=?,pins=? WHERE id=?',(self.vm['id'],json.dumps(self.store.project['pins']),self.store.id))
        self.package={'id':str(uuid.uuid4()),'projectId':self.store.id,'plan':{'pins':self.store.project['pins']}}
        self.mock=patch('update_probe.artifact',return_value=self.package);self.mock.start()
        self.request={'requestId':str(uuid.uuid4()),'projectRevision':1,'packageArtifactId':self.package['id']}

    def tearDown(self):self.mock.stop();self.fixture.tearDown()

    async def test_request_replay_has_one_scope_and_rejects_arbitrary_guest_command(self):
        from update_probe import admit
        job,fresh=admit(self.store,self.request,None,self.vm);self.assertTrue(fresh)
        self.assertEqual(admit(self.store,self.request,None,None),(job,False))
        with self.assertRaises(DevelopmentFault):admit(self.store,{**self.request,'command':'SYSUPD COMMIT'},None,self.vm)
        self.assertEqual(job['binding']['id'],self.vm['id'])

    async def test_preflight_never_starts_a_stopped_guest_or_changes_image_selection(self):
        from update_probe import admit,Probe
        job,_=admit(self.store,self.request,None,self.vm);self.store.update(job['id'],'running')
        with patch('access.transport_profile',return_value={}),patch('vm_client.vm_call',new_callable=AsyncMock,return_value={'vm':{'state':'stopped'}}) as calls,patch('vm_worker.broker_call',new_callable=AsyncMock) as bind:
            with self.assertRaisesRegex(DevelopmentFault,'explicitly'):await Probe(self.store,job).run()
            self.assertEqual([call.args[1] for call in calls.await_args_list],['info']);bind.assert_not_awaited()
        self.assertEqual(self.store.project['vmId'],self.vm['id'])
