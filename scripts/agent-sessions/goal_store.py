"""Additive native Goal observations and idempotent, session-bound user intent."""
import hashlib
import json
from session_store import identity, encode, now
from store import ProjectFault
from goal_contract import native_goal, objective


def exists(store):
    return store.db.execute("SELECT 1 FROM sqlite_master WHERE name='goal_commands' AND type='table'").fetchone() is not None


def pending(store):
    return exists(store) and store.db.execute("SELECT 1 FROM goal_commands WHERE state='pending'").fetchone() is not None


class Goals:
    def __init__(self, store): self.store = store

    def schema(self):
        with self.store.db:
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS session_goals(
              session_id TEXT PRIMARY KEY REFERENCES sessions(id), revision INTEGER NOT NULL,
              native TEXT, last_intent TEXT, phase TEXT NOT NULL, request_id TEXT, run_id TEXT, reason TEXT)''')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS goal_commands(
              request_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
              fingerprint TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL,
              stage TEXT NOT NULL, response TEXT, created_at TEXT NOT NULL)''')
            self.store.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_goal_command ON goal_commands(state) WHERE state='pending'")

    def snapshot(self, sid):
        session = self.store.row(sid)
        row = self.store.db.execute('SELECT * FROM session_goals WHERE session_id=?', (sid,)).fetchone() if exists(self.store) else None
        result = {'owner': {'type': self.store.owner_type, 'id': self.store.owner_id}, 'sessionId': sid,
                  'threadId': session['thread_id'], 'revision': row['revision'] if row else 0,
                  'goal': json.loads(row['native']) if row and row['native'] else None,
                  'lastIntent': row['last_intent'] if row else None, 'phase': row['phase'] if row else 'idle'}
        if row:
            for key, public in (('request_id','requestId'), ('run_id','runId'), ('reason','reason')):
                if row[key] is not None: result[public] = row[key]
        if result['goal'] and result['goal']['threadId'] != session['thread_id']:
            raise ProjectFault('The saved Goal thread binding changed.', 409)
        return result

    def command(self, sid, rid):
        self.store.row(sid); identity(rid)
        row = self.store.db.execute('SELECT * FROM goal_commands WHERE request_id=? AND session_id=?', (rid, sid)).fetchone() if exists(self.store) else None
        if not row: raise ProjectFault('Goal command not found.', 404)
        return row

    def receipt(self, sid, rid):
        row = self.command(sid, rid)
        return json.loads(row['response']) if row['response'] else {'requestId': rid, 'action': json.loads(row['payload'])['action'],
                'state': row['state'], 'snapshot': self.snapshot(sid)}

    def accept(self, sid, data):
        if (not isinstance(data, dict) or not set(data) <= {'requestId','revision','action','objective','sessionRevision'}
                or not {'requestId','revision','action'} <= set(data) or type(data['revision']) is not int
                or ('sessionRevision' in data and (type(data['sessionRevision']) is not int or data['sessionRevision']<1))
                or data['action'] not in ('save','play','pause','stop')
                or (('objective' in data) != (data['action'] == 'save'))):
            raise ProjectFault('Invalid Goal command.', 400)
        key = identity(data['requestId']); self.store.row(sid)
        try:
            if data['action'] == 'save': objective(data['objective'], allow_empty=True)
        except ValueError as error: raise ProjectFault(str(error), 400) from None
        fingerprint = hashlib.sha256(encode({'sessionId': sid, **data}).encode()).hexdigest()
        self.schema(); self.store.db.execute('BEGIN IMMEDIATE')
        try:
            previous = self.store.db.execute('SELECT * FROM goal_commands WHERE request_id=?', (key,)).fetchone()
            if previous:
                if previous['fingerprint'] != fingerprint: raise ProjectFault('This request ID belongs to another Goal command.', 409)
                return self.receipt(sid, key), False
            snapshot = self.snapshot(sid)
            if snapshot['revision'] != data['revision']: raise ProjectFault('The Goal changed. Reload before changing it.', 409)
            if data['action']=='play' and data.get('sessionRevision')!=self.store.row(sid)['revision']:
                raise ProjectFault('Session settings changed. Reload before pressing Play.',409)
            if pending(self.store): raise ProjectFault('Reconcile the original pending Goal command first.', 409)
            if snapshot['phase'] == 'unknown' and data['action'] not in ('pause','stop'):
                raise ProjectFault('Pause the original unconfirmed Goal before changing it.', 409)
            if self.store.db.execute('SELECT COUNT(*) FROM goal_commands WHERE session_id=?', (sid,)).fetchone()[0] >= 4096:
                raise ProjectFault('This session reached its Goal command history limit.', 409)
            if data['action'] == 'play' and not snapshot['goal']: raise ProjectFault('Save a Goal before pressing Play.', 409)
            self.store.db.execute('INSERT INTO goal_commands VALUES (?,?,?,?,?,?,NULL,?)',
                (key, sid, fingerprint, encode({**data,'_previousPhase':snapshot['phase'],'_goal':snapshot['goal']}), 'pending', 'accepted', now()))
            self.store.db.execute('''INSERT INTO session_goals VALUES (?,1,NULL,NULL,'pending',?,NULL,NULL)
              ON CONFLICT(session_id) DO UPDATE SET revision=revision+1,phase='pending',request_id=excluded.request_id,reason=NULL''',
                (sid, key))
            self.store.db.commit(); return self.receipt(sid, key), True
        finally:
            if self.store.db.in_transaction: self.store.db.rollback()

    def stage(self, sid, rid, stage):
        with self.store.db:
            self.store.db.execute("UPDATE goal_commands SET stage=? WHERE request_id=? AND session_id=? AND state='pending'", (stage,rid,sid))

    def observe(self, sid, thread_id, value, run_id=None, phase=None):
        if self.store.row(sid)['thread_id'] != thread_id: raise ProjectFault('Goal thread binding changed.', 409)
        try: goal = native_goal(value, thread_id)
        except ValueError as error: raise ProjectFault(str(error), 503) from None
        self.schema()
        raw = encode(goal) if goal else None
        with self.store.db:
            current = self.store.db.execute('SELECT native,phase,run_id FROM session_goals WHERE session_id=?',(sid,)).fetchone()
            next_phase = phase or (current['phase'] if current else 'idle')
            next_run = run_id or (current['run_id'] if current else None)
            if current and current['native'] == raw and current['phase'] == next_phase and current['run_id'] == next_run: return self.snapshot(sid)
            previous=json.loads(current['native']) if current and current['native'] else None
            control=lambda g: None if g is None else {k:g.get(k) for k in ('threadId','objective','status','tokenBudget','createdAt')}
            changed=not current or control(previous)!=control(goal) or current['phase']!=next_phase or current['run_id']!=next_run
            self.store.db.execute('''INSERT INTO session_goals VALUES (?,1,?,NULL,?,NULL,?,NULL)
              ON CONFLICT(session_id) DO UPDATE SET native=excluded.native,revision=revision+?,
              phase=excluded.phase,run_id=excluded.run_id''', (sid,raw,next_phase,next_run,int(changed)))
            self.publish(sid)
        return self.snapshot(sid)

    def publish(self, sid):
        from run_store import event
        event(self.store, sid, None, 'goal', self.snapshot(sid), False)

    def finish(self, sid, rid, state='confirmed', reason=None, phase='idle'):
        row = self.command(sid,rid)
        if row['state'] != 'pending': return self.receipt(sid,rid)
        with self.store.db:
            payload=json.loads(row['payload'])
            final_phase='unknown' if state=='unknown' or (state=='failed' and payload.get('_previousPhase')=='unknown') else phase
            self.store.db.execute('UPDATE session_goals SET last_intent=CASE WHEN ? THEN ? ELSE last_intent END,phase=?,reason=?,revision=revision+1 WHERE session_id=?',
                (state=='confirmed',payload['action'], final_phase, reason, sid))
            result={'requestId':rid,'action':json.loads(row['payload'])['action'],'state':state,'snapshot':self.snapshot(sid)}
            if reason: result['reason']=reason
            self.store.db.execute('UPDATE goal_commands SET state=?,response=? WHERE request_id=?',(state,encode(result),rid))
            self.publish(sid)
        return result

    def recover(self):
        if not exists(self.store): return
        for row in self.store.db.execute("SELECT * FROM goal_commands WHERE state='pending'").fetchall():
            self.finish(row['session_id'],row['request_id'], 'failed' if row['stage']=='accepted' else 'unknown',
                        'The original Goal control process ended. No native mutation was repeated.')

    def lost_worker(self, run_id):
        if not exists(self.store): return
        from goal_worker import end_turns
        end_turns(self.store,run_id)
        rows=self.store.db.execute('SELECT session_id,native FROM session_goals WHERE run_id=?',(run_id,)).fetchall()
        for row in rows:
            value=json.loads(row['native']) if row['native'] else None
            if value and value['status']=='active':
                with self.store.db:
                    self.store.db.execute("UPDATE session_goals SET phase='unknown',reason=?,revision=revision+1 WHERE session_id=?",
                        ('The original Goal worker ended without a confirmed pause. Pause before resuming; nothing was restarted.',row['session_id']))
                    self.publish(row['session_id'])
