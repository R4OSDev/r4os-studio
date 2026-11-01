"""Original boot scope, durable handoff ordering and loss-only reconciliation."""
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from contracts import UnconfirmedGuestEffect
from desktop_evidence import TOKEN, prepare, unpack, handoff
from deskrun import receipt

LAUNCH = {'request': '11:18446744073709551614:22:33', 'phase': 'process', 'error': 'ok',
          'errorlevel': 0, 'process_id': 44, 'process_generation': '55', 'window': 0,
          'content': '0', 'raw': 0, 'terminal': False, 'evidence_retained': True,
          'evidence_unavailable': False, 'evidence_scope_available': True,
          'evidence_epoch': ['18446744073709551615', '99', '7'],
          'control_requested': False, 'control_result': 0, 'control_grant': '0'}


class ScopeTest(unittest.TestCase):
    def test_lossless_original_epoch_and_intent(self):
        token = prepare(LAUNCH, [1, 2, 3]); fields = unpack(token)
        self.assertEqual(len(base64.b64decode(token)), 128)
        self.assertEqual(fields[3], 18446744073709551614)
        self.assertEqual(fields[10:13], (18446744073709551615, 99, 7))
        self.assertEqual(fields[14:], (1, 2, 3))
        self.assertIsNone(prepare({**LAUNCH, 'evidence_scope_available': False}))

    def test_new_receipt_and_missing_original_scope(self):
        value = {**LAUNCH, 'process_generation': 55, 'content': 0}
        self.assertEqual(receipt(json.dumps(value).encode())['evidence_epoch'], LAUNCH['evidence_epoch'])
        self.assertFalse(receipt(json.dumps({**value, 'evidence_epoch': ['0']*3, 'evidence_scope_available': False}).encode())['evidence_scope_available'])
        for changes in ({'evidence_epoch': [1, 2, 3]}, {'evidence_epoch': ['0']*3},
                        {'control_grant': '18446744073709551616'}, {'evidence_scope_available': 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                receipt(json.dumps({**value, **changes}).encode())


class HandoffTest(unittest.IsolatedAsyncioTestCase):
    async def run_handoff(self, lost=None, wrong=False):
        operations = []
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            last_op = None
            async def call(_, **args):
                nonlocal last_op
                op = args['evidenceOperation']; operations.append(op)
                fields = list(unpack(args['evidenceToken']))
                saved = json.loads((work / 'desktop-evidence.json').read_text())
                self.assertEqual(saved['token'], args['evidenceToken'])
                if op == lost:
                    last_op = op
                    return {'transportError': -10}
                effective = last_op if op == 'status' else op
                if effective == 'reserve':
                    fields[13] = 123; phase = 1
                elif effective == 'offer':
                    fields[6:10] = [45 if wrong else 44, 55, 66, 77]; phase = 3
                else:
                    self.assertEqual(effective, 'ack'); phase = 4
                token = base64.b64encode(TOKEN.pack(*fields)).decode()
                return {'token': token, 'phase': phase, 'result': -7, 'serial': str(fields[13]),
                        'instanceId': fields[6], 'generation': str(fields[7])}
            control = type('Control', (), {})(); control.call = AsyncMock(side_effect=call)
            if wrong:
                with self.assertRaises(UnconfirmedGuestEffect): await handoff(control, work, LAUNCH)
            else:
                token = await handoff(control, work, LAUNCH)
                self.assertEqual(unpack(token)[6:8], (44, 55))
                self.assertEqual(json.loads((work/'desktop-evidence.json').read_text())['phase'], 4)
        return operations

    async def test_persisted_canonical_token_precedes_ack(self):
        self.assertEqual(await self.run_handoff(), ['reserve', 'offer', 'ack'])

    async def test_each_lost_rpc_is_resolved_by_status_without_new_reference(self):
        for op in ('reserve', 'offer', 'ack'):
            with self.subTest(op=op):
                operations = await self.run_handoff(lost=op)
                self.assertEqual(operations.count('reserve'), 1)
                self.assertEqual(operations.count('offer'), 1)
                self.assertEqual(operations.count('ack'), 1)
                self.assertEqual(operations[operations.index(op)+1], 'status')

    async def test_different_child_never_acknowledged(self):
        self.assertEqual(await self.run_handoff(wrong=True), ['reserve', 'offer'])


class RecoveryTest(unittest.IsolatedAsyncioTestCase):
    async def test_failed_handoff_still_binds_known_child_for_watchdog_cleanup(self):
        from types import SimpleNamespace
        from deskrun import DesktopLaunch
        owner = SimpleNamespace(control=SimpleNamespace(call=AsyncMock()), work=Path('/unused'), store=object(),
            job={'id': 'job', 'settings': {'timeoutSeconds': 45, 'arguments': ''}}, output=lambda _: None)
        launch = DesktopLaunch(owner, object(), {'guestDirectory': r'C:\Build\P0000001\D0000001',
            'helperCapabilities': {'desktopEvidenceVersion': 1}}, None)
        launch.query = AsyncMock(return_value=LAUNCH); launch.key = LAUNCH['request']; launch.evidence_launch = LAUNCH
        with patch('desktop_evidence.handoff', AsyncMock(side_effect=UnconfirmedGuestEffect('Lost ACK'))):
            with self.assertRaises(UnconfirmedGuestEffect): await launch.start()
        owner.control.call.assert_awaited_once()
        call = owner.control.call.await_args
        self.assertEqual(call.args, ('adopt_desktop',))
        self.assertEqual((call.kwargs['instanceId'], call.kwargs['generation']), (44, '55'))
        self.assertNotIn('evidenceToken', call.kwargs)

    async def test_fresh_observer_uses_original_boot_and_keeps_cleanup_independent(self):
        import hashlib
        from types import SimpleNamespace
        from desktop_evidence import recover
        from layout import save
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); work = root/'ExecutionWork/job'; work.mkdir(parents=True)
            output = root/'Evidence/job'; output.mkdir(parents=True); (output/'output.log').write_bytes(b'old prefix')
            fields = list(unpack(prepare(LAUNCH, [1, 2, 3]))); fields[6:10] = [44, 55, 66, 77]; fields[13] = 123
            token = base64.b64encode(TOKEN.pack(*fields)).decode()
            target = {'vmId': 'vm', 'vmRevision': 'revision', 'imageId': 'image', 'imageSha256': 'hash', 'bootId': 'boot'}
            job = {'id': 'job', 'deploymentId': 'deployment', 'desktopLaunch': LAUNCH,
                'target': target, 'settings': {'expectedExitCode': 37, 'outputContains': ['EXPECTED']},
                'process': {'instanceId': 44, 'generation': '55'}}
            save(work/'intent.json', {'schema': 1, 'jobId': 'job', 'deploymentId': 'deployment', 'target': target,
                'executionId': 'd3631e93-8aef-4b66-9d3c-390dc30b8884', 'settings': job['settings']})
            # ACK response may be lost after the canonical Offered token was
            # persisted; Status can confirm the same acknowledged lease.
            save(work/'desktop-evidence.json', {'token': token, 'phase': 3, 'launch': LAUNCH})
            deployment = {'id': 'deployment', 'guestDirectory': r'C:\Build\P0000001\D0000001',
                'files': [{'path': '/C/Build/P0000001/D0000001/STHELP.R4X', 'bytes': 6,
                           'sha256': hashlib.sha256(b'helper').hexdigest()}], 'helperCapabilities': {'desktopEvidenceVersion': 1}}
            store = SimpleNamespace(root=root, id='project', projects=root, evidence=lambda _: output,
                deployment=lambda _: deployment, recovered=lambda *args, **kw: kw)
            boots = SimpleNamespace(ensure=AsyncMock(return_value={**target, 'bootId': 'foreign'}))
            host = SimpleNamespace(boots=boots, access=object())
            with patch('access.SshTransport') as transport:
                self.assertIsNone(await recover(store, job, host, {'id': 'vm'}, object(), {'invocationId': 'invocation'}))
                transport.assert_not_called()
            boots.ensure.return_value = target
            status = {'phase': 4, 'result': 0, 'completionSequence': '999', 'outputLength': 8,
                'outputFlags': 27, 'outputComplete': True, 'exitCode': 37, 'exitReason': 0,
                'outputBase64': base64.b64encode(b'EXPECTED').decode()}
            async def download(_, __, path, ___): path.write_bytes(b'helper')
            transport = AsyncMock(); transport.__aenter__.return_value = SimpleNamespace()
            query = AsyncMock(side_effect=[status, status, {'result': -9}])
            with patch('access.SshTransport', return_value=transport), patch('sftp.download', side_effect=download), \
                 patch('exchange.rebind', AsyncMock(return_value=(deployment, '/C/Build/P0000001/OWNER.JSN'))), \
                 patch('desktop_evidence.query_saved', query), patch('quarantine.resolve'):
                result = await recover(store, job, host, {'id': 'vm'}, object(), {'invocationId': 'invocation'})
            self.assertEqual(result['exitCode'], 37); self.assertEqual(result['check']['state'], 'passed')
            self.assertEqual((output/'output.log').read_bytes(), b'EXPECTED')
            self.assertEqual((work/'output-before-evidence-recovery.bin').read_bytes(), b'old prefix')
            proof = json.loads((work/'retained-completion.json').read_text())
            self.assertNotIn('cleanupReceipt', proof)
            self.assertTrue(proof['completion']['desktopEvidenceRetained'])
            self.assertEqual([c.args[-2] for c in query.await_args_list], ['status', 'read', 'release'])
