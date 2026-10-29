"""Validate whole plans, preserve accepted prefixes, never replay lost input."""
import copy
import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from contracts import DevelopmentFault, UnconfirmedGuestEffect
from gestures import execute, steps


def plan(button='left'):
    return [{'phase': 'down', 'button': button, 'x': 5, 'y': 6, 'atMilliseconds': 0},
            {'phase': 'move', 'x': 9, 'y': 8, 'atMilliseconds': 300},
            {'phase': 'up', 'button': button, 'x': 9, 'y': 8, 'atMilliseconds': 600}]


class GestureValidationTest(unittest.TestCase):
    def test_frame_scope_stays_required_before_gestures(self):
        from frame_binding import current, window
        state = {'state': 'running', 'instanceId': 9, 'generation': '99', 'windowId': 1,
            'windowWidth': 440, 'windowHeight': 300, 'windowVisible': True, 'windowFocused': True}
        job = {'process': {key: state[key] for key in ('instanceId', 'generation', 'windowId')}, 'target': {'bootId': 'boot'}}
        image = {'kind': 'screenshot', 'bootId': 'boot', 'process': dict(job['process']),
            'windowObservation': window(state), 'captureObservation': {'version': 1, 'mode': 'observed-interval',
                'completedAt': datetime.datetime.now(datetime.timezone.utc).isoformat()}}
        self.assertTrue(current(image, job, state, focused=True))
        stale = copy.deepcopy(image)
        stale['captureObservation']['completedAt'] = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=31)).isoformat()
        self.assertFalse(current(stale, job, state, focused=True))
        for change in ({'generation': '100'}, {'windowId': 2}, {'windowWidth': 441}, {'windowFocused': False}):
            self.assertFalse(current(image, job, {**state, **change}, focused=True))
        self.assertFalse(current({**image, 'bootId': 'foreign-boot'}, job, state, focused=True))

    def test_drag_double_click_right_button_and_hover(self):
        for button in ('left', 'right'):
            self.assertEqual(len(steps(plan(button), 40, 30)), 3)
        clicks = [item for item in plan() if item['phase'] != 'move']
        clicks[1]['atMilliseconds'] = 100
        clicks += [{**item, 'atMilliseconds': item['atMilliseconds'] + 200} for item in clicks]
        self.assertEqual(len(steps(clicks, 40, 30)), 4)
        self.assertEqual(steps([plan()[1]], 40, 30)[0]['button'], 'none')

    def test_invalid_plans_are_rejected_before_input(self):
        cases = [[], plan() * 11, plan()[:-1], plan()[1:],
            [{**plan()[0], 'button': 'middle'}, *plan()[1:]],
            [plan()[0], {**plan()[1], 'x': 40}, plan()[2]],
            [plan()[0], {**plan()[1], 'atMilliseconds': 2001}, plan()[2]],
            [plan()[0], {**plan()[1], 'atMilliseconds': True}, plan()[2]],
            [plan()[0], {**plan()[1], 'button': 'right'}, plan()[2]],
            [plan()[0], plan()[2], plan()[1]],
            [plan()[0], {**plan()[2], 'button': 'right'}]]
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(DevelopmentFault): steps(value, 40, 30)


class GestureExecutionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.job = {'id': 'original-job', 'deploymentId': 'original-deployment', 'state': 'running'}
        self.store = SimpleNamespace(get=lambda _: copy.deepcopy(self.job),
            deployment=lambda _: {'helperCapabilities': {'gestureVersion': 1}})
        self.worker = SimpleNamespace(store=self.store, job=self.job, stop_requested=False, output=lambda _: None)
        self.message = {'requestId': 'original-gesture', 'input': {'kind': 'gesture', 'steps': plan()}}
        self.request = {'inputKind': 'gesture', 'generation': '12', 'frameBindingVersion': 1}
        self.before = {'windowWidth': 40, 'windowHeight': 30}
        self.active = {'state': 'running', 'gestureId': 'original-gesture', 'gestureActive': True,
            'gestureAccepted': 1, 'gestureReleaseQueued': False, 'gestureTimesMilliseconds': [0]}
        self.ended = {**self.active, 'gestureActive': False, 'gestureAccepted': 3,
            'gestureReleaseQueued': True, 'gestureTimesMilliseconds': [0, 304, 608]}
        self.guard = patch('vm_worker.guard'); self.guard.start(); self.addCleanup(self.guard.stop)

    async def run_gesture(self, control, auth=None):
        return await execute(self.worker, self.message, dict(self.request), self.before, control, None,
                             {'instanceId': 7, 'generation': '12'}, auth)

    async def test_one_plan_and_actual_prefix_timing_receipt(self):
        control = SimpleNamespace(call=AsyncMock(side_effect=[self.active, self.ended]))
        _, result = await self.run_gesture(control)
        self.assertTrue(result['complete']); self.assertFalse(result['consumptionConfirmed'])
        self.assertEqual(result['queuedAtMilliseconds'], [0, 304, 608])
        self.assertEqual([call.args[0] for call in control.call.await_args_list], ['input', 'poll'])

    async def test_stop_and_partial_acceptance_release_without_replay(self):
        self.worker.stop_requested = True
        stopped = {**self.active, 'gestureActive': False, 'gestureReleaseQueued': True, 'gestureAborted': 'cancelled'}
        control = SimpleNamespace(call=AsyncMock(side_effect=[self.active, stopped]))
        _, result = await self.run_gesture(control)
        self.assertFalse(result['complete']); self.assertEqual(result['accepted'], 1)
        self.assertTrue(result['releaseQueued'])
        self.assertEqual([call.args[0] for call in control.call.await_args_list], ['input', 'cancel_gesture'])

    async def test_lost_ack_and_unconfirmed_release_remain_unknown(self):
        for response in (UnconfirmedGuestEffect('lost'), {**self.active, 'gestureActive': False}):
            control = SimpleNamespace(call=AsyncMock(side_effect=[response]))
            with self.assertRaises(UnconfirmedGuestEffect): await self.run_gesture(control)
            self.assertEqual(control.call.await_count, 1)

    async def test_legacy_profile_or_helper_cannot_submit_gestures(self):
        control = SimpleNamespace(call=AsyncMock())
        with self.assertRaises(DevelopmentFault): await self.run_gesture(control, {'engine': {'profile': 'studio-tools-v13'}})
        self.store.deployment = lambda _: {'helperCapabilities': {}}
        with self.assertRaises(DevelopmentFault): await self.run_gesture(control)
        control.call.assert_not_awaited()

    async def test_intermediate_capture_is_optional_and_does_not_resubmit(self):
        self.message['input']['observeAfterStep'] = 1
        control = SimpleNamespace(call=AsyncMock(side_effect=[self.active, self.ended]))
        capture = AsyncMock(return_value={'metadata': {'id': 'own-frame'}})
        with patch('observation.capture', capture): _, result = await self.run_gesture(control)
        self.assertEqual(result['observationId'], 'own-frame'); capture.assert_awaited_once()
        self.assertEqual([call.args[0] for call in control.call.await_args_list], ['input', 'poll'])
