"""Future, proven primary quota stops; no historical reactivation or inference."""
import base64
import hashlib
import json
import uuid
from session_store import encode,identity,now
from run_store import get_run,event
from store import ProjectFault
OPEN=('waiting','dispatching')

def has(store):return bool(store.db.execute("SELECT 1 FROM sqlite_master WHERE name='session_quota_wait'").fetchone())
def schema(store):
    store.db.execute('CREATE TABLE IF NOT EXISTS session_quota_wait(session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,revision INTEGER NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL)')
    store.db.execute('CREATE INDEX IF NOT EXISTS quota_wait_active ON session_quota_wait(state,session_id)')
def digest(value):return hashlib.sha256(encode(value).encode()).hexdigest()
def row(store,sid):
    saved=store.db.execute('SELECT * FROM session_quota_wait WHERE session_id=?',(sid,)).fetchone() if has(store) else None
    return {**json.loads(saved['payload']),'revision':saved['revision'],'state':saved['state']} if saved else None

def public(store,sid):
    value=row(store,sid)
    if value is None:return {'revision':0,'state':'idle','active':False,'waitId':None}
    fields=('id','sourceRunId','providerId','model','reason','createdAt','negativeAt','resetAt','observation','resumedRunId')
    return {'revision':value['revision'],'state':value['state'],'active':value['state']=='waiting','waitId':value.get('id'),
        **{k:value[k] for k in fields if k in value and k!='id'}}

def put(store,sid,value,publish=True):
    store.db.execute('INSERT INTO session_quota_wait VALUES (?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET revision=excluded.revision,state=excluded.state,payload=excluded.payload',
        (sid,value['revision'],value['state'],encode({k:v for k,v in value.items() if k not in ('revision','state')})))
    if publish:
        store.db.execute('SAVEPOINT quota_projection')
        try:event(store,sid,None,'quotaWait',public(store,sid),False)
        except ProjectFault:store.db.execute('ROLLBACK TO quota_projection')
        finally:store.db.execute('RELEASE quota_projection')

def control(store,sid,reason,only_goal=False):
    value=row(store,sid)
    if only_goal and (not value or not value.get('goal')):return
    schema(store);value=value or {'epoch':0,'revision':0,'state':'idle'}
    value.update(epoch=value['epoch']+1,revision=value['revision']+1)
    if value['state'] in OPEN:value.update(state='cancelled',reason=reason,endedAt=now())
    put(store,sid,value)

def settings_hash(store,sid):
    session=store.row(sid)
    return digest({'settings':json.loads(session['settings']),'engine':json.loads(session['engine'])})

def freeze(store,sid,config):
    from model_choice import public as choice
    saved=row(store,sid)
    config['quotaWait']={'protocol':1,'epoch':saved['epoch'] if saved else 0,'selectionRevision':choice(store,sid)['selectionRevision'],'settingsSha256':settings_hash(store,sid)}

def matches(store,sid,config):
    from model_choice import public as choice
    frozen=config.get('quotaWait');value=row(store,sid)
    goal=config.get('goalKeepalive')
    if goal:
        from goal_keepalive import row as goal_row
        current=goal_row(store,sid)
        if not current or not current['active'] or current['generation']!=goal['generation'] or current['goal']['goalId']!=goal['goal']['goalId']:return False
    return bool(frozen and frozen.get('protocol')==1 and frozen['epoch']==(value['epoch'] if value else 0)
        and frozen['selectionRevision']==choice(store,sid)['selectionRevision'] and frozen['settingsSha256']==settings_hash(store,sid))

def evidence(config,error):
    """A complete negative HTTP response plus a known business fact, never 429 alone."""
    details=getattr(error,'details',None)
    if (getattr(error,'not_dispatched',False) or getattr(error,'http_status',None)!=429 or not isinstance(details,dict)
            or details.get('httpResponseComplete') is not True or details.get('bodyTruncated') is True):return None
    try:
        raw=base64.b64decode(details.get('providerBodyBase64',''),validate=True)
        if not raw or len(raw)>65536:return None
        from model_transport import loads
        body=loads(raw.decode());inner=body.get('error',body)
        if not isinstance(inner,dict):return None
        code=str(inner.get('code',inner.get('type','')))
    except (ValueError,TypeError,AttributeError,ProjectFault):return None
    kind=config.get('apiProvider',{}).get('kind')
    known=(kind=='zai-coding-plan' and code in ('1308','1310','1316','1317','1318','1319','1320','1321')
        or kind=='codex-subscription' and code in ('usage_limit_reached','usage_limit_exceeded','insufficient_quota')
        or kind=='chatgpt-plan' and code=='subscription_sharing_usage_limit_exceeded'
        or kind in ('openrouter','openai-compatible','local') and code in ('insufficient_quota','quota_exceeded','usage_limit_exceeded'))
    if not known:return None
    reset=None
    from zai_monitor import stamp
    for name in ('reset_at','resets_at','nextResetTime'):
        value=inner.get(name)
        if type(value) in (int,float) and value>0:
            import datetime
            try:reset=datetime.datetime.fromtimestamp(value/(1000 if name=='nextResetTime' else 1),datetime.timezone.utc).isoformat()
            except (ValueError,OverflowError,OSError):pass
        elif stamp(value):reset=value
        if reset:break
    return {'kind':'confirmed-primary-quota','code':code,'httpStatus':429,'responseSha256':hashlib.sha256(raw).hexdigest(),
        'resetAt':reset,'windows':'all-relevant-account-windows','observedAt':now()}

def snapshot_evidence(config,error,providers):
    if getattr(error,'http_status',None)!=429:return None
    if not getattr(error,'not_dispatched',False) and (not isinstance(getattr(error,'details',None),dict) or error.details.get('httpResponseComplete') is not True):return None
    kind=config.get('apiProvider',{}).get('kind')
    if kind not in ('claude-plan','zai-coding-plan'):return None
    # This branch is a cache-only proof read; it must never start a quota request.
    if kind=='claude-plan':
        from connection_limits import Limits
        reader=Limits(providers);p=reader.provider(config['providerId']);saved=reader.record(p)
        if not saved or saved.get('error') or saved.get('extraUsageEnabled') is not False:return None
        sample=saved['public'];windows=(sample.get('claude') or {}).get('windows',[])
        if (sample.get('claude') or {}).get('coverage')!='available':return None
        negative=[w for w in windows if w.get('remainingPercent')==0]
        observed=sample.get('checkedAt');source=(sample.get('claude') or {}).get('accountIdentity')
    else:
        from zai_quota import Quota
        sample=Quota(providers).listing(config['providerId'])
        if sample['state']!='current':return None
        negative=[w for w in sample['limits'] if w['type'] in ('CREDIT_LIMIT','TOKENS_LIMIT') and w['remaining']==0]
        observed=sample['checkedAt'];source=sample['scopeId']
    from zai_monitor import stamp
    import datetime
    if not negative or not stamp(observed) or not source or not 0<=(datetime.datetime.now(datetime.timezone.utc)-stamp(observed)).total_seconds()<90:return None
    return {'kind':'confirmed-primary-quota','code':'confirmed-empty-account-window','observedAt':now(),'sourceObservedAt':observed,'sourceIdentity':source,
        'sourceSha256':digest(sample),'windows':[w['id'] for w in negative],'resetAt':next((w.get('resetAt',w.get('resetsAt')) for w in negative if w.get('resetAt',w.get('resetsAt'))),None),'httpStatus':429}

def register(worker,operation,proof):
    w=worker;store=w.store;sid=w.session_id;config=w.config
    if (not proof or not operation or w.stopping or w.uncertain_effect or config.get('quotaResume') or not matches(store,sid,config)):
        return None
    current_goal=getattr(w,'goal_worker',None)
    if current_goal and current_goal.current() and current_goal.current().get('status') in ('complete','completed','blocked','budgetLimited'):return None
    source=get_run(store,w.run_id)
    if not source['busy'] or source['session_id']!=sid or config.get('owner')!={'type':store.owner_type,'id':store.owner_id}:return None
    call=store.db.execute('SELECT data,phase FROM studio_model_calls WHERE run_id=? AND request_id=?',(w.run_id,operation)).fetchone()
    if not call:return None
    original=json.loads(call['data'])
    if (original.get('vision') or call['phase']!='failed' or not original.get('processEnd',{}).get('confirmed')
            or original.get('quotaEvidence')!=proof):return None
    rid=str(uuid.uuid5(uuid.UUID(w.run_id),'quota-wait'))
    store.db.execute('BEGIN IMMEDIATE')
    try:
        if not matches(store,sid,config):return None
        old=store.db.execute("SELECT response FROM requests WHERE request_id=? AND kind='quota_wait'",(rid,)).fetchone()
        if old:return row(store,sid)
        schema(store);previous=row(store,sid) or {'epoch':0,'revision':0,'state':'idle'}
        if previous['state'] in OPEN:return previous
        thread=store.row(sid)['thread_id'] or sid
        progress=store.db.execute('SELECT COALESCE(MAX(seq),0) FROM conversation_records WHERE session_id=?',(sid,)).fetchone()[0]
        goal=config.get('goalKeepalive')
        account=proof.get('sourceIdentity')
        if config['apiProvider']['kind']=='zai-coding-plan':
            from api_provider_store import ApiProviders
            from zai_quota import scope
            with ApiProviders(w.manifest['providers']).connect() as db:account=scope(db,config['apiProvider'])
        elif config.get('apiClaudeGrant'):
            account=hashlib.sha256(json.dumps(config['apiClaudeGrant']['identity'],sort_keys=True).encode()).hexdigest()
        value={'id':rid,'epoch':previous['epoch'],'revision':previous['revision']+1,'state':'waiting','owner':{'type':store.owner_type,'id':store.owner_id},'sessionId':sid,'threadId':thread,
            'sourceRunId':w.run_id,'sourceRequestId':source['request_id'],'sourceInputSha256':source['payload_hash'],'configSha256':digest(json.loads(source['config'])),
            'operationId':operation,'providerId':config['providerId'],'model':config['model'],'providerBinding':config['apiProvider'],
            'nativeAccount':config.get('apiNativeAccount'),'accountIdentity':account,'goal':{'generation':goal['generation'],'goalId':goal['goal']['goalId']} if goal else None,
            'confirmedThroughSequence':progress,'selection':config['quotaWait'],'proof':proof,'negativeAt':proof['observedAt'],'createdAt':now(),
            'resetAt':proof.get('resetAt'),'reason':'The primary model reported an exhausted usage allowance. Waiting for fresh matching quota evidence.',
            'observation':{'state':'unknown','reason':'Fresh account observation pending.'},'continuation':'continue-open-work'}
        put(store,sid,value)
        store.db.execute('INSERT INTO requests VALUES (?,?,?,?,?)',(rid,'quota_wait',digest(value),sid,encode({'original':value})))
        store.db.commit();return value
    finally:
        if store.db.in_transaction:store.db.rollback()
