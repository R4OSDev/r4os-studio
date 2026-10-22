import asyncio
import base64
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from contracts import UnconfirmedGuestEffect, LIMITS
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
            worker.log.write_bytes(b'x' * (LIMITS['outputBytes'] - 1))
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
