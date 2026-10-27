"""Actual pinned client configuration/askpass; SSH responses are fixed fixtures."""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import uuid
from transport import RemoteTransport, key_receipt


def key(seed=b'k'):
    kind = b'ssh-ed25519'; raw = len(kind).to_bytes(4, 'big') + kind + (32).to_bytes(4, 'big') + seed * 32
    return {'keyType': kind.decode(), 'keyData': base64.b64encode(raw).decode(),
            'fingerprint': 'SHA256:' + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')}


class TransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)
        self.target = {'id': str(uuid.uuid4()), 'endpointRevision': 1, 'address': 'own-fixture.example', 'port': 2222, 'user': 'own_user',
                       'password': 'own-private-fixture-password', 'key': {'state': 'unbound'}}

    async def test_pinned_clients_accept_fixed_dns_ipv4_ipv6_options_and_private_askpass(self):
        for address in ('own-fixture.example', '127.0.0.1', '2001:db8::1'):
            async with RemoteTransport({**self.target, 'address': address}, self.root / 'run', str(uuid.uuid4())) as client:
                args = client.argv(); environment = client.environment()
                self.assertNotIn(self.target['password'], json.dumps([args, environment]))
                config = subprocess.run(args + ['-G', client.destination()], capture_output=True, text=True, check=True).stdout
                self.assertIn('user own_user', config); self.assertIn('port 2222', config)
                self.assertIn('stricthostkeychecking accept-new', config); self.assertIn('forwardagent no', config)
                answer = subprocess.check_output([environment['SSH_ASKPASS']], env=environment, text=True)
                self.assertEqual(answer, self.target['password'] + '\n')
                self.assertEqual((client.runtime / 'password').stat().st_mode & 0o777, 0o600)
            self.assertFalse(client.runtime.exists())

    async def test_only_authenticated_version_and_real_exit_status_confirm_r4os(self):
        async with RemoteTransport(self.target, self.root / 'run', str(uuid.uuid4())) as client:
            observed = key(); path = client.runtime / 'known_hosts'
            path.write_text(client.alias + ' ' + observed['keyType'] + ' ' + observed['keyData'] + '\n'); path.chmod(0o600)
            self.assertEqual(key_receipt(path, client.alias, 2222), observed)
            cases = [({'exitCode': 0, 'stdout': 'R4OS Release 0.87.14\nKernel active 0.68.1\n', 'stderr': ''}, 'success'),
                     ({'exitCode': 1, 'stdout': 'R4OS Release 0.87.14\nKernel active 0.68.1\n', 'stderr': ''}, 'not_r4os'),
                     ({'exitCode': 0, 'stdout': 'Other OS', 'stderr': ''}, 'not_r4os'),
                     ({'exitCode': 0, 'stdout': 'R4OS Release ' + '1'*100 + '.1.1\nKernel active 0.68.1\n', 'stderr': ''}, 'not_r4os'),
                     ({'exitCode': 255, 'stdout': '', 'stderr': 'Permission denied'}, 'authentication_failed'),
                     ({'exitCode': 255, 'stdout': '', 'stderr': 'Host key verification failed'}, 'hostkey_changed'),
                     ({'exitCode': 255, 'stdout': '', 'stderr': 'Connection refused'}, 'offline'),
                     ({'exitCode': 255, 'stdout': '', 'stderr': 'Connection timed out'}, 'timeout'),
                     ({'exitCode': 255, 'stdout': '', 'stderr': 'Unexpected disconnect'}, 'transport_error')]
            for response, expected in cases:
                with patch.object(client, 'execute', AsyncMock(return_value=response)) as execute:
                    result = await client.check(); self.assertEqual(result['status'], expected); execute.assert_awaited_once_with('VER')
                    self.assertNotIn('stdout', result); self.assertNotIn('stderr', result)
            with patch.object(client, 'execute', AsyncMock(side_effect=asyncio.TimeoutError)):
                self.assertEqual((await client.check())['status'], 'timeout')

    async def test_known_key_is_strict_and_private_runtime_is_not_silently_reused(self):
        observed = key()
        target = {**self.target, 'key': {'state': 'trusted', 'key_type': observed['keyType'], 'key_data': observed['keyData'], 'fingerprint': observed['fingerprint']}}
        request = str(uuid.uuid4())
        async with RemoteTransport(target, self.root / 'run', request) as client:
            self.assertIn('StrictHostKeyChecking=yes', client.argv())
            with self.assertRaises(FileExistsError):
                async with RemoteTransport(target, self.root / 'run', request): pass

    async def test_second_broker_cannot_replace_an_owned_runtime_socket(self):
        from host import runtime_lock
        from catalog import CatalogFault
        runtime = self.root / 'run'; runtime.mkdir(mode=0o700)
        with runtime_lock(runtime):
            with self.assertRaises(CatalogFault):
                with runtime_lock(runtime): pass
