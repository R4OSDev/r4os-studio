import asyncio
import base64
import copy
import datetime
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock, patch
from contracts import DevelopmentFault, UnconfirmedGuestEffect, LIMITS
from guest_control import GuestControl
from execution import Execution

class ControlTest(unittest.IsolatedAsyncioTestCase):
    async def test_lost_start_receipt_is_not_replayed(self):
        writes = []
        class Input:
            def write(self, data): writes.append(data)
            async def drain(self): pass
        reader = asyncio.StreamReader(); reader.feed_eof()
        control = GuestControl(None, {}, 'owned-instance')
        control.process = SimpleNamespace(stdin=Input(), stdout=reader)
        with self.assertRaises(UnconfirmedGuestEffect): await control.call('start', role='terminal')
        self.assertEqual(len(writes), 1)
        self.assertEqual(control.sequence, 1)

    async def test_foreign_controller_receipt_is_rejected(self):
        reader = asyncio.StreamReader()
        reader.feed_data(b'{"version":1,"instance":"foreign","sequence":0,"success":true,"result":{}}\n')
        reader.feed_eof()
        control = GuestControl(None, {}, 'owned-instance'); control.process = SimpleNamespace(stdout=reader)
        with self.assertRaises(UnconfirmedGuestEffect): await control.read()

    async def test_console_limit_is_explicit_and_invalid_frame_is_not_logged(self):
        with tempfile.TemporaryDirectory() as root:
            worker = Execution.__new__(Execution); worker.log = Path(root) / 'output.log'
            worker.intent = None
            worker.output_data = b'x' * (LIMITS['outputBytes'] - 1); worker.output_limited = False
            worker.log.write_bytes(worker.output_data)
            state = {'outputBase64': base64.b64encode(b'AB').decode()}; worker.output(state)
            self.assertTrue(state['outputIncomplete'])
            self.assertEqual(worker.log.stat().st_size, LIMITS['outputBytes'])
            with self.assertRaises(UnconfirmedGuestEffect): worker.output({'outputBase64': '!invalid!'})
            self.assertEqual(worker.log.stat().st_size, LIMITS['outputBytes'])

class QuarantineTest(unittest.TestCase):
    def test_unconfirmed_guest_effect_blocks_new_work_until_a_confirmed_stop(self):
        import uuid
        from contracts import DevelopmentFault
        from quarantine import admission, claim, release, path
        with tempfile.TemporaryDirectory() as root:
            vm_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
            claim(root, vm_id, {'jobId': job_id})
            with self.assertRaises(DevelopmentFault): admission(root, vm_id, 'running')
            release(root, vm_id, str(uuid.uuid4()))
            self.assertTrue(path(root, vm_id).exists())
            admission(root, vm_id, 'stopped')
            self.assertFalse(path(root, vm_id).exists())
            self.assertTrue((path(root, vm_id).parent / 'Resolved' / (job_id + '.json')).exists())


class ClickTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.process = {'instanceId': 220, 'generation': '220', 'windowId': 1}
        self.state = {**self.process, 'state': 'running', 'windowWidth': 450, 'windowHeight': 278,
                      'windowVisible': True, 'windowFocused': True}
        self.job = {'id': 'job', 'deploymentId': 'deployment', 'process': self.process,
                    'target': {'bootId': 'boot'}}
        deployment = {'role': 'desktop', 'helperCapabilities': {'guiInput': True, 'guiFrameBindingVersion': 1}}
        self.store = SimpleNamespace(db=self.db, get=lambda _: self.job, deployment=lambda _: deployment)
        self.worker = SimpleNamespace(store=self.store, job=self.job, completion=None, output=lambda _: None)
        from frame_binding import window
        self.frame = {'kind': 'screenshot', 'bootId': 'boot', 'process': self.process,
                      'windowObservation': window(self.state), 'captureObservation': {
                          'version': 1, 'mode': 'observed-interval',
                          'completedAt': datetime.datetime.now(datetime.timezone.utc).isoformat()}}
        self.control = SimpleNamespace(call=AsyncMock(side_effect=self.guest))
        self.accepted = 2

    async def guest(self, operation, **fields):
        return {**self.state, 'inputAccepted': self.accepted}

    def message(self, x, y):
        return {'operation': 'input', 'requestId': str(uuid.uuid4()),
                'input': {'kind': 'click', 'frameId': '00c8d4a4-01a9-4367-84f8-a47fedd92bc8', 'x': x, 'y': y}}

    async def action(self, message):
        with patch('vm_worker.guard'), patch('evidence.read', return_value={'metadata': self.frame}):
            return await Execution.action(self.worker, message, copy.deepcopy(self.state), self.control, None, self.process)

    def inputs(self):
        return [call for call in self.control.call.await_args_list if call.args[0] == 'input']

    async def test_original_screen_coordinates_and_boundaries_have_durable_rejection(self):
        for x, y in ((844, 207), (450, 0), (0, 278), (-1, 0), (0, -1), (True, 0), (0, 1.5)):
            with self.subTest(x=x, y=y):
                message = self.message(x, y)
                _, result = await self.action(message)
                self.assertEqual(result['code'], 400)
                self.assertIn('450 × 278 window client area', result['error'])
                self.assertIn('x=0..449 and y=0..277', result['error'])
                self.assertIn(message['input']['frameId'], result['error'])
                row = self.db.execute('SELECT state,result FROM actions WHERE id=?', (message['requestId'],)).fetchone()
                self.assertEqual(row['state'], 'completed')
                self.assertEqual(json.loads(row['result']), result)
                calls = self.control.call.await_count
                self.assertEqual((await self.action(message))[1], result)
                self.assertEqual(self.control.call.await_count, calls)
        self.assertEqual(self.inputs(), [])

    async def test_client_edges_and_partial_acceptance_submit_once(self):
        for x, y, accepted in ((0, 0, 2), (449, 277, 2), (224, 67, 1)):
            with self.subTest(x=x, y=y, accepted=accepted):
                self.accepted = accepted
                message = self.message(x, y)
                count = len(self.inputs())
                _, result = await self.action(message)
                self.assertEqual(len(self.inputs()), count + 1)
                self.assertEqual(self.inputs()[-1].kwargs['x'], x)
                self.assertEqual(self.inputs()[-1].kwargs['y'], y)
                self.assertEqual(result['accepted'], accepted)
                self.assertEqual(result['complete'], accepted == 2)
                self.assertFalse(result['consumptionConfirmed'])
                self.assertEqual((await self.action(message))[1], result)
                self.assertEqual(len(self.inputs()), count + 1)

    async def test_changed_focus_or_window_keeps_frame_protection(self):
        for field, value in (('windowFocused', False), ('windowId', 2), ('windowWidth', 451), ('generation', '221')):
            with self.subTest(field=field):
                original = self.state[field]
                self.state[field] = value
                _, result = await self.action(self.message(20, 20))
                self.assertEqual(result['code'], 409)
                self.assertIn('Capture the owned window again', result['error'])
                self.state[field] = original
        self.assertEqual(self.inputs(), [])

    async def test_lost_guest_receipt_keeps_original_intent_without_replay(self):
        async def lost(operation, **fields):
            if operation == 'input':
                raise UnconfirmedGuestEffect('lost original input receipt')
            return dict(self.state)
        self.control.call.side_effect = lost
        message = self.message(20, 20)
        with self.assertRaises(UnconfirmedGuestEffect):
            await self.action(message)
        with self.assertRaisesRegex(DevelopmentFault, 'previous action result is unconfirmed'):
            await self.action(message)
        self.assertEqual(len(self.inputs()), 1)
        self.assertEqual(self.db.execute('SELECT state FROM actions').fetchone()[0], 'intent')

    async def test_agent_click_rechecks_original_input_authority(self):
        message = self.message(224, 67)
        message.update(owner={'sessionId': 'session', 'agentRunId': 'run'}, peerPid=42)
        with patch('authorization.authorize', return_value={'model': 'model'}) as authorize:
            _, result = await self.action(message)
        self.assertTrue(result['complete'])
        self.assertEqual(authorize.call_count, 2)
        self.assertEqual(authorize.call_args.args[2:4], ('input', 42))
        self.assertEqual(len(self.inputs()), 1)
