"""Actual catalog/broker recovery, with a controlled SSH boundary and no network."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid
import checks
from catalog import operation, CatalogFault, connection
from host import Host
from test_transport import key


class CheckTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name); self.directory = self.root / 'RemoteHosts'
        self.host = operation(self.directory, {'operation': 'create', 'input': {'requestId': str(uuid.uuid4()), 'name': 'Own SSH fixture', 'address': '127.0.0.1'}})
        self.calls = 0; self.reached = asyncio.Event(); self.release = asyncio.Event(); self.release.set(); case = self
        self.outcome = {'status': 'success', 'version': '0.87.14', 'kernel': '0.68.1', 'key': key()}
        class Transport:
            def __init__(self, target, *_): assert target['password'] == 'rosebud'
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            async def check(self): case.calls += 1; case.reached.set(); await case.release.wait(); return case.outcome
        self.broker = Host({'directory': str(self.directory), 'runtime': str(self.root / 'run'), 'uid': 0}, transport=Transport)
        self.addAsyncCleanup(self.broker.stop)

    def request(self, **extra): return {'protocol': 1, 'operation': 'test', 'hostId': self.host['id'], 'input': {'requestId': str(uuid.uuid4()), 'revision': self.host['revision']}, **extra}

    async def wait(self): await asyncio.gather(*tuple(self.broker.active.values()))

    async def test_original_receipt_trust_and_rebind_preserve_request_and_credentials(self):
        request = self.request(); await self.broker.request(request); await self.wait()
        result = await self.broker.request(request); self.assertEqual(self.calls, 1); self.assertEqual(result['phase'], 'complete')
        self.assertEqual(result['host']['lastTest']['status'], 'success'); self.assertEqual(result['host']['hostKey']['state'], 'trusted')
        self.assertNotIn('rosebud', json.dumps(result)); self.host = result['host']
        # A changed key cannot replace existing trust, even if a defective
        # transport adapter were to return success with a different key.
        self.outcome = {**self.outcome, 'key': key(b'x')}; other = self.request()
        await self.broker.request(other); await self.wait(); changed = await self.broker.request(other)
        self.assertEqual(changed['host']['lastTest']['status'], 'hostkey_changed')
        self.assertEqual(changed['host']['hostKey']['fingerprint'], result['host']['hostKey']['fingerprint'])
        rebind = {'requestId': str(uuid.uuid4()), 'revision': changed['host']['revision'], 'confirm': True}
        reset = operation(self.directory, {'operation': 'reset_trust', 'id': self.host['id'], 'input': rebind})
        self.assertEqual(reset['hostKey']['state'], 'unbound'); self.assertIsNone(reset['lastTest'])
        self.assertEqual(operation(self.directory, {'operation': 'reset_trust', 'id': self.host['id'], 'input': rebind}), reset)

    async def test_active_target_changes_block_names_survive_and_late_settings_invalidate(self):
        self.release.clear(); request = self.request(); await self.broker.request(request); await self.reached.wait()
        for op, content in [('update', {'password': 'another-fixture'}), ('remove', {'confirm': True}), ('reset_trust', {'confirm': True})]:
            with self.assertRaises(CatalogFault): operation(self.directory, {'operation': op, 'id': self.host['id'], 'input': {'requestId': str(uuid.uuid4()), 'revision': self.host['revision'], **content}})
        renamed = operation(self.directory, {'operation': 'update', 'id': self.host['id'], 'input': {'requestId': str(uuid.uuid4()), 'revision': self.host['revision'], 'name': 'Renamed while checking'}})
        with connection(self.directory) as db, db: db.execute('UPDATE hosts SET endpoint_revision=endpoint_revision+1 WHERE id=?', (self.host['id'],))
        self.release.set(); await self.wait(); result = await self.broker.request(request)
        self.assertTrue(result['invalidated']); self.assertIsNone(result['host']['lastTest']); self.assertEqual(result['host']['name'], renamed['name'])

    async def test_lost_result_file_recovers_atomic_catalog_receipt_without_second_ssh(self):
        original = checks.save
        def lose(path, value):
            if value['phase'] == 'complete': raise OSError('Own result-sidecar write interruption after catalog commit')
            return original(path, value)
        request = self.request()
        with patch.object(checks, 'save', side_effect=lose): await self.broker.request(request); await self.wait()
        result = checks.status(self.directory, self.host['id'], request['input']['requestId']); self.assertEqual(result['phase'], 'complete')
        revision = result['host']['revision']; checks.recover(self.directory)
        self.assertEqual((await self.broker.request(request))['host']['revision'], revision); self.assertEqual(self.calls, 1)

    async def test_interrupted_original_is_retained_and_never_reconnected_on_restart(self):
        self.release.clear(); request = self.request(); await self.broker.request(request); await self.reached.wait(); await self.broker.stop()
        checks.recover(self.directory); result = await self.broker.request(request)
        self.assertEqual(result['phase'], 'unknown'); self.assertEqual(self.calls, 1); self.assertFalse(self.broker.active)
        with self.assertRaises(CatalogFault): checks.status(self.directory, str(uuid.uuid4()), request['input']['requestId'])
        with self.assertRaises(CatalogFault): await self.broker.request({**request, 'input': {**request['input'], 'revision': 22}})

    async def test_failed_authentication_can_record_tofu_but_cannot_confirm_r4os(self):
        self.outcome = {'status': 'authentication_failed', 'key': key()}
        request = self.request(); await self.broker.request(request); await self.wait()
        result = await self.broker.request(request)
        self.assertEqual(result['host']['hostKey']['state'], 'trusted')
        self.assertEqual(result['host']['lastTest']['status'], 'authentication_failed')
        self.assertNotIn('version', result['host']['lastTest']); self.assertNotIn('kernel', result['host']['lastTest'])

    async def test_adoption_does_not_interrupt_checks_and_closes_new_admissions_when_idle(self):
        self.release.clear(); request = self.request(); await self.broker.request(request); await self.reached.wait()
        adoption = {'protocol': 1, 'operation': 'prepare_adoption'}
        self.assertFalse((await self.broker.request(adoption))['ready']); self.assertTrue(self.broker.accepting)
        self.release.set(); await self.wait(); self.assertTrue((await self.broker.request(adoption))['ready'])
        self.assertFalse(self.broker.accepting)
        with self.assertRaises(CatalogFault): await self.broker.request(self.request())
