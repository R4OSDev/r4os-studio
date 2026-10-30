"""Provider-specific Studio Goal intents and projections; no native Goal RPCs."""
import fcntl
import json
import os
import time
import uuid

from attachment_store import birth
from claude_goal import MAX_ACTIVE_SECONDS, MAX_STEPS, digest
from goal_contract import MAX_SAFE_INTEGER, STATUSES, objective
from owner import open_lock
from session_store import encode, identity, now
from store import ProjectFault


def limits(): return {'maxSteps': MAX_STEPS, 'maxActiveSeconds': MAX_ACTIVE_SECONDS}


def validate(value, native):
    if value is None: return None
    required={'source','goalId','nativeSessionId','threadId','objective','status','tokensUsed','timeUsedSeconds','createdAt','updatedAt','limits'}
    if (not isinstance(value,dict) or set(value)-required-{'executionId','stepsCompleted'} or not required<=set(value)
            or value['source']!='studio-claude' or value['threadId'] is not None or value['nativeSessionId']!=native
            or value['status'] not in STATUSES or value['tokensUsed'] is not None or value['limits']!=limits()):
        raise ProjectFault('The saved Studio Claude Goal binding is invalid. Original data was preserved.',409)
    identity(value['goalId']);identity(native)
    if objective(value['objective'])!=value['objective']:raise ProjectFault('The saved Studio Goal text changed.',409)
    for key in ('timeUsedSeconds','createdAt','updatedAt'):
        if type(value[key]) is not int or not 0<=value[key]<=MAX_SAFE_INTEGER:raise ProjectFault('The saved Studio Goal contains an invalid time.',409)
    if 'executionId' in value:identity(value['executionId'])
    if 'stepsCompleted' in value and (type(value['stepsCompleted']) is not int or not 0<=value['stepsCompleted']<=MAX_STEPS):
        raise ProjectFault('The saved Studio Goal step count is invalid.',409)
    return value


def snapshot(goals,sid):
    store=goals.store;session=store.row(sid);engine=json.loads(session['engine']);native=engine['claude']['nativeSessionId']
    from goal_store import exists
    row=store.db.execute('SELECT * FROM session_goals WHERE session_id=?',(sid,)).fetchone() if exists(store) else None
    value=validate(json.loads(row['native']) if row and row['native'] else None,native)
    result={'owner':{'type':store.owner_type,'id':store.owner_id},'sessionId':sid,'threadId':None,
        'revision':row['revision'] if row else 0,'goal':value,'lastIntent':row['last_intent'] if row else None,'phase':row['phase'] if row else 'idle'}
    if row:
        result.update({public:row[column] for column,public in (('request_id','requestId'),('run_id','runId'),('reason','reason')) if row[column] is not None})
    if value and value.get('executionId'):
        from goal_clock import snapshot as clock_snapshot
        clock=clock_snapshot(store,sid)
        if clock and clock['executionId']==value['executionId']:value['timeUsedSeconds']=clock['durationMs']//1000
    # Claude conversation identity is never placed into Codex's thread_id.
    if session['thread_id'] is not None:raise ProjectFault('This Claude session has a foreign native thread binding.',409)
    return result


def target(store,sid,run):
    config=json.loads(run['config']);meta=json.loads(run['worker'] or '{}');spec=config.get('claudeGoalExecution')
    try:current_birth=birth(meta['pid']) if type(meta.get('pid')) is int and meta['pid']>0 else None
    except OSError:current_birth=None
    if (not spec or config['engine'].get('kind')!='claude-code' or run['session_id']!=sid
            or run['state'] not in ('starting','running','stopping') or not run['busy']
            or not current_birth or current_birth!=meta.get('birth') or not meta.get('release')):
        raise ProjectFault('The original bounded Claude Goal worker is unavailable. Read its original result.',409)
    row=store.db.execute('SELECT payload FROM claude_goal_executions WHERE execution_id=? AND session_id=? AND run_id=?',
        (spec['executionId'],sid,run['id'])).fetchone()
    if not row or json.loads(row[0]).get('controlOpen') is not True:
        raise ProjectFault('The original Claude Goal worker is closing. Read its original result.',409)
    return {'runId':run['id'],'executionId':spec['executionId'],'nativeSessionId':spec['nativeSessionId'],
        'configSha256':digest(config),'worker':meta}


def accept(goals,sid,data):
    store=goals.store
    if (not isinstance(data,dict) or not {'requestId','revision','action'}<=set(data)
            or set(data)-{'requestId','revision','action','objective','sessionRevision'}
            or type(data['revision']) is not int or not 0<=data['revision']<=MAX_SAFE_INTEGER
            or data['action'] not in ('save','play','pause','stop') or (('objective' in data)!=(data['action']=='save'))
            or 'sessionRevision' in data and (type(data['sessionRevision']) is not int or data['sessionRevision']<1)):
        raise ProjectFault('Invalid Studio Claude Goal command. Live activation requires its separately qualified adapter.',400)
    key=identity(data['requestId']);hashed=digest({'sessionId':sid,**data})
    if data['action']=='save':
        try:objective(data['objective'],allow_empty=True)
        except ValueError as error:raise ProjectFault(str(error),400) from None
    goals.schema();db=store.db;db.execute('BEGIN IMMEDIATE')
    try:
        previous=db.execute('SELECT * FROM goal_commands WHERE request_id=?',(key,)).fetchone()
        if previous:
            if previous['session_id']!=sid or previous['fingerprint']!=hashed:raise ProjectFault('This request ID belongs to another Goal command.',409)
            return goals.receipt(sid,key),False
        current=snapshot(goals,sid);saved=current['goal'];action=data['action']
        if current['revision']!=data['revision']:raise ProjectFault('The Goal changed. Reload before changing it.',409)
        from goal_store import pending
        if pending(store):raise ProjectFault('Reconcile the original pending Goal command first.',409)
        if current['phase']=='unknown' and action not in ('pause','stop'):raise ProjectFault('Pause or Stop the original unconfirmed Goal before changing it.',409)
        if db.execute('SELECT COUNT(*) FROM goal_commands WHERE session_id=?',(sid,)).fetchone()[0]>=4096:
            raise ProjectFault('This session reached its Goal command history limit.',409)
        busy=db.execute('SELECT * FROM runs WHERE busy=1').fetchone();bound=None
        if busy:
            if busy['session_id']!=sid:raise ProjectFault('Another session is using this workspace.',409)
            if action not in ('pause','stop'):raise ProjectFault('Wait for this run to end before saving or starting a Claude Goal. Your draft was preserved.',409)
            if action=='pause' and busy['state']=='stopping':raise ProjectFault('This original Goal is already stopping. Read its original result.',409)
            bound=target(store,sid,busy)
        if action=='save' and saved and saved['status']=='active':raise ProjectFault('Pause the active Goal before changing its text.',409)
        if action=='play':
            if not saved:raise ProjectFault('Save a Goal before pressing Play.',409)
            if saved['status']=='active' or current['phase']!='idle':raise ProjectFault('The original Goal is active or still pausing.',409)
            if data.get('sessionRevision')!=store.row(sid)['revision']:raise ProjectFault('Session settings changed. Reload before pressing Play.',409)
            from message_store import pending_queue
            if pending_queue(store,sid):raise ProjectFault('Continue or remove the saved message queue before pressing Play.',409)
            from claude_history import ClaudeHistory
            if ClaudeHistory(store,sid).get()['phase'] not in ('allocated','ready'):
                raise ProjectFault('The original native Claude history is unconfirmed. No Goal was started.',409)
        payload={**data,'_goal':saved,'_previousPhase':current['phase'],**({'_claudeTarget':bound} if bound else {})}
        db.execute('INSERT INTO goal_commands VALUES (?,?,?,?,?,?,NULL,?)',(key,sid,hashed,encode(payload),'pending','accepted',now()))
        db.execute('''INSERT INTO session_goals VALUES (?,1,NULL,NULL,'pending',?,NULL,NULL)
            ON CONFLICT(session_id) DO UPDATE SET revision=revision+1,phase='pending',request_id=excluded.request_id,reason=NULL''',(sid,key))
        db.commit();return goals.receipt(sid,key),True
    finally:
        if db.in_transaction:db.rollback()


def write(goals,sid,value,phase='idle',run_id=None,reason=None):
    store=goals.store;native=store.get(sid)['engine']['claude']['nativeSessionId'];validate(value,native)
    store.db.execute('UPDATE session_goals SET native=?,phase=?,run_id=COALESCE(?,run_id),reason=?,revision=revision+1 WHERE session_id=?',
        (encode(value) if value else None,phase,run_id,reason,sid))
    goals.publish(sid)


def idle(goals,sid,rid):
    """A local saved intent has no native process, authentication or model send."""
    store=goals.store;row=goals.command(sid,rid);data=json.loads(row['payload'])
    if row['state']!='pending':return goals.receipt(sid,rid)
    if data['action']=='play':raise ProjectFault('Play requires its original admitted bounded worker.',409)
    lock=open_lock(store.projects,store.owner_type,store.owner_id)
    try:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ProjectFault('The original workspace operation is still active.',409) from None
        if store.db.execute('SELECT 1 FROM runs WHERE busy=1').fetchone():raise ProjectFault('The owning Claude Goal worker must confirm this command.',409)
        current=snapshot(goals,sid);value=current['goal'];phase='idle';reason=None
        if data['action']=='save':
            text=objective(data['objective'],allow_empty=True)
            if not text:value=None
            elif not value or value['objective']!=text:
                stamp=int(time.time());value={'source':'studio-claude','goalId':str(uuid.uuid4()),'nativeSessionId':store.get(sid)['engine']['claude']['nativeSessionId'],
                    'threadId':None,'objective':text,'status':'paused','tokensUsed':None,'timeUsedSeconds':0,
                    'createdAt':stamp,'updatedAt':stamp,'limits':limits()}
            else:value={**value,'status':'paused','updatedAt':int(time.time())}
        else:
            from claude_history import ClaudeHistory
            if ClaudeHistory(store,sid).get()['phase'] not in ('allocated','ready'):
                phase='unknown';reason='The Goal is paused locally. Its original native history is still unconfirmed; nothing was replayed.'
            if value:value={**value,'status':'paused','updatedAt':int(time.time())}
        with store.db:
            write(goals,sid,value,phase=phase,reason=reason)
            return goals.finish(sid,rid,phase=phase,reason=reason)
    finally:lock.close()


def pending_controls(worker):
    return [row for row in worker.store.db.execute("SELECT * FROM goal_commands WHERE session_id=? AND state='pending'",(worker.session_id,)).fetchall()
        if json.loads(row['payload']).get('_claudeTarget',{}).get('runId')==worker.run_id]


def project(worker,journal,final=False):
    """Project only this original Play; local authority and native identity differ."""
    from goal_store import Goals
    goals=Goals(worker.store);row=goals.command(worker.session_id,journal['contract']['requestId']);data=json.loads(row['payload'])
    current=snapshot(goals,worker.session_id);value=current['goal']
    if not value or value['goalId']!=(data.get('_goal') or {}).get('goalId'):
        raise ProjectFault('The saved Studio Goal changed during its original Play.',409)
    phase=current['phase'];reason=current.get('reason');value={**value,'executionId':journal['contract']['executionId'],
        'stepsCompleted':sum(step['nativeResult'] is not None for step in journal['steps']),'updatedAt':int(time.time())}
    started=journal['startedNs'] is not None
    if final:
        unknown=journal['state']=='unknown';value['status']='blocked' if unknown else journal['state']
        phase='unknown' if unknown else 'idle';reason=journal['reason']
    elif started and row['state']=='pending':value['status']='active';phase='idle'
    # A pending Pause/Stop must keep its original receipt and phase while late
    # positive native input observations still retain their own evidence.
    with worker.store.db:
        write(goals,worker.session_id,value,phase,worker.run_id,reason)
        if row['state']=='pending' and (started or final):
            goals.finish(worker.session_id,row['request_id'],'confirmed' if started else ('unknown' if journal['state']=='unknown' else 'failed'),
                reason=reason,phase=phase)


def stopping(worker):
    """Direct user Stop is also a local revocation before native input exists."""
    from goal_store import Goals
    from run_store import get_run
    if get_run(worker.store,worker.run_id)['state']!='stopping' or worker.uncertain_effect:return
    goals=Goals(worker.store);current=snapshot(goals,worker.session_id)
    if not current['goal']:return
    with worker.store.db:
        write(goals,worker.session_id,{**current['goal'],'status':'paused','updatedAt':int(time.time())},'pausing',worker.run_id)
        worker.store.db.execute("UPDATE session_goals SET last_intent='stop' WHERE session_id=?",(worker.session_id,))
        goals.publish(worker.session_id)


def lost(store,run_id):
    """Preserve unknown observations; never make a lost execution playable."""
    from goal_store import Goals,exists
    if not exists(store):return
    for row in store.db.execute('SELECT session_id,native FROM session_goals WHERE run_id=?',(run_id,)).fetchall():
        value=json.loads(row['native']) if row['native'] else None
        if not value or value.get('source')!='studio-claude':continue
        if value['status']!='active':continue
        with store.db:
            write(Goals(store),row['session_id'],{**value,'status':'blocked','updatedAt':int(time.time())},'unknown',run_id,
                'The original Claude Goal worker ended without a confirmed closure. Nothing was restarted.')
