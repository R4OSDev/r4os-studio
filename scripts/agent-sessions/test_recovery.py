import asyncio
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch
import uuid
import test_runs
from host import Host, UNIT
from profile import write_json
from run_store import admit, get_run, transition, item
from session_store import encode
from store import ProjectFault
from worker import Worker


class Recovery(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture = test_runs.Runs(); self.fixture.setUp(); f = self.fixture
        self.config = {'projects': str(f.projects), 'r4os': str(f.r4os), 'providers': str(f.providers), 'uid': 1000}
        self.host = Host(self.config)

    def tearDown(self): self.fixture.tearDown()

    def admit(self):
        f = self.fixture
        with f.open() as s:
            run, _ = admit(s, f.sid, {**f.data, 'requestId': str(uuid.uuid4())}, f.providers)
        return run['id']

    def meta(self, rid):
        f = self.fixture
        value = {'schema': 1, **self.config, 'runId': rid, 'projectId': f.pid, 'sessionId': f.sid, 'providerId': f.provider}
        parent = self.host.root / rid; parent.mkdir(); write_json(parent / 'worker.json', value)

    async def test_boot_does_not_start_queued_work_and_live_units_reattach(self):
        rid = self.admit(); f = self.fixture
        control = AsyncMock(return_value='')
        with patch('host.systemctl', control): await self.host.recover()
        with f.open() as s: self.assertEqual(get_run(s, rid)['state'], 'unknown')
        self.assertFalse(any(c.args[0] in ('start', 'stop') for c in control.call_args_list))
        rid = self.admit(); self.meta(rid)
        async def alive(*args): return 'active' if args[0] == 'show' else UNIT.format(rid) + ' loaded active running Agent run'
        with patch('host.systemctl', side_effect=alive): await self.host.recover()
        self.assertIn(rid, self.host.active)
        with f.open() as s:
            self.assertEqual(get_run(s, rid)['busy'], 1)
            item(s, f.sid, rid, {'id': 'unconfirmed', 'runId': rid, 'type': 'tool', 'status': 'pending'})
            s.db.execute('INSERT INTO tools VALUES (?,?,?,?,?,?,NULL)', (rid, 'unconfirmed', 'studio_write_file', 'hash', 'intent', '{}')); s.db.commit()
        file = f.projects / f.pid / 'Workspace/effect.txt'; file.write_text('effect before receipt')
        with patch('host.systemctl', AsyncMock(return_value='')): await self.host.refresh()
        with f.open() as s:
            self.assertEqual(get_run(s, rid)['state'], 'unknown')
            self.assertEqual(s.db.execute('SELECT state FROM tools').fetchone()[0], 'unknown')
            self.assertEqual(json.loads(s.db.execute("SELECT payload FROM items WHERE item_id='unconfirmed'").fetchone()[0])['status'], 'unknown')
        self.assertEqual(file.read_text(), 'effect before receipt')

    async def test_lost_service_query_and_unbound_units_fail_closed(self):
        rid = self.admit(); self.meta(rid)
        value = self.host.metadata(self.host.root / rid / 'worker.json'); self.host.active[rid] = value
        with patch('host.systemctl', AsyncMock(side_effect=ProjectFault('Unavailable', 503))):
            with self.assertRaises(ProjectFault): await self.host.refresh()
        with self.fixture.open() as s: self.assertEqual(get_run(s, rid)['busy'], 1)
        self.host.active.clear()
        with patch('host.systemctl', AsyncMock(return_value=UNIT.format(rid) + ' loaded active running Agent run')):
            await self.host.check_unbound()
            self.assertIn(rid, self.host.unbound)

    async def test_lost_start_reply_uses_native_events_and_never_submits_twice(self):
        f = self.fixture
        for mode in ('completed-without-started', 'started-then-completed', 'unconfirmed'):
            rid = self.admit(); calls = []
            worker = Worker({**self.config, 'projectId': f.pid, 'runId': rid, 'release': 'fixture', 'version': '0.3.17'})
            worker.config['engine'] = {'version': '0.163.0'}
            class Native:
                def __init__(self, args, notify, tool): self.notify = notify
                async def start(self): pass
                async def close(self): pass
                async def request(self, method, params, **kwargs):
                    calls.append(method)
                    if method.startswith('thread/'): return {'thread': {'id': 'native-thread'}}
                    if method == 'turn/start':
                        complete = {'threadId': 'native-thread', 'turn': {'id': 'native-turn', 'status': 'completed'}}
                        if mode == 'completed-without-started': await self.notify('turn/completed', complete)
                        if mode == 'started-then-completed':
                            await self.notify('turn/started', {'threadId': 'native-thread', 'turn': {'id': 'native-turn'}})
                            asyncio.get_running_loop().call_later(.01, lambda: asyncio.create_task(self.notify('turn/completed', complete)))
                        raise asyncio.TimeoutError('The RPC response was lost')
                    return {}
            with patch('worker.prepare', return_value=([], {})), patch('worker.CodexRPC', Native): await worker.run()
            self.assertEqual(calls.count('turn/start'), 1)
            with f.open() as store:
                row = get_run(store, rid)
                self.assertEqual(row['state'], 'unknown' if mode == 'unconfirmed' else 'completed')
                self.assertEqual(row['busy'], 0)
                if mode != 'unconfirmed': self.assertIsNone(row['error']); self.assertEqual(row['turn_id'], 'native-turn')

    async def test_unconfirmed_native_call_is_not_replayed_in_another_run(self):
        rid = self.admit(); f = self.fixture
        args = {'path': 'receipt.txt', 'content': 'one', 'expectedSha256': None}
        hashed = hashlib.sha256(encode({'tool': 'studio_write_file', 'arguments': args}).encode()).hexdigest()
        with f.open() as s:
            s.db.execute('INSERT INTO tools VALUES (?,?,?,?,?,?,NULL)', (rid, 'same-call', 'studio_write_file', hashed, 'unknown', encode(args))); s.db.commit()
            transition(s, rid, 'unknown')
        second = self.admit(); w = Worker({**self.config, 'projectId': f.pid, 'runId': second})
        w.thread_id = 'thread'; w.turn_id = 'turn'; w.execute = AsyncMock()
        try:
            result = await w.tool({'namespace': None, 'threadId': 'thread', 'turnId': 'turn', 'tool': 'studio_write_file', 'callId': 'same-call', 'arguments': args})
            self.assertIn('unknown', result['contentItems'][0]['text']); w.execute.assert_not_called()
        finally: w.store.close()


if __name__ == '__main__': unittest.main()
