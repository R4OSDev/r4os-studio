"""Monotone per-Play duration; observation and storage cannot control a Goal."""
import asyncio
import json
import os
from pathlib import Path
import time
from attachment_store import birth
from session_store import now
from stats_store import Source

FRESH_MS=6000

def boot():return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
def exists(store):return store.db.execute("SELECT 1 FROM sqlite_master WHERE name='goal_clocks'").fetchone() is not None

def snapshot(store,sid,monotonic=time.monotonic_ns):
    store.row(sid)
    if not exists(store):return None
    row=store.db.execute('SELECT * FROM goal_clocks WHERE session_id=? ORDER BY rowid DESC LIMIT 1',(sid,)).fetchone()
    if not row:return None
    state=row['state'];age=0
    if state=='running':
        try:
            age=max(0,(monotonic()-row['last_ns'])//1000000)
            if row['boot_id']!=boot() or row['birth']!=birth(row['pid']) or age>FRESH_MS:state='unknown'
        except (OSError,ValueError,TypeError):state='unknown'
    return {'executionId':row['execution_id'],'durationMs':row['elapsed_ns']//1000000,'state':state,
        'sampledAt':row['checkpoint_at'],'referenceAt':now(),'ageMs':age,'staleAfterMs':FRESH_MS}

def lost(store,run_id):
    if not exists(store):return
    with store.db:store.db.execute("UPDATE goal_clocks SET state='unknown' WHERE run_id=? AND state='running'",(run_id,))
    for row in store.db.execute("SELECT * FROM goal_clocks WHERE run_id=? AND state='unknown'",(run_id,)):
        Source(store).put(row['session_id'],'goal',{'owner':{'type':store.owner_type,'id':store.owner_id},'session':row['session_id'],'play':row['execution_id']},{'durationMs':row['elapsed_ns']//1000000,'uncertain':True})

class GoalClock:
    def __init__(self,worker,monotonic=time.monotonic_ns):
        self.w=worker;self.monotonic=monotonic;self.execution=None;self.elapsed=0;self.last=None;self.state=None;self.task=None
        self.failed=False
    def start(self,rid):
        if self.execution==rid:return
        try:
            if self.state=='running':self.end()
            self.execution=rid;self.elapsed=0;self.last=self.monotonic();self.state='running'
            with self.w.store.db:
                self.w.store.db.execute('''CREATE TABLE IF NOT EXISTS goal_clocks(execution_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,session_id TEXT NOT NULL,boot_id TEXT NOT NULL,pid INTEGER NOT NULL,birth TEXT NOT NULL,
                    elapsed_ns INTEGER NOT NULL,last_ns INTEGER NOT NULL,state TEXT NOT NULL,checkpoint_at TEXT NOT NULL)''')
                previous=self.w.store.db.execute('SELECT 1 FROM goal_clocks WHERE execution_id=?',(rid,)).fetchone()
                if previous:raise ValueError('A Play execution cannot start twice')
                self.w.store.db.execute('INSERT INTO goal_clocks VALUES (?,?,?,?,?,?,?,?,?,?)',(rid,self.w.run_id,self.w.session_id,boot(),os.getpid(),birth(os.getpid()),0,self.last,'running',now()))
            self.checkpoint()
            if not self.task or self.task.done():self.task=asyncio.create_task(self.tick())
        except Exception:self.failed=True
    def resume(self,rid):
        """Observe an admitted continuation of this same Play; exclude its wait."""
        try:
            if self.execution==rid and self.state=='running':return
            if self.failed or self.execution!=rid or self.state!='ended':
                raise ValueError('The original Play clock cannot be resumed')
            current=self.monotonic()
            with self.w.store.db:
                changed=self.w.store.db.execute('''UPDATE goal_clocks SET state='running',last_ns=?,checkpoint_at=?
                    WHERE execution_id=? AND run_id=? AND session_id=? AND state='ended'
                      AND elapsed_ns=? AND pid=? AND birth=? AND boot_id=?''',
                    (current,now(),rid,self.w.run_id,self.w.session_id,self.elapsed,
                     os.getpid(),birth(os.getpid()),boot())).rowcount
                if changed!=1:raise ValueError('The original Play clock binding changed')
            self.last=current;self.state='running';self.checkpoint()
            if not self.task or self.task.done():self.task=asyncio.create_task(self.tick())
        except Exception:
            # Timing failure is missing coverage, never execution permission or
            # an execution failure. Preserve the last confirmed elapsed value.
            self.mark_unknown(rid)
    def mark_unknown(self,rid):
        """Keep the known prefix when a continuation may have started unseen."""
        self.failed=True
        if self.execution!=rid:return
        self.state='unknown'
        try:
            with self.w.store.db:
                changed=self.w.store.db.execute('''UPDATE goal_clocks SET state='unknown'
                    WHERE execution_id=? AND run_id=? AND session_id=? AND pid=? AND birth=? AND boot_id=?''',
                    (rid,self.w.run_id,self.w.session_id,os.getpid(),birth(os.getpid()),boot())).rowcount
            if changed:
                Source(self.w.store).put(self.w.session_id,'goal',
                    {'owner':{'type':self.w.store.owner_type,'id':self.w.store.owner_id},'session':self.w.session_id,'play':rid},
                    {'durationMs':self.elapsed//1000000,'uncertain':True})
        except Exception:pass
    def checkpoint(self):
        if self.execution is None:return
        try:
            current=self.monotonic()
            if self.state=='running':self.elapsed+=max(0,current-self.last)
            self.last=current
            with self.w.store.db:self.w.store.db.execute('UPDATE goal_clocks SET elapsed_ns=?,last_ns=?,state=?,checkpoint_at=? WHERE execution_id=?',(self.elapsed,self.last,self.state,now(),self.execution))
            source=Source(self.w.store)
            source.put(self.w.session_id,'goal',{'owner':{'type':self.w.store.owner_type,'id':self.w.store.owner_id},'session':self.w.session_id,'play':self.execution},{'durationMs':self.elapsed//1000000,'uncertain':self.state=='unknown'})
            source.flush(16)
        except Exception:self.failed=True
    def end(self,unknown=False):
        if self.state!='running':return
        # Unknown closure retains only a previous confirmed checkpoint.
        if not unknown:self.checkpoint()
        self.state='unknown' if unknown else 'ended';self.checkpoint()
    async def tick(self):
        try:
            while self.state=='running':await asyncio.sleep(2);self.checkpoint()
        except asyncio.CancelledError:pass
    async def close(self):
        if self.task:self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
