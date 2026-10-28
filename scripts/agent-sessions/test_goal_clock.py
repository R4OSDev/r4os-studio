"""Deterministic per-Play monotone time and lifetime maxima, no inference."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import uuid
import test_runs as fixtures
from goal_clock import GoalClock,snapshot,lost
from stats_store import Source,Statistics,read,scope

class GoalClockTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.Runs.setUp
    tearDown=fixtures.Runs.tearDown
    open=fixtures.Runs.open
    async def test_live_prefix_is_excluded_pause_and_new_play_are_separate(self):
        tick=[100000000000];rid=str(uuid.uuid4())
        with self.open() as store:
            w=SimpleNamespace(store=store,run_id=str(uuid.uuid4()),session_id=self.sid)
            clock=GoalClock(w,lambda:tick[0]);tick[0]+=30000000000
            self.assertIsNone(snapshot(store,self.sid))
            clock.start(rid);tick[0]+=7000000000;clock.checkpoint()
            # Pausing current turn still belongs to this execution.
            tick[0]+=2000000000
            with patch('goal_clock.now',return_value='1999-01-01T00:00:00Z'):clock.end()
            self.assertEqual(snapshot(store,self.sid)['durationMs'],9000)
            tick[0]+=60000000000;clock.start(str(uuid.uuid4()));tick[0]+=3000000000;clock.end()
            self.assertEqual(snapshot(store,self.sid)['durationMs'],3000)
            self.assertEqual(read(self.projects)['longestGoalMs'],9000)
            owner={'type':'project','id':self.pid}
            self.assertEqual(read(self.projects,'project:'+scope(owner))['longestGoalMs'],9000)
            self.assertNotIn('longestGoalMs',read(self.projects,'session:'+scope(owner,self.sid)))
            await clock.close()
    async def test_lost_worker_freezes_checkpoint_and_stale_read_never_extends_record(self):
        tick=[100000000000]
        with self.open() as store:
            run=str(uuid.uuid4());w=SimpleNamespace(store=store,run_id=run,session_id=self.sid)
            clock=GoalClock(w,lambda:tick[0]);clock.start(str(uuid.uuid4()));tick[0]+=4000000000;clock.checkpoint()
            tick[0]+=20000000000
            state=snapshot(store,self.sid,lambda:tick[0]);self.assertEqual(state['state'],'unknown');self.assertEqual(state['durationMs'],4000)
            lost(store,run);self.assertEqual(snapshot(store,self.sid)['durationMs'],4000)
            self.assertEqual(snapshot(store,self.sid)['state'],'unknown');clock.state='unknown';await clock.close()
    async def test_concurrent_maxima_and_duplicate_old_updates_are_atomic(self):
        with self.open() as store:
            source=Source(store)
            receipts=[source.put(self.sid,'goal',{'play':str(n)},{'durationMs':n*1000,'uncertain':False}) for n in (4,9,3)]
            source.flush()
        def update(value):
            db=Statistics(self.projects,True)
            try:db.apply(value)
            finally:db.close()
        with ThreadPoolExecutor(3) as pool:list(pool.map(update,receipts*3))
        self.assertEqual(read(self.projects)['longestGoalMs'],9000)
    async def test_statistics_fault_does_not_propagate_to_execution(self):
        with self.open() as store:
            clock=GoalClock(SimpleNamespace(store=store,run_id=str(uuid.uuid4()),session_id=self.sid))
            with patch('goal_clock.Source.put',side_effect=OSError('owned unavailable aggregate')):
                clock.start(str(uuid.uuid4()));clock.checkpoint();clock.end()
            self.assertTrue(clock.failed);self.assertEqual(snapshot(store,self.sid)['state'],'ended');await clock.close()
