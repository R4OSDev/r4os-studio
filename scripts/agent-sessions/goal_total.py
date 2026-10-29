"""Read-only per-session sum of original monotone Play measurements."""
import json
import os
from pathlib import Path
import sqlite3
import time

from attachment_store import birth
from goal_clock import boot, FRESH_MS
from session_store import identity, now
from stats_store import hashed, scope, validate, Statistics, MAX_NUMBER
from store import ProjectFault


def has(db, name): return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def mark_new(store, sid):
    """Called only inside new-session creation's original transaction."""
    store.db.execute('CREATE TABLE IF NOT EXISTS goal_time_coverage(session_id TEXT PRIMARY KEY REFERENCES sessions(id),version INTEGER NOT NULL)')
    store.db.execute('INSERT INTO goal_time_coverage VALUES (?,1)', (sid,))


def snapshot(store, sid, monotonic=time.monotonic_ns):
    session = store.row(sid); sid = identity(sid)
    owner = {'type': store.owner_type, 'id': store.owner_id}; session_scope = scope(owner, sid)
    project_scope = scope(owner) if store.owner_type == 'project' else None
    measurements = {}; clocks = {}; plays = set(); reasons = set(); expected = set(); samples = []
    db = store.db; own_transaction = not db.in_transaction
    if own_transaction: db.execute('BEGIN')
    try:
        marker = has(db, 'goal_time_coverage') and db.execute('SELECT 1 FROM goal_time_coverage WHERE session_id=? AND version=1',(sid,)).fetchone() is not None
        commands = has(db, 'goal_commands') and db.execute('SELECT 1 FROM goal_commands WHERE session_id=? LIMIT 1',(sid,)).fetchone() is not None
        if commands:
            for row in db.execute('SELECT request_id,payload,state,stage FROM goal_commands WHERE session_id=?',(sid,)):
                try:
                    payload=json.loads(row['payload'])
                    if payload.get('action')!='play': continue
                    rid=identity(row['request_id'])
                    # Admission alone adds no elapsed time; native mutations can.
                    if row['state']=='confirmed' or row['stage'] in ('native_activation','native_live_mutation'):
                        plays.add(rid); expected.add(rid)
                except (ProjectFault,ValueError,TypeError): reasons.add('invalid_activation_evidence')
        for row in db.execute('SELECT config FROM runs WHERE session_id=?',(sid,)):
            try:
                execution=json.loads(row['config']).get('goalExecution')
                if execution: plays.add(identity(execution['requestId']))
            except (ProjectFault,ValueError,KeyError,TypeError): reasons.add('invalid_activation_evidence')
        if has(db,'goal_clocks'):
            for row in db.execute('SELECT * FROM goal_clocks WHERE session_id=? ORDER BY rowid',(sid,)):
                try:
                    rid=identity(row['execution_id']); elapsed=row['elapsed_ns']
                    run=db.execute('SELECT session_id,busy,worker FROM runs WHERE id=?',(identity(row['run_id']),)).fetchone()
                    if (run is None or run['session_id']!=sid or type(elapsed) is not int or not 0<=elapsed//1_000_000<=MAX_NUMBER
                            or row['state'] not in ('running','ended','unknown')): raise ValueError()
                    key=hashed({'owner':owner,'session':sid,'play':rid})
                    plays.add(rid);clocks[key]=(dict(row),dict(run));measurements[key]=elapsed
                    samples.append(row['checkpoint_at'])
                except (ProjectFault,ValueError,KeyError,TypeError): reasons.add('invalid_clock_evidence')
        keys={hashed({'owner':owner,'session':sid,'play':rid}):rid for rid in plays}
        receipt_uncertain=set()

        def accept(raw, expected_key=None):
            try:
                value=validate(json.loads(raw))
                if expected_key is not None and value['key']!=expected_key:
                    reasons.add('invalid_time_receipt');return
                if value['kind']!='goal' or value['session']!=session_scope: return
                if value['project']!=project_scope or value['key'] not in keys:
                    reasons.add('unmatched_time_receipt'); return
                key=value['key'];duration=value['values']['durationMs']*1_000_000
                measurements[key]=max(measurements.get(key,0),duration)
                if value['values'].get('uncertain',True):receipt_uncertain.add(key)
            except (ProjectFault,ValueError,KeyError,TypeError): reasons.add('invalid_time_receipt')

        if has(db,'statistic_receipts'):
            try:
                for row in db.execute("SELECT payload FROM statistic_receipts WHERE json_extract(payload,'$.session')=? AND json_extract(payload,'$.kind')='goal'",(session_scope,)): accept(row[0])
            except sqlite3.Error:reasons.add('private_time_receipts_unavailable')
        try:
            target=Statistics(store.projects)
            try:
                if target.db:
                    for row in target.db.execute("SELECT payload FROM receipts WHERE json_extract(payload,'$.session')=? AND json_extract(payload,'$.kind')='goal'",(session_scope,)): accept(row[0])
            finally:target.close()
        except (ProjectFault,sqlite3.Error,OSError): reasons.add('lifetime_receipts_unavailable')
        pending=store.projects/'.studio/statistics/Pending'
        # Exact original execution keys only; never scan another session's outbox.
        for key in keys:
            file=pending/(key+'.json')
            try:
                if not file.exists() and not file.is_symlink():continue
                if file.resolve(strict=True)!=file or not file.is_file() or file.stat().st_nlink!=1 or file.stat().st_size>4096:
                    reasons.add('pending_time_receipt_unavailable');continue
                accept(file.read_text(),key)
            except FileNotFoundError:continue  # The normal numeric outbox may finish concurrently.
            except (OSError,UnicodeError):reasons.add('pending_time_receipt_unavailable')
        measured_ids={keys[k] for k in measurements if k in keys}
        if expected-measured_ids:reasons.add('missing_execution_measurement')
        # Goal runs admitted but never activated contribute no duration.
        if not marker and not commands and session['thread_id'] is not None: reasons.add('legacy_time_coverage_unavailable')
        if has(db,'session_goals'):
            row=db.execute('SELECT native,phase FROM session_goals WHERE session_id=?',(sid,)).fetchone()
            if row:
                try:
                    native=json.loads(row['native'] or '{}')
                    if row['phase']=='unknown' or native.get('status')=='active' and not clocks:
                        reasons.add('goal_activation_unconfirmed')
                    if native.get('timeUsedSeconds',0)>0 and not plays:reasons.add('legacy_time_coverage_unavailable')
                except (ValueError,TypeError,AttributeError):reasons.add('goal_activation_unconfirmed')
        running=[]
        for key,(clock,run) in clocks.items():
            if measurements[key]>clock['elapsed_ns']:
                reasons.add('clock_restore_gap');continue
            if clock['state']=='unknown':reasons.add('execution_time_unconfirmed')
            elif clock['state']=='running':running.append((key,clock,run))
        for key in measurements.keys()-clocks.keys():
            reasons.add('clock_source_missing')
            if key in receipt_uncertain:reasons.add('execution_time_unconfirmed')
        live=None
        if len(running)>1:reasons.add('multiple_live_clocks')
        elif running:
            key,clock,run=running[0]
            try:
                worker=json.loads(run['worker'] or '{}');age=(monotonic()-clock['last_ns'])//1_000_000
                if (not run['busy'] or worker.get('pid')!=clock['pid'] or worker.get('birth')!=clock['birth']
                        or clock['boot_id']!=boot() or clock['birth']!=birth(clock['pid'])
                        or (Path('/proc')/str(clock['pid'])).stat().st_uid!=os.geteuid() or not 0<=age<=FRESH_MS): raise ValueError()
                live={'executionId':clock['execution_id'],'ageMs':age,'staleAfterMs':FRESH_MS}
            except (OSError,ValueError,TypeError,KeyError):reasons.add('live_clock_unconfirmed')
        known_zero=not plays and not measurements and (marker or session['thread_id'] is None or commands) and not reasons
        total=sum(measurements.values())//1_000_000 if measurements else 0 if known_zero else None
        if total is None:reasons.add('time_not_reported')
        return {'schema':1,'durationMs':str(total) if total is not None else None,
            'state':'running' if live else 'unknown' if reasons else 'idle','live':live,'referenceAt':now(),
            'sampledAt':samples[-1] if samples else None,
            'coverage':{'state':'partial' if total is not None and reasons else 'unavailable' if total is None else 'complete',
                'measuredExecutions':len(measurements),'missingExecutions':len(expected-measured_ids),'reasons':sorted(reasons)}}
    finally:
        if own_transaction:db.rollback()
