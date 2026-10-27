"""Real bounded client subprocess lifecycle; the SSH executable is a local fixture."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid
from transport import RemoteTransport


class CommandTransport(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)
        self.target = {'id': str(uuid.uuid4()), 'endpointRevision': 1, 'address': '127.0.0.1', 'port': 22, 'user': 'own_user',
                       'password': 'own-command-fixture-secret', 'key': {'state': 'unbound'}}

    async def call(self, code, timeout=2, abort=None):
        async with RemoteTransport(self.target, self.root / 'run', str(uuid.uuid4())) as client:
            with patch.object(client, 'argv', return_value=['/usr/bin/python3', '-c', code]):
                result = await client.execute_complete('VER', timeout, abort or asyncio.Event())
            self.assertFalse(client.processes)
        self.assertFalse(client.runtime.exists()); return result

    async def test_exit_stdout_stderr_and_password_redaction_do_not_claim_remote_process_end(self):
        result = await self.call("import sys; print('output own-command-fixture-secret'); sys.stderr.write('native warning'); sys.exit(7)")
        self.assertEqual(result['commandExitCode'], 7); self.assertTrue(result['commandReturnConfirmed'])
        self.assertFalse(result['transportUncertain']); self.assertIn('[redacted password]', result['stdout'])
        self.assertEqual(result['stderr'], 'native warning'); self.assertTrue(result['localClientEndConfirmed']); self.assertFalse(result['remoteProcessEndConfirmed'])

    async def test_exit_255_timeout_stop_and_output_limit_remain_uncertain(self):
        self.assertTrue((await self.call('raise SystemExit(255)'))['transportUncertain'])
        result = await self.call("import time; print('before timeout',flush=True); time.sleep(10)", timeout=.1)
        self.assertTrue(result['timedOut']); self.assertTrue(result['transportUncertain']); self.assertIn('before timeout', result['stdout'])
        event = asyncio.Event()
        async def stop(): await asyncio.sleep(.1); event.set()
        stopper = asyncio.create_task(stop())
        result = await self.call('import time; time.sleep(10)', abort=event); await stopper
        self.assertTrue(result['stoppedLocally']); self.assertTrue(result['transportUncertain']); self.assertFalse(result['remoteProcessEndConfirmed'])
        result = await self.call("print('x'*100000)")
        self.assertTrue(result['outputTruncated']); self.assertTrue(result['transportUncertain']); self.assertLessEqual(len(result['stdout'].encode()), 32768)

    async def test_stop_before_launch_does_not_spawn_or_invent_a_remote_exit(self):
        event = asyncio.Event(); event.set(); result = await self.call("raise RuntimeError('must not execute')", abort=event)
        self.assertFalse(result['dispatched']); self.assertFalse(result['transportUncertain']); self.assertIsNone(result['commandExitCode']); self.assertFalse(result['commandReturnConfirmed'])
