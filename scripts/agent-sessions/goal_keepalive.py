"""Session keepalive intent over the existing Goal journal; never controls a live run."""
import copy
import hashlib
import json
import time
import uuid
from pathlib import Path
from session_store import encode, identity, now
from store import ProjectFault
from goal_contract import objective


def exists(store):
    return store.db.execute("SELECT 1 FROM sqlite_master WHERE name='session_keepalive' AND type='table'").fetchone() is not None


def schema(store):
    store.db.execute('''CREATE TABLE IF NOT EXISTS session_keepalive(
        session_id TEXT PRIMARY KEY REFERENCES sessions(id),revision INTEGER NOT NULL,active INTEGER NOT NULL,payload TEXT NOT NULL)''')
    store.db.execute('CREATE INDEX IF NOT EXISTS active_session_keepalive ON session_keepalive(active,session_id)')


def row(store, sid):
    value=store.db.execute('SELECT * FROM session_keepalive WHERE session_id=?',(sid,)).fetchone() if exists(store) else None
    return json.loads(value['payload']) if value else None


def write(store, sid, value):
    store.db.execute('''INSERT INTO session_keepalive(session_id,revision,active,payload) VALUES(?,?,?,?)
        ON CONFLICT(session_id) DO UPDATE SET revision=excluded.revision,active=excluded.active,payload=excluded.payload''',
        (sid,value['revision'],int(value['active']),encode(value)))


def publish(store,sid):
    # A full public event history must not prevent a local Pause/Stop. The
    # original control receipt remains authoritative and independently readable.
    store.db.execute('SAVEPOINT keepalive_projection')
    try:
        from goal_store import Goals
        Goals(store).publish(sid)
    except ProjectFault:store.db.execute('ROLLBACK TO keepalive_projection')
    finally:store.db.execute('RELEASE keepalive_projection')


def elapsed(value,budget=False):
    goal=value.get('goal');clock=value.get('clock')
    if not goal:return 0,True
    if not clock:return goal.get('timeUsedSeconds',0)*1_000_000_000,goal.get('timeUsageKnown',False)
    total=clock.get('budgetNs',clock['elapsedNs']) if budget else clock['elapsedNs']
    known=clock.get('budgetKnown',clock['known']) if budget else clock['known']
    if clock.get('startedNs') is not None:
        if clock['bootId']==Path('/proc/sys/kernel/random/boot_id').read_text().strip() and time.monotonic_ns()>=clock['startedNs']:
            total+=time.monotonic_ns()-clock['startedNs']
        else:known=False
    return total,known


def checkpoint(value,reset=False,new_goal=False):
    total,known=elapsed(value)
    spent,spent_known=elapsed(value,budget=True)
    value['clock']={'elapsedNs':0 if reset else total,'known':True if reset else known,'startedNs':None,
        'budgetNs':0 if new_goal else spent,'budgetKnown':True if new_goal else spent_known,
        'bootId':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    if value.get('goal'):value['goal'].update(timeUsedSeconds=value['clock']['elapsedNs']//1_000_000_000,timeUsageKnown=value['clock']['known'])


def snapshot(store, sid):
    value=row(store,sid)
    if value is None:return None
    session=store.row(sid);goal=copy.deepcopy(value['goal'])
    if goal:
        total,known=elapsed(value);goal.update(threadId=session['thread_id'] or sid,timeUsedSeconds=total//1_000_000_000,timeUsageKnown=known)
    result={'owner':{'type':store.owner_type,'id':store.owner_id},'sessionId':sid,'threadId':session['thread_id'],
        'revision':value['revision'],'goal':goal,'lastIntent':value.get('lastIntent'),'phase':value.get('phase','idle'),
        'keepalive':{'active':value['active'],'generation':value['generation']}}
    for name in ('requestId','runId','reason'):
        if value.get(name) is not None:result[name]=value[name]
    return result


def adopted(previous, sid):
    if not previous:return None
    return {'source':'studio','goalId':previous.get('goalId') or str(uuid.uuid4()),'threadId':previous.get('threadId') or sid,
        'objective':previous['objective'],'status':previous['status'],'createdAt':previous['createdAt'],'updatedAt':previous['updatedAt'],
        'tokensUsed':previous.get('tokensUsed'),'timeUsedSeconds':previous.get('timeUsedSeconds',0),
        'timeUsageKnown':previous.get('timeUsageKnown',False),'tokenBudget':previous.get('tokenBudget'),'timeBudgetMs':previous.get('timeBudgetMs')}


def accept(goals, sid, data):
    store=goals.store;store.row(sid)
    allowed={'requestId','revision','action','objective','sessionRevision','target','targetRunId','tokenBudget','timeBudgetMs'}
    if (not isinstance(data,dict) or set(data)-allowed or not {'requestId','revision','action'}<=set(data)
        or type(data['revision']) is not int or data['revision']<0 or data['action'] not in ('save','play','pause','stop')
        or ('objective' in data)!=(data['action']=='save')):raise ProjectFault('Invalid Goal command.',400)
    rid=identity(data['requestId']);action=data['action']
    if action=='save':
        try:objective(data['objective'],allow_empty=True)
        except ValueError as error:raise ProjectFault(str(error),400) from None
    from studio_goal import budget
    for name in ('tokenBudget','timeBudgetMs'):
        if name in data:
            if action!='save':raise ProjectFault('Only Save can change Goal budgets.',400)
            budget(data[name])
    goals.schema();schema(store);db=store.db;db.execute('BEGIN IMMEDIATE')
    try:
        previous=db.execute('SELECT * FROM goal_commands WHERE request_id=?',(rid,)).fetchone()
        if previous:
            original={k:v for k,v in json.loads(previous['payload']).items() if not k.startswith('_')}
            if previous['session_id']!=sid or original!=data:raise ProjectFault('This request ID belongs to another Goal command.',409)
            return goals.receipt(sid,rid),False
        current=goals.snapshot(sid)
        if current['revision']!=data['revision']:raise ProjectFault('The Goal changed. Read its original state before changing it.',409)
        if db.execute("SELECT 1 FROM goal_commands WHERE state='pending'").fetchone():raise ProjectFault('Reconcile the original pending Goal request first.',409)
        if db.execute('SELECT COUNT(*) FROM goal_commands WHERE session_id=?',(sid,)).fetchone()[0]>=4096:raise ProjectFault('The session reached its Goal command history limit.',409)
        value=row(store,sid) or {'schema':1,'revision':current['revision'],'generation':0,'active':False,'goal':adopted(current['goal'],sid),'phase':current['phase']}
        if value['phase']=='unknown' and action not in ('pause','stop'):raise ProjectFault('Pause or Stop the unconfirmed Goal before resuming.',409)
        goal=copy.deepcopy(value['goal']);noop=action=='play' and value['active']
        if action=='save':
            if value['active']:raise ProjectFault('Pause the Goal before editing its text.',409)
            text=objective(data['objective'],allow_empty=True)
            if not text:goal=None
            elif not goal or goal['objective']!=text:
                stamp=int(time.time());goal={'source':'studio','goalId':str(uuid.uuid4()),'threadId':store.row(sid)['thread_id'] or sid,
                    'objective':text,'status':'paused','tokensUsed':0,'timeUsedSeconds':0,'timeUsageKnown':True,
                    'createdAt':stamp,'updatedAt':stamp,'tokenBudget':None,'timeBudgetMs':None}
            if goal:
                for name in ('tokenBudget','timeBudgetMs'):
                    if name in data:goal[name]=data[name]
                goal['status']='paused'
        if action=='play':
            if data.get('sessionRevision')!=store.row(sid)['revision']:raise ProjectFault('Session settings changed. Reload before pressing Start.',409)
            if not goal:raise ProjectFault('Save a Goal before pressing Start.',409)
            if goal['status']=='complete':raise ProjectFault('This Goal is complete. Save its objective explicitly before starting again.',409)
            if not noop:
                from active_tools import goal_selection
                value['tools']=goal_selection(store,sid);value['playRequestId']=rid
        if not noop:
            changed=action=='save' and (not value['goal'] or not goal or value['goal']['goalId']!=goal['goalId'])
            checkpoint(value,reset=action=='stop' or changed,new_goal=changed)
            value.update(revision=value['revision']+1,generation=value['generation']+1,active=action=='play',goal=goal,
                lastIntent=action,requestId=rid,phase='idle',reason=None)
            if goal:
                goal.update(timeUsedSeconds=value['clock']['elapsedNs']//1_000_000_000,timeUsageKnown=value['clock']['known'])
                goal.update(status='active' if value['active'] else 'paused',updatedAt=int(time.time()))
                if action=='stop':goal.update(timeUsedSeconds=0,timeUsageKnown=True)
            if value['active']:value['clock']['startedNs']=time.monotonic_ns()
            value.pop('dispatch',None);write(store,sid,value)
        result={'requestId':rid,'action':action,'state':'confirmed','snapshot':snapshot(store,sid)}
        fingerprint=hashlib.sha256(encode({'sessionId':sid,**data}).encode()).hexdigest()
        db.execute('INSERT INTO goal_commands VALUES(?,?,?,?,?,?,?,?)',
            (rid,sid,fingerprint,encode({**data,'_keepalive':1}),'confirmed','session_intent',encode(result),now()))
        publish(store,sid);db.commit();return result,True
    finally:
        if db.in_transaction:db.rollback()


def block(store,sid,reason,unknown=False,status='blocked'):
    value=row(store,sid)
    if not value or not value['active']:return
    checkpoint(value)
    value.update(active=False,revision=value['revision']+1,phase='unknown' if unknown else 'idle',reason=reason)
    value['goal'].update(status=status,updatedAt=int(time.time()))
    with store.db:
        write(store,sid,value)
        publish(store,sid)


def prepare(store,sid,after):
    value=row(store,sid)
    if not value or not value['active'] or value['phase']!='idle' or not value['goal'] or value['goal']['status']!='active':return None
    goal=value['goal']
    used,known=elapsed(value);spent,spent_known=elapsed(value,budget=True)
    goal.update(timeUsedSeconds=used//1_000_000_000,timeUsageKnown=known)
    if goal.get('timeBudgetMs') is not None and (not spent_known or spent>=goal['timeBudgetMs']*1_000_000):
        block(store,sid,'The original Goal time budget is exhausted or its elapsed time is unknown.',status='budgetLimited');return None
    if goal.get('tokenBudget') is not None and (goal.get('tokensUsed') is None or goal['tokensUsed']>=goal['tokenBudget']):
        block(store,sid,'The original Goal token budget is exhausted or its usage is unknown.',status='budgetLimited');return None
    request=str(uuid.uuid5(uuid.UUID(goal['goalId']),str(value['generation'])+':'+(after or 'initial')))
    dispatch=value.get('dispatch')
    if dispatch and dispatch['requestId']==request:
        return {**dispatch,'goal':copy.deepcopy(goal),'tools':value['tools'],'generation':value['generation'],'playRequestId':value['playRequestId']}
    dispatch={'requestId':request,'afterRunId':after,'state':'prepared'}
    value['dispatch']=dispatch
    with store.db:write(store,sid,value)
    return {**dispatch,'goal':copy.deepcopy(goal),'tools':value['tools'],'generation':value['generation'],'playRequestId':value['playRequestId']}


def require(store,sid,execution):
    value=row(store,sid)
    if (not value or not value['active'] or value['phase']!='idle' or value['goal']['status']!='active'
        or value['generation']!=execution['generation'] or value['goal']['goalId']!=execution['goal']['goalId']
        or value.get('dispatch',{}).get('requestId')!=execution['requestId']):
        raise ProjectFault('A newer Goal control superseded this unadmitted continuation.',409)
    used,known=elapsed(value,budget=True)
    if value['goal'].get('timeBudgetMs') is not None and (not known or used>=value['goal']['timeBudgetMs']*1_000_000):
        raise ProjectFault('The original Goal time budget is exhausted or unknown.',409)


def admitted(store,sid,execution,run_id):
    require(store,sid,execution);value=row(store,sid)
    value['dispatch'].update(state='admitted',runId=run_id);value['runId']=run_id
    with store.db:write(store,sid,value)


def freeze(store,sid,snapshot,execution=None,original=None):
    if original is not None:
        for key in ('goalKeepaliveControl','goalKeepalive'):
            if key in original:snapshot[key]=copy.deepcopy(original[key])
        return
    if not row(store,sid):return
    snapshot['goalKeepaliveControl']=1
    for key in ('nativeGoalPreparation','claudeGoalPreparation','studioGoalPreparation'):
        if key in snapshot:snapshot[key]=False
    if execution:
        require(store,sid,execution)
        snapshot['goalKeepalive']={k:copy.deepcopy(execution[k]) for k in ('requestId','afterRunId','goal','generation','playRequestId')}
        frozen=execution['tools'];snapshot['permissions']={k:bool(v and snapshot['permissions'].get(k,False)) for k,v in frozen['permissions'].items()}
        snapshot['toolCatalog']=copy.deepcopy(frozen['catalog'])


def instructions(config):
    original=config.get('goalKeepalive')
    if not original:return ''
    return ('\n\nSTUDIO GOAL RUN: This ordinary run was admitted at a confirmed session boundary for the following saved Goal. '
        'Work within the frozen permissions. Use studio_get_goal and studio_update_goal to report complete or blocked with a reason and confirmed receipts. '
        'End this run naturally when your response is finished. Studio alone decides whether to admit another run. Do not create a scheduler or continue loop.\n'+encode(original['goal']))
