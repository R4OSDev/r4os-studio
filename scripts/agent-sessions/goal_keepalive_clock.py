"""One monotone control clock, resettable display cycles and original numeric receipts."""
import copy
import json
from pathlib import Path
import time
import uuid
from session_store import encode,now
from stats_store import Source

FRESH_MS=6000
def boot():return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
def elapsed(value,budget=False,at=None):
    goal=value.get('goal');clock=value.get('clock')
    if not goal:return 0,True
    if not clock:return goal.get('timeUsedSeconds',0)*1_000_000_000,goal.get('timeUsageKnown',False)
    total=clock.get('budgetNs',clock['elapsedNs']) if budget else clock['elapsedNs']
    known=clock.get('budgetKnown',clock['known']) if budget else clock['known']
    if clock.get('startedNs') is not None:
        current=time.monotonic_ns() if at is None else at
        if clock['bootId']==boot() and current>=clock['startedNs']:total+=current-clock['startedNs']
        else:known=False
    return total,known

def legacy_overlap(store,sid):
    has=store.db.execute("SELECT 1 FROM sqlite_master WHERE name='goal_clocks'").fetchone()
    if has and store.db.execute("SELECT 1 FROM goal_clocks WHERE session_id=? AND state='running' LIMIT 1",(sid,)).fetchone():return True
    return store.db.execute("SELECT 1 FROM runs WHERE session_id=? AND busy=1 AND (json_extract(config,'$.goalExecution') IS NOT NULL OR json_extract(config,'$.claudeGoalExecution') IS NOT NULL) LIMIT 1",(sid,)).fetchone() is not None

def cycle_id(store,sid,value):
    clock=value.get('clock') or {}
    if clock.get('cycleId'):return clock['cycleId']
    previous=store.db.execute("SELECT request_id FROM goal_commands WHERE session_id=? AND json_extract(payload,'$._keepalive')=1 AND json_extract(payload,'$.action')='stop' ORDER BY rowid DESC LIMIT 1",(sid,)).fetchone()
    return str(uuid.uuid5(uuid.UUID((value.get('goal') or {}).get('goalId',sid)),'control-clock:'+(previous[0] if previous else 'initial')))

def schema(store):
    store.db.execute('''CREATE TABLE IF NOT EXISTS goal_keepalive_cycles(
        session_id TEXT NOT NULL REFERENCES sessions(id),cycle_id TEXT PRIMARY KEY,payload TEXT NOT NULL,pending INTEGER NOT NULL)''')
    store.db.execute('CREATE INDEX IF NOT EXISTS session_keepalive_cycles ON goal_keepalive_cycles(session_id)')
    store.db.execute('CREATE INDEX IF NOT EXISTS pending_keepalive_cycles ON goal_keepalive_cycles(session_id) WHERE pending=1')

def restore_prefix(store,sid,value):
    clock=value.get('clock') or {}
    if not clock.get('cycleId') or clock.get('startedNs') is None:return
    if clock['bootId']==boot() and time.monotonic_ns()>=clock['startedNs']:return
    if not store.db.execute("SELECT 1 FROM sqlite_master WHERE name='goal_keepalive_cycles'").fetchone():return
    row=store.db.execute('SELECT payload FROM goal_keepalive_cycles WHERE session_id=? AND cycle_id=?',(sid,clock['cycleId'])).fetchone()
    if row:
        prefix=json.loads(row['payload'])
        if prefix['goalId']==value['goal']['goalId']:
            clock['elapsedNs']=max(clock['elapsedNs'],prefix.get('durationNs',0))
            clock['budgetNs']=max(clock['budgetNs'],prefix.get('budgetNs',0))
            clock['measuredNs']=max(clock['measuredNs'],prefix['measuredNs'])
    clock.update(known=False,budgetKnown=False,startedNs=None)
    if 'measurement_gap' not in clock['historyReasons']:clock['historyReasons'].append('measurement_gap')

def ensure(store,sid,value,at=None):
    restore_prefix(store,sid,value)
    if value.get('clock',{}).get('cycleId'):return
    at=time.monotonic_ns() if at is None else at
    total,known=elapsed(value,at=at);spent,spent_known=elapsed(value,True,at)
    overlap=legacy_overlap(store,sid)
    reasons=[]
    if total or not known:reasons.append('adopted_display_prefix_excluded')
    if overlap:reasons.append('legacy_execution_overlap_excluded')
    value['clock']={'elapsedNs':total,'known':known,'budgetNs':spent,'budgetKnown':spent_known,
        'startedNs':at if value.get('active') else None,'bootId':boot(),
        'cycleId':cycle_id(store,sid,value),'measuredNs':0,'measurementExcluded':overlap,
        'historyReasons':reasons,'hasStarted':bool(value.get('active') or value.get('playRequestId')),'sampledAt':now()}

def measured(value,at=None):
    clock=value['clock'];total=clock['measuredNs'];known=clock['known']
    if clock.get('startedNs') is not None:
        current=time.monotonic_ns() if at is None else at
        if clock['bootId']==boot() and current>=clock['startedNs']:
            if not clock['measurementExcluded']:total+=current-clock['startedNs']
        else:known=False
    return total,known

def record(store,sid,value,closed=False,at=None):
    clock=value.get('clock')
    if not clock or not clock.get('cycleId') or not clock.get('hasStarted') or not value.get('goal'):return
    schema(store);duration,known=measured(value,at)
    entry={'schema':1,'cycleId':clock['cycleId'],'goalId':value['goal']['goalId'],'measuredNs':duration,
        'durationNs':elapsed(value,at=at)[0],'budgetNs':elapsed(value,True,at)[0],
        'liveMeasured':not clock['measurementExcluded'],
        'state':'unknown' if not known else 'ended' if closed or not value['active'] else 'running',
        'reasons':clock['historyReasons'],'sampledAt':now(),'controlRevision':value['revision']}
    previous=store.db.execute('SELECT session_id,payload FROM goal_keepalive_cycles WHERE cycle_id=?',(entry['cycleId'],)).fetchone()
    if previous:
        original=json.loads(previous['payload'])
        if previous['session_id']!=sid or original['goalId']!=entry['goalId'] or original['measuredNs']>duration:
            from store import ProjectFault
            raise ProjectFault('The original Goal clock cycle changed. Its history was preserved.',409)
        if {k:v for k,v in original.items() if k!='sampledAt'}=={k:v for k,v in entry.items() if k!='sampledAt'}:return
    store.db.execute('''INSERT INTO goal_keepalive_cycles(session_id,cycle_id,payload,pending) VALUES(?,?,?,1)
        ON CONFLICT(cycle_id) DO UPDATE SET payload=excluded.payload,pending=1''',(sid,entry['cycleId'],encode(entry)))

def checkpoint(value,reset=False,new_goal=False,store=None,sid=None,request_id=None):
    at=time.monotonic_ns()
    if store is not None:ensure(store,sid,value,at)
    total,known=elapsed(value,at=at);spent,spent_known=elapsed(value,True,at)
    old=copy.deepcopy(value.get('clock') or {})
    measured_ns,measurement_known=measured(value,at) if old.get('cycleId') else (0,known)
    if store is not None and reset:record(store,sid,value,closed=True,at=at)
    clock={'elapsedNs':0 if reset else total,'known':True if reset else known,'startedNs':None,'bootId':boot(),
        'budgetNs':0 if new_goal else spent,'budgetKnown':True if new_goal else spent_known}
    if old.get('cycleId'):
        clock.update(cycleId=request_id or str(uuid.uuid4()) if reset else old['cycleId'],measuredNs=0 if reset else measured_ns,
            measurementExcluded=legacy_overlap(store,sid) if reset and store is not None else old['measurementExcluded'],
            historyReasons=[] if reset else old['historyReasons'],hasStarted=False if reset else old['hasStarted'],sampledAt=now())
        if not measurement_known and not reset and 'measurement_gap' not in clock['historyReasons']:clock['historyReasons'].append('measurement_gap')
        if clock['measurementExcluded'] and 'legacy_execution_overlap_excluded' not in clock['historyReasons']:clock['historyReasons'].append('legacy_execution_overlap_excluded')
    value['clock']=clock
    if value.get('goal'):value['goal'].update(timeUsedSeconds=clock['budgetNs']//1_000_000_000,timeUsageKnown=clock['budgetKnown'])

def budget_snapshot(store,sid,value):
    value=copy.deepcopy(value);restore_prefix(store,sid,value)
    return elapsed(value,True)

def snapshot(store,sid,value):
    value=copy.deepcopy(value);restore_prefix(store,sid,value)
    total,known=elapsed(value);clock=value.get('clock') or {}
    return {'mode':'keepalive','owner':{'type':store.owner_type,'id':store.owner_id},'sessionId':sid,
        'executionId':cycle_id(store,sid,value),'cycleId':cycle_id(store,sid,value),'controlRevision':value['revision'],'generation':value['generation'],
        'durationMs':total//1_000_000,'state':'unknown' if not known else 'running' if value['active'] else 'ended',
        'referenceAt':now(),'sampledAt':clock.get('sampledAt',now()),'ageMs':0,'staleAfterMs':FRESH_MS}

def entries(store,sid,current=None):
    rows={}
    if store.db.execute("SELECT 1 FROM sqlite_master WHERE name='goal_keepalive_cycles'").fetchone():
        rows={row['cycle_id']:json.loads(row['payload']) for row in store.db.execute('SELECT cycle_id,payload FROM goal_keepalive_cycles WHERE session_id=?',(sid,))}
    if current and current.get('clock',{}).get('hasStarted') and current['clock'].get('cycleId'):
        current=copy.deepcopy(current);restore_prefix(store,sid,current)
        clock=current['clock'];duration,known=measured(current)
        rows[clock['cycleId']]={'cycleId':clock['cycleId'],'goalId':current['goal']['goalId'],'measuredNs':duration,
            'liveMeasured':not clock['measurementExcluded'],
            'state':'unknown' if not known else 'running' if current['active'] else 'ended','reasons':clock['historyReasons'],'sampledAt':now()}
    return list(rows.values())

def reconcile(store,sid):
    from goal_keepalive import row,write,exists
    if not exists(store) or not store.db.execute('SELECT 1 FROM session_keepalive WHERE session_id=?',(sid,)).fetchone():return
    store.db.execute('BEGIN IMMEDIATE')
    try:
        value=row(store,sid)
        if not value:return
        before=encode(value);ensure(store,sid,value)
        if encode(value)!=before:write(store,sid,value)
        record(store,sid,value)
        store.db.commit()
    finally:
        if store.db.in_transaction:store.db.rollback()
    # Numeric transport follows the original committed cycle, never commits
    # inside a Goal control transaction or resets an older receipt.
    for pending in store.db.execute('SELECT cycle_id,payload FROM goal_keepalive_cycles WHERE session_id=? AND pending=1 LIMIT 128',(sid,)).fetchall():
        entry=json.loads(pending['payload'])
        Source(store).put(sid,'goal',{'owner':{'type':store.owner_type,'id':store.owner_id},'session':sid,'play':entry['cycleId']},
            {'durationMs':entry['measuredNs']//1_000_000,'uncertain':entry['state']=='unknown' or bool(entry['reasons'])})
        with store.db:store.db.execute('UPDATE goal_keepalive_cycles SET pending=0 WHERE cycle_id=? AND payload=?',(pending['cycle_id'],pending['payload']))

def retain_before_delete(db,projects,path):
    """Feed original pending numeric cycles into the existing deletion outbox."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='goal_keepalive_cycles'").fetchone():return
    from types import SimpleNamespace
    from owner import skills_root
    from session_store import identity
    from store import ProjectFault
    owner_id=identity(path.parent.parent.name);parent=path.parent.parent.parent
    if parent==projects:kind='project'
    elif parent==skills_root(projects):kind='skill'
    else:raise ProjectFault('The original Goal statistics owner could not be verified.',503)
    def owned(sid):
        value=db.execute('SELECT id FROM sessions WHERE id=? AND project_id=?',(sid,owner_id)).fetchone()
        if value is None:raise ProjectFault('The original numeric Goal cycle belongs to another owner.',503)
        return value
    source=SimpleNamespace(db=db,projects=projects,owner_type=kind,owner_id=owner_id,row=owned)
    for session in db.execute('SELECT DISTINCT session_id FROM goal_keepalive_cycles').fetchall():
        sid=session['session_id'];owned(sid)
        while True:
            before=db.execute('SELECT COUNT(*) FROM goal_keepalive_cycles WHERE session_id=? AND pending=1',(sid,)).fetchone()[0]
            reconcile(source,sid)
            after=db.execute('SELECT COUNT(*) FROM goal_keepalive_cycles WHERE session_id=? AND pending=1',(sid,)).fetchone()[0]
            if not after:break
            if after>=before:raise ProjectFault('The original Goal numeric receipts need reconciliation before deletion.',503)
