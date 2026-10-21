import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
import uuid
from test_runs import Runs
from run_store import admit
from terminal import Terminals


class Box:
    async def prepare(self): pass
    async def file(self, *args): return {'success': True}
    def command(self, command, workdir):
        args = ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-pid', '--unshare-net']
        for path in ('/usr', '/lib', '/lib64'):
            if Path(path).exists(): args += ['--ro-bind', path, path]
        return args + ['--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp', '--chdir', '/tmp', '--clearenv', '--setenv', 'PATH', '/usr/bin', *command]


@unittest.skipIf(os.getuid() == 0, 'Run this namespace test as an unprivileged user.')
class Terminal(unittest.TestCase):
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
