import asyncio
import base64
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, AsyncMock
import uuid

from access import Access, SshTransport, DEFAULT_USERNAME, DEFAULT_PASSWORD, CREDENTIAL_POLICY
from boot import BootWatch
from contracts import DevelopmentFault, encode
from lease import VmLease, inspect
from lease import birth
from layout import save


class LeaseAndAccessTests(unittest.TestCase):
    def test_lost_boot_observer_cannot_authorize_a_guest_effect(self):
        with tempfile.TemporaryDirectory() as root:
            vm_id, boot_id = str(uuid.uuid4()), str(uuid.uuid4())
            scope = {'kind': 'job', 'bootId': boot_id, 'vmRevision': 'revision'}
            with VmLease(root, vm_id, scope) as lease:
                path = lease.root / 'Boots' / (vm_id + '.json'); path.parent.mkdir()
                record = {'bootId': boot_id, 'connected': True, 'vmRevision': 'revision', 'pid': os.getpid(), 'birth': birth(os.getpid())}
                save(path, record); self.assertEqual(inspect(root, lease.id, lease.token)['vmId'], vm_id)
                record['birth'] = 'invalid'; save(path, record)
                with self.assertRaises(DevelopmentFault): inspect(root, lease.id, lease.token)
                self.assertEqual(inspect(root, lease.id, lease.token, check_boot=False)['vmId'], vm_id)

    def test_vm_lease_is_exclusive_across_projects_and_rejects_expired_owner(self):
        with tempfile.TemporaryDirectory() as root:
            vm_id, other = str(uuid.uuid4()), str(uuid.uuid4())
            with VmLease(root, vm_id, {'kind': 'job', 'projectId': str(uuid.uuid4())}) as first:
                self.assertEqual(inspect(root, first.id, first.token)['vmId'], vm_id)
                with self.assertRaises(DevelopmentFault):
                    with VmLease(root, vm_id, {'kind': 'job', 'projectId': str(uuid.uuid4())}): pass
                with VmLease(root, other, {'kind': 'job'}) as second:
                    self.assertEqual(inspect(root, second.id, second.token)['vmId'], other)
                with self.assertRaises(DevelopmentFault): inspect(root, first.id, '0' * 64)
            with self.assertRaises(DevelopmentFault): inspect(root, first.id, first.token)

    def test_access_never_enables_network_or_returns_stored_password(self):
        with tempfile.TemporaryDirectory() as root:
            projects, r4os = Path(root) / 'Projects', Path(root) / 'R4OS'; vm_id = str(uuid.uuid4())
            path = r4os / 'Instances' / vm_id / 'vm.json'; path.parent.mkdir(parents=True)
            vm = {'id': vm_id, 'revision': str(uuid.uuid4()), 'imageId': 'test-full', 'imageSha256': 'a' * 64, 'networkEnabled': False}
            path.write_text(encode(vm)); access = Access(projects, r4os, SimpleNamespace(values={}))
            request = {'revision': 0, 'vmRevision': vm['revision'], 'enabled': True}
            with patch('access.transport_profile', return_value={}):
                with self.assertRaises(DevelopmentFault): access.configure(vm_id, request)
                self.assertFalse(json.loads(path.read_text())['networkEnabled'])
                vm['networkEnabled'] = True; path.write_text(encode(vm))
                value = access.configure(vm_id, request)
                self.assertEqual(value['credentialPolicy'],CREDENTIAL_POLICY); self.assertEqual(value['username'],DEFAULT_USERNAME); self.assertNotIn('password', value)
                self.assertNotIn('private-fixture', encode(value)); self.assertFalse(value['ready'])
                self.assertEqual((access.directory(vm_id) / 'access.json').stat().st_mode & 0o777, 0o600)
                with self.assertRaises(DevelopmentFault): access.configure(vm_id, request)
                vm['imageSha256'] = 'b' * 64; path.write_text(encode(vm))
                value = access.public(vm_id); self.assertTrue(value['available']); self.assertEqual(value['credentialPolicy'],CREDENTIAL_POLICY)
                self.assertFalse(value['ready']); self.assertIsNone(value['hostKeyFingerprint'])
                # The fixed login policy remains after saving other settings.
                access.configure(vm_id, {**request, 'revision':1})
                self.assertEqual(access.record(vm_id)['password'], DEFAULT_PASSWORD)
                self.assertEqual(access.record(vm_id)['vmId'], vm_id)
                other = str(uuid.uuid4()); self.assertEqual(access.record(other)['password'],DEFAULT_PASSWORD)
                save(access.directory(other) / 'access.json', access.record(vm_id))
                with self.assertRaises(DevelopmentFault): access.record(other)

    def test_ssh_argv_and_environment_do_not_contain_credentials(self):
        transport = object.__new__(SshTransport)
        transport.runtime = Path('/private-fixture'); transport.port = 23456
        transport.record = {'password': 'private-fixture-secret', 'username': 'guest'}
        transport.vm = {'id': str(uuid.uuid4()), 'imageId': 'test-full'}
        transport.lease = SimpleNamespace(id=str(uuid.uuid4()))
        self.assertNotIn('private-fixture-secret', encode(transport.argv()) + encode(transport.environment()))
        self.assertIn('ControlMaster=no', transport.argv())
        self.assertIn('BatchMode=no', transport.argv(True))


class BootTests(unittest.IsolatedAsyncioTestCase):
    async def test_image_change_reuses_legacy_vm_login_and_relearns_only_host_key(self):
        import access as module
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); vm_id = str(uuid.uuid4())
            vm = {'id':vm_id,'revision':'new-revision','imageId':'new-full','imageSha256':'b'*64}
            access = Access(root/'Projects',root/'R4OS',SimpleNamespace(values={}))
            # An existing schema-1 record predates the explicit vmId field.
            old = {'schema':1,'revision':1,'enabled':True,'username':'guest','password':'private-fixture',
                'imageId':'old-full','imageSha256':'a'*64,'hostKeyFingerprint':'SHA256:old',
                'readiness':{'bootId':'old','vmRevision':'old-revision'}}
            save(access.directory(vm_id)/'access.json',old)
            (access.directory(vm_id)/'known_hosts').write_text('old host key\n')
            original = module.folder
            def folder(path):
                return original(root/'runtime' if str(path).startswith('/run/r4os-studio-development/auth/') else path)
            lease = SimpleNamespace(id=str(uuid.uuid4()),vm_id=vm_id,token='private-token',root=root/'state',scope={})
            with patch('access.folder',side_effect=folder), patch('access.transport_profile',return_value={}), patch('access.vm_call',new=AsyncMock()):
                transport = SshTransport(access,vm,lease)
                async with transport:
                    self.assertIn('StrictHostKeyChecking=accept-new',transport.argv())
                    self.assertEqual((transport.runtime/'password').read_text(),DEFAULT_PASSWORD)
                    self.assertFalse((transport.runtime/'known_hosts').exists())
                    (transport.runtime/'known_hosts').write_text('new-host ssh-ed25519 '+base64.b64encode(b'new-key').decode()+'\n')
                    transport.publish_host_key()
                saved = access.record(vm_id)
                self.assertEqual(saved['password'],DEFAULT_PASSWORD); self.assertEqual(saved['username'],DEFAULT_USERNAME)
                self.assertEqual(saved['vmId'],vm_id); self.assertEqual(saved['imageId'],vm['imageId'])
                self.assertNotIn('readiness',saved)
                pinned = saved['hostKeyFingerprint']
                # A key change within that same image still fails verification.
                transport = SshTransport(access,vm,lease)
                async with transport:
                    self.assertIn('StrictHostKeyChecking=yes',transport.argv())
                    (transport.runtime/'known_hosts').write_text('new-host ssh-ed25519 '+base64.b64encode(b'unexpected-key').decode()+'\n')
                    with self.assertRaises(DevelopmentFault): transport.publish_host_key()
                self.assertEqual(access.record(vm_id)['hostKeyFingerprint'],pinned)

    async def test_qmp_reset_invalidates_the_previous_boot_binding(self):
        with tempfile.TemporaryDirectory() as root:
            path = str(Path(root) / 'qmp.sock'); writers = []
            async def peer(reader, writer):
                writers.append(writer); writer.write(b'{"QMP":{}}\n'); await writer.drain()
                try:
                    while raw := await reader.readline():
                        value = json.loads(raw)
                        writer.write((encode({'id': value['id'], 'return': {'running': True} if value['id'] == 'state' else {}}) + '\n').encode()); await writer.drain()
                finally: writer.close()
            server = await asyncio.start_unix_server(peer, path)
            watcher = BootWatch(root); vm = {'id': str(uuid.uuid4()), 'revision': str(uuid.uuid4()), 'imageId': 'test', 'imageSha256': 'a' * 64}
            original = asyncio.open_unix_connection
            async def connect(*args, **kwargs): return await original(path, limit=kwargs['limit'])
            try:
                with patch('boot.asyncio.open_unix_connection', side_effect=connect):
                    first = await watcher.ensure(vm, 'a' * 32)
                    writers[0].write(b'{"event":"RESET"}\n'); await writers[0].drain()
                    for _ in range(100):
                        await asyncio.sleep(.01)
                        current = watcher.values[vm['id']]
                        if current['bootId'] != first['bootId'] and current['connected']: break
                    self.assertNotEqual(current['bootId'], first['bootId']); self.assertTrue(current['connected'])
            finally:
                await watcher.close(); server.close(); await server.wait_closed()


if __name__ == '__main__': unittest.main()
