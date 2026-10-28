"""Advance an actual worker's clock by days without model or guest inference."""
import asyncio
import fcntl
from unittest.mock import AsyncMock, patch
import unittest

import test_goal_control as controls
from owner import open_lock
from run_store import admit, get_run, transition
from worker import Worker


class LongRuns(unittest.IsolatedAsyncioTestCase):
    setUp = controls.GoalControlTests.setUp
    tearDown = controls.GoalControlTests.tearDown
    open = controls.GoalControlTests.open
    command = controls.GoalControlTests.command
    goal_worker = controls.GoalControlTests.goal_worker

    async def scenario(self, goal=False, stop=False):
        if goal:
            worker, native = await self.goal_worker()
        else:
            with self.open() as store: run, _ = admit(store, self.sid, self.data, self.providers)
            worker = Worker({'projects': str(self.projects), 'r4os': str(self.r4os), 'providers': str(self.providers),
                'projectId': self.pid, 'runId': run['id'], 'release': 'fixture', 'version': 'fixture'})
            native = controls.Native()
        worker.manifest.update(providers=str(self.providers), version='fixture')
        worker.build_snapshots.start = AsyncMock(); worker.build_snapshots.close = AsyncMock()
        original = native.request; activated = asyncio.Event()

        async def request(method, params, **kwargs):
            if method == 'thread/resume': return {}
            if method == 'turn/start':
                await worker.notify('turn/started', {'threadId': native.thread, 'turn': {'id': 'first'}})
                activated.set(); return {'turn': {'id': 'first'}}
            value = await original(method, params, **kwargs)
            if method == 'thread/goal/set' and params.get('status') == 'active':
                await worker.notify('turn/started', {'threadId': native.thread, 'turn': {'id': 'first'}})
                activated.set()
            return value

        loop = asyncio.get_running_loop(); clock = [loop.time()]
        with patch('worker.prepare', return_value=([], {})), patch('worker.CodexRPC', native.factory), \
                patch.object(native, 'request', side_effect=request), patch.object(loop, 'slow_callback_duration', float('inf')), \
                patch.object(loop, 'time', side_effect=lambda: clock[0]):
            task = asyncio.create_task(worker.run())
            try:
                for _ in range(50):
                    await asyncio.sleep(0)
                    if activated.is_set(): break
                self.assertTrue(activated.is_set())
                for _ in range(5): await asyncio.sleep(0)
                clock[0] += 7 * 24 * 3600
                for _ in range(25): await asyncio.sleep(0)
                self.assertFalse(task.done(), 'A healthy run ended merely because seven days elapsed.')
                self.assertFalse(worker.stopping)
                with open_lock(self.projects, 'project', self.pid) as lease:
                    with self.assertRaises(BlockingIOError): fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if stop:
                    with self.open() as store: transition(store, worker.run_id, 'stopping')
                    await worker.stop()
                else:
                    await worker.notify('turn/completed', {'threadId': native.thread, 'turn': {'id': 'first', 'status': 'completed'}})
                    if goal:
                        await worker.notify('turn/started', {'threadId': native.thread, 'turn': {'id': 'second'}})
                        await worker.notify('turn/completed', {'threadId': native.thread, 'turn': {'id': 'second', 'status': 'completed'}})
                        native.goal['status'] = 'complete'
                        await worker.notify('thread/goal/updated', {'threadId': native.thread, 'goal': native.goal.copy()})
                for _ in range(50):
                    clock[0] += .1
                    await asyncio.sleep(0)
                    if task.done(): break
            finally:
                if not task.done(): await worker.stop()
        await asyncio.wait_for(task, 2)
        with self.open() as store:
            run = get_run(store, worker.run_id)
            self.assertEqual(run['state'], 'interrupted' if stop else 'completed')
            self.assertIsNone(run['error']); self.assertEqual(store.db.execute('SELECT count(*) FROM runs').fetchone()[0], 1)
            if goal:
                from goal_store import Goals
                self.assertEqual(Goals(store).snapshot(self.sid)['goal']['status'], 'paused' if stop else 'complete')
        self.assertFalse(any('tokenBudget' in params for _, params in native.calls))

    async def test_single_turn_survives_seven_days_then_completes(self):
        await self.scenario()

    async def test_goal_retains_lease_across_seven_days_and_native_turns(self):
        await self.scenario(goal=True)

    async def test_user_stop_still_interrupts_a_goal_after_seven_days(self):
        await self.scenario(goal=True, stop=True)

    async def test_startup_rpc_timeout_is_not_reported_as_a_session_time_limit(self):
        with self.open() as store: run, _ = admit(store, self.sid, self.data, self.providers)
        worker = Worker({'projects': str(self.projects), 'r4os': str(self.r4os), 'providers': str(self.providers),
            'projectId': self.pid, 'runId': run['id'], 'release': 'fixture', 'version': 'fixture'})
        worker.build_snapshots.start = AsyncMock(); worker.build_snapshots.close = AsyncMock()
        native = controls.Native(); native.request = AsyncMock(side_effect=asyncio.TimeoutError())
        with patch('worker.prepare', return_value=([], {})), patch('worker.CodexRPC', native.factory): await worker.run()
        with self.open() as store:
            result = get_run(store, run['id'])
            self.assertEqual(result['state'], 'failed')
            self.assertNotIn('host time limit', result['error'])
