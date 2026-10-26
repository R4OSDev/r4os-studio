"""Package request identity, frozen argv/rights, process failures and preserved artifacts."""
import asyncio
import json
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch,AsyncMock
from contracts import DevelopmentFault,digest,LIMITS
from jobs import folder
from layout import save
import test_update_plans as fixtures
import update_plans
import package_jobs
from packager import Packager
from package_support import extend

class Packages(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.f=fixtures.PackagePlans();self.f.setUp();self.store=self.f.store
        self.binary=self.store.root/'qualified-binary';self.binary.write_bytes(b'qualified binary fixture');self.binary.chmod(0o500)
        self.f.packer.update(binary=str(self.binary),directory=str(self.store.root),sha256=digest(self.binary))
        self.f.pinning_mock.return_value=self.f.packer
        self.plan=update_plans.create(self.store,self.f.request())
        self.request={'requestId':str(uuid.uuid4()),'projectRevision':1,'planId':self.plan['id'],'planSha256':self.plan['sha256']}

    def tearDown(self):self.f.tearDown()

    def admit(self):
        job,fresh=self.store.admit('package',self.request);self.assertTrue(fresh);return job

    async def test_replayed_request_returns_original_when_busy_or_active_default_changes(self):
        job=self.admit();same,fresh=self.store.admit('package',self.request)
        self.assertFalse(fresh);self.assertEqual(job,same)
        self.f.pinning_mock.return_value={**self.f.packer,'sha256':'f'*64}
        self.assertEqual(self.store.admit('package',self.request)[0],job)
        with self.assertRaises(DevelopmentFault):self.store.admit('package',{**self.request,'planSha256':'f'*64})
        with self.assertRaises(DevelopmentFault):self.store.admit('build',self.f.fixture.input())
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM jobs WHERE kind=?',('package',)).fetchone()[0],1)

    async def test_wrong_plan_or_packer_preserves_original_records(self):
        for changes in [{'projectRevision':2},{'planSha256':'0'*64},{'binary':'/bin/sh'}]:
            with self.assertRaises(DevelopmentFault):self.store.admit('package',{**self.request,**changes})
        self.f.pinning_mock.return_value={**self.f.packer,'profileSha256':'f'*64}
        with self.assertRaisesRegex(DevelopmentFault,'Packer differs'):self.store.admit('package',self.request)
        self.assertFalse(self.store.db.execute("SELECT id FROM jobs WHERE kind='package'").fetchone())

    async def test_structured_argv_keeps_payload_and_requirements_as_single_values(self):
        job=self.admit();job['updatePlan']['metadata']['title']='Title; literal $(touch /output/side-effect)'
        job['updatePlan']['requirements']=[update_plans.requirement({'kind':'R4L','name':'LIB','target':'/R4OS/LIBS/LIB.R4L','minVersion':'1.2.3','state':'installed'})]
        packer=Packager(self.store,job);args=packer.arguments();value=args[args.index('--payload')+1]
        self.assertEqual(value.count('|'),2);self.assertIn(r'C:\R4OS\SOFTWARE\FIXTURE\FIXTURE.R4X',value)
        self.assertEqual(args[args.index('--require')+1].count('|'),4)
        self.assertEqual(args[args.index('--title')+1],job['updatePlan']['metadata']['title'])
        namespace=packer.command(args);self.assertIn('--unshare-net',namespace);self.assertIn('--clearenv',namespace)
        self.assertNotIn('/bin/sh',namespace);self.assertNotIn('/codex',namespace)

    async def test_stopped_job_and_changed_source_do_not_start_a_process(self):
        job=self.admit();packer=Packager(self.store,job)
        self.store.update(job['id'],'stopping')
        with patch('packager.asyncio.create_subprocess_exec',new_callable=AsyncMock) as start:
            with self.assertRaises(DevelopmentFault):await packer.build()
            start.assert_not_awaited()
        self.store.update(job['id'],'interrupted')
        self.request['requestId']=str(uuid.uuid4());job=self.admit();packer=Packager(self.store,job)
        self.f.parent.joinpath(self.f.artifact['entry']).write_bytes(b'changed input')
        with patch('packager.asyncio.create_subprocess_exec',new_callable=AsyncMock) as start:
            with self.assertRaisesRegex(DevelopmentFault,'checksum changed'):await packer.build()
            start.assert_not_awaited()

    async def test_nonzero_native_exit_captures_stderr_without_publishing_or_replacing(self):
        job=self.admit();self.store.update(job['id'],'running')
        packer=Packager(self.store,job)
        keep=folder(self.store.root/'UpdatePackages'/str(uuid.uuid4()))/'package.R4U';keep.write_bytes(b'keep existing package')
        stdout=asyncio.StreamReader();stdout.feed_data(b'progress\n');stdout.feed_eof()
        stderr=asyncio.StreamReader();stderr.feed_data(b'native error\n');stderr.feed_eof()
        class Process:
            returncode=7
            async def wait(self):return 7
        proc=Process();proc.stdout=stdout;proc.stderr=stderr
        with patch('packager.program',return_value=self.f.packer),patch('packager.asyncio.create_subprocess_exec',new_callable=AsyncMock,return_value=proc):
            with self.assertRaisesRegex(DevelopmentFault,'R4UPack failed') as error:await packer.build()
        self.assertEqual(error.exception.exit_code,7)
        self.assertEqual(keep.read_bytes(),b'keep existing package')
        self.assertIn('[stdout] progress',packer.log.read_text());self.assertIn('[stderr] native error',packer.log.read_text())
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM update_artifacts').fetchone()[0],0)

    async def test_output_limit_and_timeout_kill_owned_process_without_publication(self):
        class Process:
            def __init__(self):
                self.returncode=None;self.ended=asyncio.Event()
                self.stdout=asyncio.StreamReader();self.stderr=asyncio.StreamReader()
            async def wait(self):
                await self.ended.wait();return self.returncode
            def kill(self):self.returncode=-9;self.ended.set()
            def terminate(self):self.returncode=-15;self.ended.set()
        for reason in ('output','timeout'):
            self.request['requestId']=str(uuid.uuid4());job=self.admit();self.store.update(job['id'],'running')
            packer=Packager(self.store,job);proc=Process()
            if reason=='output':proc.stdout.feed_data(b'over limit'*10);proc.stdout.feed_eof()
            with patch('packager.program',return_value=self.f.packer),patch('packager.asyncio.create_subprocess_exec',new_callable=AsyncMock,return_value=proc):
                if reason=='output':
                    with patch.dict(LIMITS,{'outputBytes':16}):
                        with self.assertRaisesRegex(DevelopmentFault,'output exceeded'):await packer.build()
                else:
                    with self.assertRaises(asyncio.TimeoutError):await asyncio.wait_for(packer.build(),.02)
            self.assertEqual(proc.returncode,-9)
            self.assertEqual(self.store.db.execute('SELECT count(*) FROM update_artifacts').fetchone()[0],0)
            self.store.update(job['id'],'failed',error='Injected limit')
    async def test_targeted_dispatcher_extension_is_idempotent_and_refuses_unknown_hosts(self):
        old="prefix\nname = 'worker.py' if meta.get('kind', 'build') == 'build' else 'vm_worker.py'\nsuffix\n"
        value=extend(old);self.assertIn("in ('build', 'package')",value);self.assertEqual(extend(value),value)
        self.assertTrue(value.startswith('prefix\n') and value.endswith('\nsuffix\n'))
        with self.assertRaises(ValueError):extend('unknown administrator implementation')

if __name__=='__main__':unittest.main()
