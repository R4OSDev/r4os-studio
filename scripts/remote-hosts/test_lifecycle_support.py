"""Resolved peer and immutable release boundaries, without a network probe."""
import asyncio
import json
import os
from pathlib import Path
import socket
import tempfile
import subprocess
import unittest
from unittest.mock import patch
from catalog import CatalogFault
import endpoints
from adoption import candidate
from transport import RemoteTransport


class EndpointSupport(unittest.IsolatedAsyncioTestCase):
    async def test_command_cannot_be_reparsed_as_local_ssh_options_and_peer_is_pinned(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); config = root / 'untrusted-config'; config.write_text('Host *\n  Hostname own-injected.invalid\n')
            target = {'id': str(__import__('uuid').uuid4()), 'endpointRevision': 1, 'address': 'own-alias.invalid', 'connectAddress': '127.0.0.1',
                      'port': 22, 'user': 'own_user', 'password': 'own_secret', 'key': {'state': 'unbound'}}
            async with RemoteTransport(target, root / 'run', str(__import__('uuid').uuid4())) as client:
                result = await asyncio.to_thread(subprocess.run, [*client.argv(), '-G', '--', client.destination(), '-F' + str(config)], capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertIn('hostname 127.0.0.1\n', result.stdout.decode()); self.assertNotIn('own-injected.invalid', result.stdout.decode())

    async def test_resolution_normalizes_ip_aliases_pins_one_and_bounds_dns(self):
        rows = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 22)),
                (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('::ffff:127.0.0.1', 22, 0, 0)),
                (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('::1', 22, 0, 0))]
        with patch('endpoints.socket.getaddrinfo', return_value=rows): result = await endpoints.resolve({'address': 'own-alias.invalid', 'port': 22})
        self.assertEqual(result['addresses'], ['127.0.0.1', '::1']); self.assertEqual(result['connectAddress'], '127.0.0.1')
        with patch('endpoints.socket.getaddrinfo', side_effect=socket.gaierror()):
            with self.assertRaises(CatalogFault): await endpoints.resolve({'address': 'own-offline.invalid', 'port': 22})
        self.assertTrue(endpoints.overlaps(result, {'address': '127.0.0.1', 'port': 22, 'addresses': ['127.0.0.1']}))
        self.assertFalse(endpoints.overlaps(result, {**result, 'port': 2222}))

    async def test_duplicate_dns_and_ip_effect_reservations_fail_before_dispatch_and_release_all_fds(self):
        with tempfile.TemporaryDirectory() as name:
            runtime = Path(name); first = {'address': '127.0.0.1', 'port': 22, 'addresses': ['127.0.0.1']}
            alias = {'address': 'own-alias.invalid', 'port': 22, 'addresses': ['127.0.0.1', '::1']}
            held = endpoints.Reservation(runtime, first, True)
            try:
                with self.assertRaises(CatalogFault): endpoints.Reservation(runtime, alias, True)
                read = endpoints.Reservation(runtime, alias, False); read.close()
            finally: held.close()
            next_effect = endpoints.Reservation(runtime, alias, True); next_effect.close(); self.assertFalse(next_effect.descriptors)


@unittest.skipUnless(os.geteuid() == 0, 'Root-owned release validation requires a root-owned isolated fixture.')
class AdoptionSupport(unittest.TestCase):
    def test_only_matching_immutable_root_owned_compatible_release_can_be_adopted(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); base = root / 'releases'; release = base / 'own-release'
            (release / 'shared').mkdir(parents=True); (release / 'scripts/remote-hosts').mkdir(parents=True)
            (release / 'release.json').write_text(json.dumps({'id': release.name, 'version': '0.6.21'}))
            (release / 'shared/version.json').write_text(json.dumps({'version': '0.6.21'}))
            protocol = release / 'shared/remote-host.json'; protocol.write_text(json.dumps({'hostProtocol': 1, 'catalogSchema': 1, 'jobSchema': 1}))
            source = release / 'scripts/remote-hosts/host.py'; source.write_text('pass\n')
            current = root / 'current'; current.symlink_to(release)
            self.assertEqual(candidate(current, base), source)
            source.chmod(0o666)
            with self.assertRaises(ValueError): candidate(current, base)
            source.chmod(0o644); protocol.write_text(json.dumps({'hostProtocol': 1, 'catalogSchema': 1, 'jobSchema': 2}))
            with self.assertRaises(ValueError): candidate(current, base)
            protocol.write_text(json.dumps({'hostProtocol': 1, 'catalogSchema': 1, 'jobSchema': 1}))
            (release / 'release.json').write_text(json.dumps({'id': 'wrong-identity', 'version': '0.6.21'}))
            with self.assertRaises(ValueError): candidate(current, base)
