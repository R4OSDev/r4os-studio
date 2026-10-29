"""Gesture receipts keep image bytes transient and partial input explicit."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
import uuid
from development_tools import DevelopmentTools


class GestureOutputTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.worker = SimpleNamespace(run_id=str(uuid.uuid4()), manifest={'projectId': str(uuid.uuid4())},
            config={'permissions': {'studio.capture_vm': True}})
        self.tool = DevelopmentTools(self.worker)
        self.tool.image_capable = lambda: True

    async def test_intermediate_image_is_not_embedded_in_durable_text(self):
        job = str(uuid.uuid4())
        image = {'id': str(uuid.uuid4()), 'jobId': job, 'projectId': self.worker.manifest['projectId'],
            'kind': 'screenshot', 'sha256': 'a' * 64}
        transient = {'metadata': image, 'base64': 'aW1hZ2U='}
        self.tool.request = AsyncMock(return_value={'complete': True, 'observationId': image['id'], 'observation': transient})
        result = await self.tool.call('send_vm_input', {'jobId': job, 'kind': 'gesture', 'observeAfterStep': 1, 'steps': []}, 'gesture-call')
        self.assertTrue(result['success'])
        self.assertNotIn('base64', json.loads(result['output']))
        self.assertNotIn('observation', json.loads(result['output']))
        self.assertEqual(result['_transientImage'], transient)
        native = await self.tool.native_output(result, result['_transientImage'])
        self.assertEqual(native['contentItems'][1]['imageUrl'], 'data:image/png;base64,aW1hZ2U=')
        self.assertEqual(self.tool.request.await_count, 1)

    async def test_partial_prefix_is_not_success_and_missing_image_capability_starts_nothing(self):
        self.tool.request = AsyncMock(return_value={'complete': False, 'accepted': 1, 'expected': 3, 'releaseQueued': True})
        result = await self.tool.call('send_vm_input', {'jobId': str(uuid.uuid4()), 'kind': 'gesture', 'steps': []}, 'partial')
        self.assertFalse(result['success']); self.assertEqual(json.loads(result['output'])['accepted'], 1)
        self.tool.request.reset_mock(); self.tool.image_capable = lambda: False
        result = await self.tool.call('send_vm_input', {'jobId': str(uuid.uuid4()), 'kind': 'gesture', 'observeAfterStep': 1, 'steps': []}, 'no-image')
        self.assertFalse(result['success']); self.tool.request.assert_not_awaited()
