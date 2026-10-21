import asyncio
import fcntl
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from agent_snapshot import AgentSnapshots, delegated
from contracts import DevelopmentFault
import test_jobs
sys.path.append(str(Path(__file__).resolve().parents[1] / 'agent-sessions'))


class DelegationTest(unittest.IsolatedAsyncioTestCase):
    async def test_agent_owner_captures_under_its_existing_lease_without_live_terminals(self):
        fixture = test_jobs.JobsTest(); fixture.setUp()
        worker_db = sqlite3.connect(':memory:'); worker_db.row_factory = sqlite3.Row
        worker_db.execute('CREATE TABLE runs(id TEXT, busy INTEGER, state TEXT)')
        run_id, session_id = str(uuid.uuid4()), str(uuid.uuid4())
        worker_db.execute('INSERT INTO runs VALUES(?,1,?)', (run_id, 'running'))
        job, _ = fixture.store.admit('build', fixture.input(), {'sessionId': session_id, 'agentRunId': run_id})
        fake = SimpleNamespace(manifest={'projects': str(fixture.root), 'r4os': str(fixture.root / 'R4OS'), 'projectId': fixture.id},
            run_id=run_id, session_id=session_id, stopping=False, store=SimpleNamespace(db=worker_db),
            terminals=SimpleNamespace(lock=asyncio.Lock(), processes={'active': SimpleNamespace(finished=asyncio.Event())}),
            sandbox=SimpleNamespace(lock=asyncio.Lock()))
        server = AgentSnapshots(fake); lease = (fixture.root / 'lease').open('a')
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with patch('agent_snapshot.socket_path', return_value=fixture.root / 'snapshot.sock'):
                await server.start()
                with self.assertRaises(DevelopmentFault): await delegated(fixture.store, job)
                fake.terminals.processes.clear()
                source, directory = await delegated(fixture.store, job)
                self.assertEqual(source['id'], job['id'])
                self.assertEqual((directory / 'main.zig').read_text(), 'uncommitted source')
                with (fixture.root / 'lease').open('a') as other:
                    with self.assertRaises(BlockingIOError): fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                await server.close()
        finally:
            lease.close(); worker_db.close(); fixture.tearDown()


if __name__ == '__main__': unittest.main()
