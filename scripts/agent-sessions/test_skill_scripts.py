"""Real readonly script mounts, exit results, frozen revisions and existing rights."""
import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import uuid

import test_skill_application as fixtures
from profile import CODEX_VERSION
from run_store import admit, transition
from worker import Worker
from terminal import Terminals
from skill_scripts import bindings


@unittest.skipIf(os.getuid() == 0, 'Run script namespaces as the unprivileged service user.')
class Scripts(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture = fixtures.Application(); self.fixture.setUp(); self.f = self.fixture.fixture
        self.r4os = Path(__file__).resolve().parents[2] / 'Data/R4OS'
        if not (self.r4os / 'Toolchains/Codex' / CODEX_VERSION / 'codex').is_file(): self.skipTest('Qualified Codex absent')
        self.workspace = self.f.skills / self.f.ids[0] / 'Workspace'
        for name in ('scripts', 'references', 'assets'): (self.workspace / name).mkdir(exist_ok=True)
        package = fixtures.fixtures.packages
        package.atomic(self.workspace / 'references/value.txt', b'ORIGINAL')
        package.atomic(self.workspace / 'assets/probe.bin', bytes([0, 127, 255, 6]))
        package.atomic(self.workspace / 'scripts/report.py', b"""from pathlib import Path
import json,hashlib,socket
base=Path(__file__).resolve().parents[1]
value={'word':(base/'references/value.txt').read_text(),'asset':hashlib.sha256((base/'assets/probe.bin').read_bytes()).hexdigest()}
assert not Path('/codex').exists() and not Path('/session').exists() and not Path('/Data').exists()
try: socket.create_connection(('1.1.1.1',443),timeout=.1)
except OSError: pass
else: raise AssertionError('Network unexpectedly available')
Path('/workspace/report.json').write_text(json.dumps(value))
print(json.dumps(value),flush=True)
""", True)
        package.atomic(self.workspace / 'scripts/wait.py', b"""from pathlib import Path
import time
ref=Path(__file__).resolve().parents[1]/'references/value.txt'
print('BEFORE:'+ref.read_text(),flush=True)
time.sleep(2)
print('AFTER:'+ref.read_text(),flush=True)
""", True)
        package.atomic(self.workspace / 'scripts/exit.py', b"raise SystemExit(7)\n", True)
        package.atomic(self.workspace / 'scripts/missing.py', b"import missing_skill_dependency_qa\n", True)
        self.fixture.publish(self.f.ids[0], 'Run the requested script from scripts/.')
        self.worker = None

    async def asyncTearDown(self):
        if self.worker: await self.finish()
        self.fixture.tearDown()

    async def finish(self):
        await self.worker.cleanup()
        transition(self.worker.store, self.worker.run_id, 'completed')
        self.worker.store.close(); self.worker = None

    def start(self, scripts=True):
        with self.fixture.open() as store:
            data = {'requestId': str(uuid.uuid4()), 'revision': store.get(self.fixture.session['id'])['revision'],
                    'text': 'Execute the requested skill script.', 'skillSelection': 1}
            if scripts: data['skillScripts'] = 1
            run, _ = admit(store, self.fixture.session['id'], data, self.f.providers)
        self.worker = Worker({**self.fixture.manifest(run), 'r4os': str(self.r4os)})
        self.worker.thread_id = 'thread'; self.worker.turn_id = 'turn'
        return self.worker

    async def execute(self, command, **fields):
        return await self.worker.terminals.call('exec_command', {'cmd': command, 'yield_time_ms': 100, **fields})

    async def poll(self, result):
        output = result['output']
        for _ in range(80):
            if result['state'] == 'exited': return result, output
            result = await self.worker.terminals.call('write_stdin', {'processId': result['processId'], 'yield_time_ms': 100})
            output += result['output']
        self.fail('Process did not reach an actual exit status')

    async def test_script_reads_frozen_assets_writes_selected_workspace_and_cannot_modify_revision(self):
        worker = self.start(); ident = self.f.ids[0]
        self.assertFalse((worker.store.workspace / 'report.json').exists())
        result, output = await self.poll(await self.execute('/usr/bin/python3 /skills/'+ident+'/scripts/report.py'))
        self.assertEqual(result['exitCode'], 0, output)
        report = json.loads((worker.store.workspace / 'report.json').read_text())
        self.assertEqual(report['word'], 'ORIGINAL'); self.assertEqual(len(report['asset']), 64)
        result, output = await self.poll(await self.execute('printf bad > /skills/'+ident+'/references/value.txt'))
        self.assertNotEqual(result['exitCode'], 0); self.assertIn('Read-only', output)
        self.assertEqual((self.workspace / 'references/value.txt').read_text(), 'ORIGINAL')
        self.assertEqual(len(worker.sandbox.script_roots), 1)
        self.assertFalse(any(path.name.startswith('__studio_skills__') for path in worker.store.workspace.iterdir()))

    async def test_live_script_keeps_old_revision_and_next_run_uses_new_revision(self):
        worker = self.start(); ident = self.f.ids[0]
        result = await self.execute('/usr/bin/python3 /skills/'+ident+'/scripts/wait.py')
        output = result['output']
        while 'BEFORE:ORIGINAL' not in output:
            result = await worker.terminals.call('write_stdin', {'processId': result['processId'], 'yield_time_ms': 100}); output += result['output']
        fixtures.fixtures.packages.atomic(self.workspace / 'references/value.txt', b'NEW')
        self.fixture.publish(ident, 'Run updated scripts.')
        result, tail = await self.poll(result); output += tail
        self.assertEqual(result['exitCode'], 0); self.assertIn('AFTER:ORIGINAL', output)
        await self.finish(); self.start()
        result, output = await self.poll(await self.execute('/usr/bin/python3 /skills/'+ident+'/scripts/report.py'))
        self.assertEqual(result['exitCode'], 0); self.assertIn('"word": "NEW"', output)

    async def test_missing_dependencies_failures_timeouts_and_cleanup_have_actual_status(self):
        worker = self.start(); root = '/skills/'+self.f.ids[0]
        for command, expected in [('/usr/bin/python3 '+root+'/scripts/exit.py', 7),
                                  ('/usr/bin/python3 '+root+'/scripts/missing.py', 1),
                                  ('missing-skill-interpreter '+root+'/scripts/report.py', 127)]:
            result, _ = await self.poll(await self.execute(command)); self.assertEqual(result['exitCode'], expected)
        result, _ = await self.poll(await self.execute('sleep 60', timeout_ms=200))
        self.assertEqual(result['reason'], 'timeout'); self.assertNotEqual(result['exitCode'], 0)
        pending = await self.execute('sleep 60')
        await worker.terminals.close()
        self.assertTrue(worker.terminals.processes[pending['processId']].finished.is_set())
        self.assertIsNotNone(worker.terminals.processes[pending['processId']].proc.returncode)

    async def test_legacy_scope_disabled_skill_and_disabled_exec_do_not_gain_an_execution_path(self):
        self.start(scripts=False)
        self.assertEqual(bindings(self.worker), [])
        result, _ = await self.poll(await self.execute('test ! -e /skills'))
        self.assertEqual(result['exitCode'], 0)
        await self.finish()
        with self.fixture.open() as store:
            permissions = store.get(self.fixture.session['id'])['permissions'] | {'studio.exec_command': False}
            store.update(self.fixture.session['id'], {'revision': 1, 'permissions': permissions}, self.f.providers)
        worker = self.start()
        result = await worker.tool({'namespace': None, 'threadId': 'thread', 'turnId': 'turn', 'tool': 'studio_exec_command',
                                   'arguments': {'cmd': 'must-not-execute'}, 'callId': 'disabled-script'})
        self.assertIn('disabled', result['contentItems'][0]['text'])
        self.assertIsNone(worker.sandbox.context)
        await self.finish()
        with self.fixture.open() as store:
            store.update(self.fixture.session['id'], {'revision': 2, 'skillOverrides': {self.f.ids[0]: False}}, self.f.providers)
        self.start(); self.assertEqual(bindings(self.worker), [])


class StopAdmission(unittest.IsolatedAsyncioTestCase):
    async def test_accepted_stop_during_preparation_prevents_a_new_process(self):
        from test_runs import Runs
        fixture = Runs(); fixture.setUp()
        with fixture.open() as store:
            run, _ = admit(store, fixture.sid, fixture.data, fixture.providers)
            async def prepare(): transition(store, run['id'], 'stopping')
            box = SimpleNamespace(prepare=prepare, file=AsyncMock(return_value={'success': True}), command=lambda *args: ['/bin/false'])
            manager = Terminals(SimpleNamespace(store=store, run_id=run['id'], session_id=fixture.sid, sandbox=box))
            with patch('terminal.asyncio.create_subprocess_exec', AsyncMock()) as spawn:
                result = await manager.call('exec_command', {'cmd': 'must not start'})
                self.assertEqual(result['error'], 'interrupted'); spawn.assert_not_called()
        fixture.tearDown()


if __name__ == '__main__': unittest.main()
