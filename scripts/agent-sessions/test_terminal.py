import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
import uuid
from test_runs import Runs
from run_store import admit
from terminal import Terminals, bounded_text
from session_store import encode


class Box:
    async def prepare(self): pass
    async def file(self, *args): return {'success': True}
    def command(self, command, workdir):
        args = ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-pid', '--unshare-net']
        for path in ('/usr', '/lib', '/lib64'):
            if Path(path).exists(): args += ['--ro-bind', path, path]
        return args + ['--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp', '--chdir', '/tmp', '--clearenv', '--setenv', 'PATH', '/usr/bin', *command]


class TextBounds(unittest.TestCase):
    def test_unicode_and_control_output_bound_actual_encoded_size(self):
        for value in ('\x01'*100000, '🦀\n'*100000):
            for tail in (False, True):
                text, clipped = bounded_text(value, 60000, tail)
                self.assertTrue(clipped); self.assertLessEqual(len(encode(text).encode()), 60000)
                self.assertTrue(value.endswith(text) if tail else value.startswith(text))
        self.assertEqual(bounded_text('small', 60000), ('small', False))


@unittest.skipIf(os.getuid() == 0, 'Run this namespace test as an unprivileged user.')
class Terminal(unittest.TestCase):
    def test_completed_commands_reuse_slots_and_old_handles_retain_final_status(self):
        fixture = Runs(); fixture.setUp()
        store = fixture.open().__enter__()
        try:
            run, _ = admit(store, fixture.sid, fixture.data, fixture.providers)
            worker = SimpleNamespace(store=store, session_id=fixture.sid, run_id=run['id'], sandbox=Box())
            manager = Terminals(worker)
            async def scenario():
                first = None
                try:
                    for _ in range(65):
                        result = await manager.call('exec_command', {'cmd': 'printf OK', 'yield_time_ms': 100})
                        self.assertTrue(result['success'], result); first = first or result['processId']
                        while result['state'] != 'exited':
                            result = await manager.call('write_stdin', {'processId': result['processId'], 'yield_time_ms': 100})
                        self.assertEqual(result['exitCode'], 0); self.assertLessEqual(len(manager.processes), 32)
                    self.assertNotIn(first, manager.processes)
                    for name in ('write_stdin', 'terminate_process'):
                        ended = await manager.call(name, {'processId': first})
                        self.assertTrue(ended['success']); self.assertEqual(ended['state'], 'exited'); self.assertEqual(ended['exitCode'], 0)
                        self.assertEqual(ended['output'], '')
                    rejected = await manager.call('write_stdin', {'processId': first, 'chars': 'must not execute'})
                    self.assertEqual(rejected['error'], 'processExited')
                    self.assertEqual(store.db.execute("SELECT count(*) FROM items WHERE json_extract(payload,'$.type')='terminal'").fetchone()[0], 65)
                    self.assertEqual((await manager.call('write_stdin', {'processId': str(uuid.uuid4())}))['error'], 'unknownProcess')
                finally: await manager.close()
            asyncio.run(scenario())
        finally: store.close(); fixture.tearDown()

    def test_four_live_processes_still_limit_concurrency(self):
        fixture = Runs(); fixture.setUp()
        store = fixture.open().__enter__()
        try:
            run, _ = admit(store, fixture.sid, fixture.data, fixture.providers)
            worker = SimpleNamespace(store=store, session_id=fixture.sid, run_id=run['id'], sandbox=Box())
            manager = Terminals(worker)
            async def scenario():
                try:
                    for _ in range(4):
                        self.assertTrue((await manager.call('exec_command', {'cmd': 'sleep 60', 'yield_time_ms': 100}))['success'])
                    self.assertEqual((await manager.call('exec_command', {'cmd': 'printf extra'}))['error'], 'processLimit')
                    self.assertEqual(len(manager.processes), 4)
                finally: await manager.close()
            asyncio.run(scenario())
        finally: store.close(); fixture.tearDown()

    def test_completed_processes_with_pending_output_are_not_discarded(self):
        fixture = Runs(); fixture.setUp()
        store = fixture.open().__enter__()
        try:
            run, _ = admit(store, fixture.sid, fixture.data, fixture.providers)
            worker = SimpleNamespace(store=store, session_id=fixture.sid, run_id=run['id'], sandbox=Box())
            manager = Terminals(worker)
            async def scenario():
                for _ in range(32):
                    finished = asyncio.Event(); finished.set()
                    manager.processes[str(uuid.uuid4())] = SimpleNamespace(finished=finished, pending='Keep this output')
                result = await manager.call('exec_command', {'cmd': 'printf must-not-start'})
                self.assertEqual(result['error'], 'processLimit'); self.assertEqual(len(manager.processes), 32)
                self.assertTrue(all(p.pending == 'Keep this output' for p in manager.processes.values()))
                await manager.close()
            asyncio.run(scenario())
        finally: store.close(); fixture.tearDown()

    def test_pipes_pty_timeouts_handles_and_cleanup(self):
        fixture = Runs(); fixture.setUp()
        store = fixture.open().__enter__()
        try:
            run, _ = admit(store, fixture.sid, fixture.data, fixture.providers)
            worker = SimpleNamespace(store=store, session_id=fixture.sid, run_id=run['id'], sandbox=Box())
            manager = Terminals(worker)
            async def poll(p):
                output = p['output']
                for _ in range(20):
                    if p['state'] == 'exited': return p, output
                    p = await manager.call('write_stdin', {'processId': p['processId'], 'yield_time_ms': 100}); output += p['output']
                self.fail('Process did not finish')
            async def scenario():
                p = await manager.call('exec_command', {'cmd': 'read -r line; echo "PIPE:$line"; echo ERR >&2', 'yield_time_ms': 100})
                p = await manager.call('write_stdin', {'processId': p['processId'], 'chars': 'input\n', 'closeStdin': True})
                p, text = await poll(p); self.assertIn('PIPE:input', text); self.assertIn('ERR', text); self.assertEqual(p['exitCode'], 0)
                p = await manager.call('exec_command', {'cmd': 'test -t 0; read -r line; echo "TTY:$line"', 'tty': True, 'yield_time_ms': 100})
                p = await manager.call('write_stdin', {'processId': p['processId'], 'chars': 'input\n'})
                p, text = await poll(p); self.assertIn('TTY:input', text)
                p = await manager.call('exec_command', {'cmd': 'cat', 'tty': True, 'yield_time_ms': 100})
                p = await manager.call('write_stdin', {'processId': p['processId'], 'closeStdin': True})
                p, _ = await poll(p); self.assertEqual(p['exitCode'], 0)
                p = await manager.call('exec_command', {'cmd': 'echo CTRL_C_READY; sleep 60', 'tty': True, 'yield_time_ms': 100})
                p = await manager.call('write_stdin', {'processId': p['processId'], 'chars': '\x03'})
                p, _ = await poll(p); self.assertIsNotNone(p['exitCode']); self.assertNotEqual(p['exitCode'], 0)
                p = await manager.call('exec_command', {'cmd': "python3 -c 'print(chr(120)*350000)'", 'yield_time_ms': 100})
                p, _ = await poll(p); self.assertEqual(p['exitCode'], 0)
                transcript = manager.processes[p['processId']].value
                self.assertTrue(transcript['truncated']); self.assertLessEqual(len(encode(transcript['output']).encode()), 120000)
                p = await manager.call('exec_command', {'cmd': 'sleep 60', 'timeout_ms': 200, 'yield_time_ms': 100})
                p, _ = await poll(p); self.assertEqual(p['reason'], 'timeout')
                p = await manager.call('exec_command', {'cmd': 'sleep 60', 'yield_time_ms': 100})
                result = await manager.call('write_stdin', {'processId': str(uuid.uuid4()), 'chars': 'x'})
                self.assertFalse(result['success'])
                await manager.close(); self.assertTrue(manager.processes[p['processId']].finished.is_set())
                self.assertIsNotNone(manager.processes[p['processId']].proc.returncode)
            asyncio.run(scenario())
        finally: store.close(); fixture.tearDown()


if __name__ == '__main__': unittest.main()
