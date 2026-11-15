"""Exercise the coordinator's Goal rotation through admission and control."""
import asyncio
from collections import OrderedDict
import json
from pathlib import PurePosixPath
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import uuid

import goal_keepalive as control
import goal_keepalive_host as scheduler
from goal_store import Goals
from run_store import admit, get_run, transition
from session_store import SessionStore, encode
import test_runs


def key(kind='project'):
    return kind, str(uuid.uuid4()), str(uuid.uuid4())


async def settle(host):
    await asyncio.gather(*tuple(host.goal_tasks.values()))
    await asyncio.sleep(0)


class WorkerReleasePath(PurePosixPath):
    def resolve(self, *, strict=False):
        return self

    def is_file(self):
        return self.name == 'goal_keepalive_run.py'


class GoalRotationTests(unittest.IsolatedAsyncioTestCase):
    def make_goal(self, *, inspect_images=False):
        fixture = test_runs.Runs()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.ready = ('project', fixture.pid, fixture.sid)
        self.launched = []
        self.host = SimpleNamespace(
            config={'providers': fixture.providers, 'workerReleaseRoot': '/opt/r4os-studio/releases/fixture'},
            lock=asyncio.Lock(),
            unbound=set(), active={}, max_active_runs=4, goal_tasks={},
            keepalives=OrderedDict.fromkeys((self.ready,)),
            image_capability_lock=asyncio.Lock(), active_unit=AsyncMock(return_value=False),
            store=self.open_fixture, launch_admitted=self.launch,
        )
        patcher = patch.object(scheduler, 'Path', WorkerReleasePath)
        patcher.start()
        self.addCleanup(patcher.stop)

        with fixture.open() as store:
            with store.db:
                settings = json.loads(store.row(fixture.sid)['settings'])
                settings['imageGenerationEnabled'] = inspect_images
                store.db.execute('UPDATE sessions SET settings=? WHERE id=?', (encode(settings), fixture.sid))
            predecessor, _ = admit(store, fixture.sid, fixture.data, fixture.providers)
            transition(store, predecessor['id'], 'running')
            transition(store, predecessor['id'], 'completed', worker={'runEndProtocol': 1, 'processEnd': {'confirmed': True}})
            self.command(store, 'save', objective='Continue the existing project Goal.')
            self.play = self.command(store, 'play', sessionRevision=1)
        self.predecessor = predecessor['id']

    def open_fixture(self, owner, kind):
        self.assertEqual((kind, owner), self.ready[:2])
        return SessionStore(self.fixture.projects, self.fixture.r4os, owner)

    def command(self, store, action, **fields):
        goals = Goals(store)
        revision = goals.snapshot(self.fixture.sid)['revision']
        return control.accept(goals, self.fixture.sid, {
            'requestId': str(uuid.uuid4()), 'revision': revision, 'action': action, **fields,
        })[0]

    async def launch(self, store, run, kind, owner, sid):
        self.assertEqual((kind, owner, sid), self.ready)
        self.launched.append(run['id'])
        transition(store, run['id'], 'running')
        self.host.active[run['id']] = {'ownerType': kind, 'ownerId': owner}

    async def check_goals(self):
        async with self.host.lock:
            scheduler.schedule(self.host)
            scheduler.schedule(self.host)
            self.assertLessEqual(len(self.host.goal_tasks), 2)
        await settle(self.host)

    async def test_third_goal_gets_one_continuation_while_two_workspaces_are_busy(self):
        self.make_goal()
        busy = (key(), key('skill'))
        self.host.keepalives = OrderedDict.fromkeys((*busy, self.ready))
        self.host.active = {session: {'ownerType': kind, 'ownerId': owner} for kind, owner, session in busy}
        self.host.max_active_runs = 2
        await self.check_goals()
        await self.check_goals()
        self.assertEqual(self.launched, [])
        self.host.max_active_runs = 3
        for _ in range(2):
            await self.check_goals()
        self.assertEqual(len(self.launched), 1)
        run_id = self.launched[0]
        with self.fixture.open() as store:
            run = get_run(store, run_id)
            execution = json.loads(run['config'])['goalKeepalive']
            self.assertEqual(execution['afterRunId'], self.predecessor)
            self.assertEqual(execution['playRequestId'], self.play['requestId'])
            self.assertEqual(execution['goal']['goalId'], self.play['snapshot']['goal']['goalId'])
            self.assertEqual(control.row(store, self.ready[2])['dispatch']['runId'], run_id)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 2)
        self.assertTrue(all(session in self.host.active for _, _, session in busy))

    async def test_one_free_slot_checks_the_next_goal_after_membership_changes(self):
        first, paused, waiting, added = key(), key(), key(), key('skill')
        host = SimpleNamespace(keepalives=OrderedDict.fromkeys((first, paused, waiting)), goal_tasks={})
        checked = []
        release_first = asyncio.Event()

        async def check(_host, *selected):
            checked.append(selected)
            if selected == first:
                await release_first.wait()

        with patch.object(scheduler, 'dispatch', check):
            scheduler.schedule(host)
            self.assertEqual(len(host.goal_tasks), 2)
            scheduler.schedule(host)
            await host.goal_tasks[(*paused, 'keepalive')]
            await asyncio.sleep(0)
            host.keepalives.pop(paused)
            host.keepalives[added] = None
            scheduler.schedule(host)
            self.assertEqual(len(host.goal_tasks), 2)
            await host.goal_tasks[(*waiting, 'keepalive')]
            await asyncio.sleep(0)
            scheduler.schedule(host)
            await host.goal_tasks[(*added, 'keepalive')]
            release_first.set()
            await settle(host)
        self.assertEqual(checked, [first, paused, waiting, added])

    async def test_pause_during_check_requires_the_new_play_before_admission(self):
        self.make_goal(inspect_images=True)
        inspecting = asyncio.Event()
        finish = asyncio.Event()

        async def inspect(*_):
            inspecting.set()
            await finish.wait()
            return None

        with patch('image_generation.inspect', inspect):
            scheduler.schedule(self.host)
            await asyncio.wait_for(inspecting.wait(), 5)
            with self.fixture.open() as store:
                self.command(store, 'pause')
                self.host.keepalives.pop(self.ready)
                newer = self.command(store, 'play', sessionRevision=1)
                self.host.keepalives[self.ready] = None
            finish.set()
            await settle(self.host)
            self.assertEqual(self.launched, [])
            await self.check_goals()
        self.assertEqual(len(self.launched), 1)
        with self.fixture.open() as store:
            execution = json.loads(get_run(store, self.launched[0])['config'])['goalKeepalive']
            self.assertEqual(execution['playRequestId'], newer['requestId'])
            self.assertEqual(execution['afterRunId'], self.predecessor)


if __name__ == '__main__':
    unittest.main()
