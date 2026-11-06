"""Durable local admission/backoff for the existing original quota GET."""
import datetime
import json
import uuid
from api_catalog import has
from session_store import encode,now
from store import ProjectFault
FIELDS=('id','kind','baseUrl','protocol','auth','revision','credentialRevision')

def stamp(value):
    try:
        result=datetime.datetime.fromisoformat(value)
        return result if result.tzinfo else None
    except (ValueError,TypeError):return None

def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS zai_monitor(provider_id TEXT NOT NULL,config_revision INTEGER NOT NULL,credential_revision INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(provider_id,config_revision,credential_revision))')
    db.execute('CREATE INDEX IF NOT EXISTS quota_request_phase ON catalog_requests(provider_id,operation,phase)')

def key(p):return (p['id'],p['revision'],p['credentialRevision'])

def record(db,p):
    row=db.execute('SELECT payload FROM zai_monitor WHERE provider_id=? AND config_revision=? AND credential_revision=?',key(p)).fetchone() if has(db,'zai_monitor') else None
    return json.loads(row[0]) if row else {'lastAttemptAt':None,'nextAutoAt':None,'failures':0,'retryAfterAt':None,'lastRequestId':None}

def put(db,p,value):
    db.execute('INSERT OR REPLACE INTO zai_monitor VALUES (?,?,?,?)',(*key(p),encode(value)))

def public(db,p):
    value=record(db,p)
    pending=db.execute("SELECT id,phase,result FROM catalog_requests WHERE provider_id=? AND operation='quota_refresh' AND phase!='complete' ORDER BY created_at LIMIT 1",(p['id'],)).fetchone() if has(db,'catalog_requests') else None
    return {**value,'pendingRequestId':pending['id'] if pending else None,'pendingState':'unknown' if pending and pending['phase']=='unknown' else 'pending' if pending else None}

def claimed(db,p,rid):
    schema(db);value=record(db,p);started=now();value.update(lastAttemptAt=started,lastRequestId=rid,nextAutoAt=(stamp(started)+datetime.timedelta(seconds=60)).isoformat(),retryAfterAt=None)
    put(db,p,value)

def finished(db,p,rid,error,retry_after):
    value=record(db,p)
    if value['lastRequestId']!=rid:return
    value['failures']=min(16,value['failures']+1) if error else 0
    delay=min(900,60*2**min(4,max(0,value['failures']-1)))
    end=(stamp(value['lastAttemptAt']) or stamp(now()))+datetime.timedelta(seconds=delay)
    retry=stamp(retry_after)
    if retry and retry>end:end=retry
    value.update(nextAutoAt=end.isoformat(),retryAfterAt=retry.isoformat() if retry else None)
    put(db,p,value)

def admit(store,ident,allowed=True,data=None):
    from zai_policy import require
    with store.api.connect(write=True) as db:
        store.schema(db)
        if data is not None:
            rid,fingerprint,old=store.original(db,ident,data,'quota_refresh')
            if old:return old,False
        p=store.api.current(db,ident);require(p)
        if data is not None and (set(data)!={'requestId','providerRevision'} or type(data['providerRevision']) is not int or data['providerRevision']!=p['revision']):
            raise ProjectFault('Subscription settings changed. Reload before checking limits.',409)
        state=public(db,p)
        if state['pendingRequestId']:
            return store.receipt_in(db,ident,state['pendingRequestId']),False
        if not p['enabled'] or not p['keyConfigured']:
            if data is not None:raise ProjectFault('Connect your Z.AI subscription before checking limits.',409)
            return None,False
        current=stamp(now());until=stamp(state['retryAfterAt'])
        if until and until>current:
            if data is not None:raise ProjectFault('The provider requested a wait before another quota check.',429)
            return None,False
        if data is None:
            due=stamp(state['nextAutoAt'])
            if not due and has(db,'zai_quota'):
                old=db.execute('SELECT checked_at FROM zai_quota WHERE provider_id=? AND config_revision=? AND credential_revision=?',key(p)).fetchone()
                due=stamp(old[0])+datetime.timedelta(seconds=60) if old and stamp(old[0]) else None
            if due and due>current:return None,False
        busy=db.execute("SELECT 1 FROM catalog_requests WHERE provider_id=? AND phase!='complete' LIMIT 1",(ident,)).fetchone()
        if busy or not allowed:
            if data is not None:raise ProjectFault('Subscription checks are busy. No new request was sent.',429)
            return None,False
        if data is None:
            data={'requestId':str(uuid.uuid4()),'providerRevision':p['revision']};rid,fingerprint,old=store.original(db,ident,data,'quota_refresh')
        binding={k:p[k] for k in FIELDS}
        # DNS/TLS failures also consume a bounded check attempt. Claim refreshes
        # this timestamp immediately before the original credential is sent.
        claimed(db,p,rid)
        db.execute("INSERT INTO catalog_requests VALUES (?,?,?,?,?,'reserved',0,NULL,NULL,?)",(rid,ident,'quota_refresh',fingerprint,encode(binding),now()))
        return {'requestId':rid,'providerId':ident,'state':'pending'},True
