"""Actual clock/source writes, read-only summing, live binding and partial restore."""
from contextlib import closing
import json
import os
from types import SimpleNamespace
import unittest
import uuid

import test_runs as fixtures
from goal_clock import GoalClock, snapshot as current_clock
from goal_total import snapshot, mark_new
from goal_store import Goals
from stats_store import Statistics, Source, read, hashed
from session_store import SessionStore, encode
from attachment_store import birth
from skill_application import packages
from profile import SKILL_PROFILE


class GoalTotalTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.Runs.setUp
    tearDown=fixtures.Runs.tearDown
    open=fixtures.Runs.open

    async def play(self,store,tick,ms,*,ended=True,live_activation=False):
        sid=self.sid if store.owner_type=='project' else self.skill_sid
        run=str(uuid.uuid4());eid=str(uuid.uuid4());Goals(store).schema()
        config={} if live_activation else {'goalExecution':{'requestId':eid}}
        worker={'pid':os.getpid(),'birth':birth(os.getpid()),'release':'fixture'}
        with store.db:
            store.db.execute("INSERT INTO runs VALUES (?,?,?,'hash','running',1,?,NULL,?,NULL,'now',NULL)",(run,sid,str(uuid.uuid4()),encode(config),encode(worker)))
            store.db.execute("INSERT INTO goal_commands VALUES (?,?,'hash',?,'confirmed','native_activation','{}','now')",(eid,sid,encode({'action':'play'})))
        w=SimpleNamespace(store=store,run_id=run,session_id=sid)
        clock=GoalClock(w,lambda:tick[0]);clock.start(eid);tick[0]+=ms*1_000_000;clock.checkpoint()
        if ended:
            clock.end();await clock.close()
            with store.db:store.db.execute("UPDATE runs SET state='completed',busy=0,completed_at='now' WHERE id=?",(run,))
        return clock,eid,run

    async def test_two_plays_pause_goal_change_repeat_reads_and_maxima_are_independent(self):
        tick=[100_000_000_000]
        with self.open() as store:
            await self.play(store,tick,60000);tick[0]+=3_600_000_000_000
            await self.play(store,tick,30000)
            before=store.db.total_changes
            for _ in range(3):
                total=snapshot(store,self.sid,lambda:tick[0])
                self.assertEqual(total['durationMs'],'90000');self.assertEqual(total['coverage']['state'],'complete')
                self.assertEqual(total['coverage']['measuredExecutions'],2)
            self.assertEqual(store.db.total_changes,before)
            self.assertEqual(current_clock(store,self.sid)['durationMs'],30000)
            self.assertEqual(read(self.projects)['longestGoalMs'],60000)
            from host import Host
            host=Host({'projects':str(self.projects),'r4os':str(self.r4os),'providers':str(self.providers)})
            api=await host.handle({'operation':'statistics','scope':'session','projectId':self.pid,'sessionId':self.sid})
            self.assertEqual(api['totalGoalRuntime']['durationMs'],'90000')
            global_value=await host.handle({'operation':'statistics','scope':'global'})
            self.assertNotIn('totalGoalRuntime',global_value);self.assertEqual(global_value['longestGoalMs'],60000)

    async def test_live_normal_run_prefix_is_excluded_and_stale_birth_loss_freezes(self):
        tick=[100_000_000_000]
        with self.open() as store:
            await self.play(store,tick,60000)
            tick[0]+=99_000_000_000  # Ordinary run prefix before actual activation.
            clock,_,run=await self.play(store,tick,30000,ended=False,live_activation=True)
            try:
                tick[0]+=2_000_000_000;total=snapshot(store,self.sid,lambda:tick[0])
                self.assertEqual(total['durationMs'],'90000');self.assertEqual(total['live']['ageMs'],2000)
                self.assertEqual(total['state'],'running')
                tick[0]+=10_000_000_000;stale=snapshot(store,self.sid,lambda:tick[0])
                self.assertIsNone(stale['live']);self.assertEqual(stale['durationMs'],'90000');self.assertEqual(stale['coverage']['state'],'partial')
                tick[0]-=10_000_000_000
                with store.db:store.db.execute("UPDATE runs SET worker='{}' WHERE id=?",(run,))
                lost=snapshot(store,self.sid,lambda:tick[0]);self.assertIsNone(lost['live']);self.assertEqual(lost['durationMs'],'90000')
            finally:clock.end(unknown=True);await clock.close()

    async def test_source_global_outbox_replay_restore_and_missing_original_counter(self):
        tick=[100_000_000_000]
        with self.open() as store:
            _,eid,_=await self.play(store,tick,30000)
            value=json.loads(store.db.execute("SELECT payload FROM statistic_receipts WHERE json_extract(payload,'$.kind')='goal'").fetchone()[0])
            target=Statistics(self.projects,True)
            try:
                target.apply(value);target.apply(value)
            finally:target.close()
            pending=self.projects/'.studio/statistics/Pending';pending.mkdir(parents=True,exist_ok=True)
            (pending/(value['key']+'.json')).write_text(encode(value))
            self.assertEqual(snapshot(store,self.sid,lambda:tick[0])['durationMs'],'30000')
            with store.db:store.db.execute('DELETE FROM goal_clocks WHERE execution_id=?',(eid,))
            restored=snapshot(store,self.sid,lambda:tick[0]);self.assertEqual(restored['durationMs'],'30000');self.assertEqual(restored['coverage']['state'],'partial')
            second=str(uuid.uuid4())
            with store.db:store.db.execute("INSERT INTO goal_commands VALUES (?,?,'hash','{\"action\":\"play\"}','confirmed','native_activation','{}','now')",(second,self.sid))
            incomplete=snapshot(store,self.sid,lambda:tick[0]);self.assertEqual(incomplete['coverage']['missingExecutions'],1)
            self.assertEqual(incomplete['durationMs'],'30000')

    async def test_zero_legacy_unknown_foreign_session_and_skill_owner(self):
        with self.open() as store:
            self.assertEqual(snapshot(store,self.sid)['durationMs'],'0')
            with store.db:store.db.execute("UPDATE sessions SET thread_id='own-legacy-thread' WHERE id=?",(self.sid,))
            self.assertIsNone(snapshot(store,self.sid)['durationMs'])
            with store.db:mark_new(store,self.sid)
            self.assertEqual(snapshot(store,self.sid)['durationMs'],'0')
            other=str(uuid.uuid4());row=store.row(self.sid)
            with store.db:store.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,'foreign-legacy-thread',1,'now','now')",(other,self.pid,'Other',row['settings'],row['engine']))
            before=snapshot(store,other)
            self.assertIsNone(before['durationMs'])
            await self.play(store,[100_000_000_000],90061000)
            after=snapshot(store,other)
            self.assertEqual({k:v for k,v in after.items() if k!='referenceAt'},{k:v for k,v in before.items() if k!='referenceAt'})
        skill=str(uuid.uuid4());self.skill_sid=str(uuid.uuid4())
        with closing(packages.connect(self.root/'Skills')) as db:packages.create(db,self.root/'Skills',{'id':skill,'name':'Own clock skill'})
        with closing(SessionStore(self.projects,self.r4os,skill,'skill')) as store:
            with store.db:store.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,NULL,1,'now','now')",(self.skill_sid,skill,'Own',encode(self.settings),encode({'profile':SKILL_PROFILE})))
            tick=[100_000_000_000];await self.play(store,tick,60000);await self.play(store,tick,30000)
            self.assertEqual(snapshot(store,self.skill_sid,lambda:tick[0])['durationMs'],'90000')

    async def test_receipt_keys_are_bound_and_native_usage_is_never_time_reconstruction(self):
        tick=[100_000_000_000]
        with self.open() as store:
            await self.play(store,tick,30000)
            Source(store).put(self.sid,'goal',{'unqualified':'different key'},{'durationMs':999999,'uncertain':False})
            total=snapshot(store,self.sid,lambda:tick[0]);self.assertEqual(total['durationMs'],'30000')
            self.assertIn('unmatched_time_receipt',total['coverage']['reasons'])
            with store.db:store.db.execute("INSERT INTO session_goals VALUES (?,1,?,NULL,'idle',NULL,NULL,NULL)",(self.sid,encode({'status':'paused','timeUsedSeconds':999999})))
            self.assertEqual(snapshot(store,self.sid,lambda:tick[0])['durationMs'],'30000')

    async def test_submillisecond_segments_are_added_before_rounding(self):
        tick=[100_000_000_000]
        with self.open() as store:
            _,first,_=await self.play(store,tick,0);_,second,_=await self.play(store,tick,0)
            with store.db:
                store.db.execute('UPDATE goal_clocks SET elapsed_ns=999999999 WHERE execution_id=?',(first,))
                store.db.execute('UPDATE goal_clocks SET elapsed_ns=1 WHERE execution_id=?',(second,))
            self.assertEqual(snapshot(store,self.sid,lambda:tick[0])['durationMs'],'1000')
