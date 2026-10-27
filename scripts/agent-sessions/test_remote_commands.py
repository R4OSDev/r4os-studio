"""Real active-run/SCM lease and job persistence; reserved v9 and SSH are fixtures."""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
import uuid

import test_roadmap_tools as fixtures
from session_store import encode
from run_store import transition

REMOTE = Path(__file__).resolve().parents[1] / 'remote-hosts'
sys.path.insert(1, str(REMOTE))
import catalog as remote_catalog
import checks as remote_checks
import job_store
from test_transport import key
import agent_channel
spec = importlib.util.spec_from_file_location('own_remote_commands_host', REMOTE / 'host.py')
remote_host = importlib.util.module_from_spec(spec); spec.loader.exec_module(remote_host)


class RemoteCommandTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.RoadmapToolsTest.setUp
    tearDown = fixtures.RoadmapToolsTest.tearDown
    open = fixtures.RoadmapToolsTest.open
    start = fixtures.RoadmapToolsTest.start
    finish = fixtures.RoadmapToolsTest.finish

    async def setup_remote(self):
        self.directory = self.root / 'RemoteHosts'; self.runtime = self.root / 'RemoteRuntime'; self.runtime.mkdir(mode=0o700)
        host = remote_catalog.operation(self.directory, {'operation': 'create', 'input': {'requestId': str(uuid.uuid4()), 'name': 'Own reserved-profile target', 'address': '127.0.0.1'}})
        original = remote_checks.begin(self.directory, host['id'], {'requestId': str(uuid.uuid4()), 'revision': 1})
        self.host = remote_checks.finish(self.directory, original, {'status': 'success', 'version': '0.0.1', 'kernel': '0.0.2', 'key': key()})['host']
        from store import connect, operation
        from contextlib import closing
        with closing(connect(self.projects)) as db:
            operation(db, {'operation': 'update', 'id': self.pid, 'input': {'revision': 1, 'remoteHostId': self.host['id']}}, self.r4os)
        self.calls = []; self.reached = asyncio.Event(); self.release = asyncio.Event(); self.release.set(); case = self
        self.outcome = {'stdout': 'Fixed SSH-boundary output', 'stderr': '', 'commandExitCode': 0, 'sshExitCode': 0,
                        'commandReturnConfirmed': True, 'localClientEndConfirmed': True, 'remoteProcessEndConfirmed': False,
                        'transportUncertain': False, 'dispatched': True}
        class Transport:
            def __init__(self, target, *_): assert target['password'] == 'rosebud'
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            async def execute_complete(self, command, timeout, abort):
                case.calls.append(command); case.reached.set()
                allowed = asyncio.create_task(case.release.wait()); stopped = asyncio.create_task(abort.wait())
                try:
                    await asyncio.wait((allowed, stopped), return_when=asyncio.FIRST_COMPLETED)
                    if abort.is_set(): return {**case.outcome, 'commandExitCode': None, 'commandReturnConfirmed': False, 'transportUncertain': True, 'stoppedLocally': True}
                    return case.outcome
                finally:
                    allowed.cancel(); stopped.cancel(); await asyncio.gather(allowed, stopped, return_exceptions=True)
        self.broker = remote_host.Host({'directory': str(self.directory), 'runtime': str(self.runtime), 'uid': os.getuid()}, transport=Transport, allow_agent_profile=True)
        self.server = agent_channel.start(self.broker, self.runtime / 'agent.sock', asyncio.get_running_loop())
        async def close():
            await self.broker.stop(); await asyncio.to_thread(self.server.shutdown); self.server.server_close()
        self.addAsyncCleanup(close)
        worker = self.start(); self.reserve(worker); return worker

    def reserve(self, worker, profile='studio-tools-v9', enabled=True):
        # Full native declaration/admission compatibility is intentionally tested
        # in0.6.19. This fixture changes only trusted stored engine/config fields.
        config = json.loads(worker.store.db.execute('SELECT config FROM runs WHERE id=?', (worker.run_id,)).fetchone()[0])
        config['engine']['profile'] = profile; config['remoteHostBinding'] = self.host
        config['permissions'].update({'studio.' + name: enabled for name in ('run_remote_command', 'read_remote_job', 'stop_remote_job')})
        engine = json.loads(worker.store.row(worker.session_id)['engine']); engine['profile'] = profile
        with worker.store.db:
            worker.store.db.execute('UPDATE sessions SET engine=? WHERE id=?', (encode(engine), worker.session_id))
            worker.store.db.execute('UPDATE runs SET config=? WHERE id=?', (encode(config), worker.run_id))
        worker.config = config

    async def call(self, worker, tool, arguments, descriptor=None, project_id=None, wait=False):
        call_id = str(uuid.uuid4()); hashed = hashlib.sha256(encode({'tool': 'studio_' + tool, 'arguments': arguments}).encode()).hexdigest()
        with worker.store.db: worker.store.db.execute('INSERT INTO tools VALUES (?,?,?,?,?,?,NULL)', (worker.run_id, call_id, 'studio_' + tool, hashed, 'intent', encode(arguments)))
        birth = (Path('/proc') / str(os.getpid()) / 'stat').read_text().rsplit(') ', 1)[1].split()[19]
        frame = {'protocol': 1, 'operation': 'tool', 'projectId': project_id or self.pid, 'tool': tool, 'callId': call_id, 'arguments': arguments,
                 'actor': {'sessionId': worker.session_id, 'runId': worker.run_id, 'workerPid': os.getpid(), 'workerBirth': birth,
                           'release': worker.manifest['release'], 'revision': worker.config['revision']}}
        descriptor = worker.lease.fileno() if descriptor is None else descriptor
        proc = await asyncio.create_subprocess_exec('/usr/bin/python3', '-B', str(REMOTE / 'agent_call.py'), str(self.runtime / 'agent.sock'), str(descriptor), *(['--wait'] if wait else []), pass_fds=(descriptor,),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        raw, error = await asyncio.wait_for(proc.communicate(encode(frame).encode()), 15)
        self.assertFalse(error, error.decode()); return json.loads(raw)

    async def good(self, *args, **kwargs):
        value = await self.call(*args, **kwargs); self.assertIn('result', value, value); return value['result']

    async def wait(self): await asyncio.gather(*(entry['task'] for entry in tuple(self.broker.commands.active.values())))

    async def test_actual_inherited_lease_original_request_and_lost_reply_lookup(self):
        worker = await self.setup_remote(); arguments = {'requestId': str(uuid.uuid4()), 'command': 'VER'}
        first = await self.good(worker, 'run_remote_command', arguments); await self.wait()
        replay = await self.good(worker, 'run_remote_command', arguments)
        self.assertEqual(first['id'], replay['id']); self.assertEqual(replay['state'], 'completed'); self.assertEqual(self.calls, ['VER'])
        by_request = await self.good(worker, 'read_remote_job', {'requestId': arguments['requestId']})
        self.assertEqual(by_request, replay); self.assertNotIn('rosebud', json.dumps(replay))
        changed = await self.call(worker, 'run_remote_command', {**arguments, 'command': 'OTHER'})
        self.assertEqual(changed['code'], 409); self.assertEqual(self.calls, ['VER'])
        with job_store.connection(self.projects, self.pid) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0], 1)
        self.assertEqual((self.projects / self.pid / 'Workspace/module.R4MF').read_text(), 'R4OS_MODULE_MANIFEST=2\n')

    async def test_off_old_profile_foreign_project_and_reopened_lock_cannot_dispatch(self):
        worker = await self.setup_remote(); arguments = {'requestId': str(uuid.uuid4()), 'command': 'VER'}
        self.reserve(worker, enabled=False); self.assertEqual((await self.call(worker, 'run_remote_command', arguments))['code'], 403)
        self.reserve(worker, profile='studio-tools-v8'); self.assertEqual((await self.call(worker, 'run_remote_command', arguments))['code'], 403)
        self.reserve(worker)
        self.assertEqual((await self.call(worker, 'run_remote_command', arguments, project_id=str(uuid.uuid4())))['code'], 403)
        from owner import open_lock
        with open_lock(self.projects, 'project', self.pid) as reopened:
            self.assertEqual((await self.call(worker, 'run_remote_command', arguments, descriptor=reopened.fileno()))['code'], 403)
        self.assertFalse(self.calls); self.assertFalse((self.projects / self.pid / 'RemoteHosts/Jobs.sqlite').exists())

    async def test_stop_preserves_unknown_effect_and_blocks_target_changes_without_replay(self):
        worker = await self.setup_remote(); self.release.clear()
        original = {'requestId': str(uuid.uuid4()), 'command': 'OWN TEST COMMAND'}
        accepted = await self.good(worker, 'run_remote_command', original); await self.reached.wait()
        stopped = await self.good(worker, 'stop_remote_job', {'jobId': accepted['id']}); self.assertTrue(stopped['stopRequested']); self.assertFalse(stopped['remoteProcessEndConfirmed']); await self.wait()
        result = await self.good(worker, 'read_remote_job', {'jobId': accepted['id']})
        self.assertEqual(result['state'], 'unknown'); self.assertFalse(result['result']['remoteProcessEndConfirmed'])
        self.assertEqual((await self.good(worker, 'run_remote_command', original))['id'], accepted['id']); self.assertEqual(len(self.calls), 1)
        from catalog import CatalogFault
        with self.assertRaises(CatalogFault): remote_catalog.operation(self.directory, {'operation': 'update', 'id': self.host['id'], 'input': {'requestId': str(uuid.uuid4()), 'revision': self.host['revision'], 'password': 'own-changed-fixture'}})
        denied = await self.call(worker, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'ANOTHER WORK COMMAND'})
        self.assertEqual(denied['code'], 409); self.assertEqual(len(self.calls), 1)
        # New explicit read-only diagnosis is distinct from replaying the old effect.
        self.release.set(); await self.good(worker, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'VER'}); await self.wait(); self.assertEqual(len(self.calls), 2)

    async def test_broker_restart_marks_interrupted_original_unknown_and_does_not_run_it_again(self):
        worker = await self.setup_remote(); self.release.clear(); arguments = {'requestId': str(uuid.uuid4()), 'command': 'OWN TEST COMMAND'}
        first = await self.good(worker, 'run_remote_command', arguments); await self.reached.wait()
        # This exercises original journal recovery, without a new native request.
        await self.broker.stop(); job_store.recover(self.projects)
        result = await self.good(worker, 'run_remote_command', arguments)
        self.assertEqual(result['id'], first['id']); self.assertEqual(result['state'], 'unknown'); self.assertEqual(len(self.calls), 1)

    async def test_harness_waits_on_the_original_job_and_returns_its_confirmed_exit(self):
        worker = await self.setup_remote()
        result = await self.good(worker, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'VER'}, wait=True)
        self.assertEqual(result['state'], 'completed'); self.assertEqual(result['result']['commandExitCode'], 0)
        self.assertEqual(len(self.calls), 1); self.assertIsNotNone(result['deadlineAt'])

    async def test_another_session_cannot_read_or_stop_the_original_job(self):
        worker = await self.setup_remote(); result = await self.good(worker, 'run_remote_command', {'requestId': str(uuid.uuid4()), 'command': 'VER'}, wait=True)
        self.finish(worker)
        other_id = str(uuid.uuid4()); row = worker.store.row(worker.session_id)
        with worker.store.db:
            worker.store.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,NULL,1,'now','now')", (other_id, self.pid, 'Other own fixture', row['settings'], encode({'profile': 'studio-tools-v8'})))
        other = self.start(other_id); self.reserve(other)
        for tool in ('read_remote_job', 'stop_remote_job'):
            denied = await self.call(other, tool, {'jobId': result['id']}); self.assertEqual(denied['code'], 403)
        self.assertEqual(len(self.calls), 1)
