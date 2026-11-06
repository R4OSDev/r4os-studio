"""Small adapter over existing account readers; never probes a model."""
import json
from api_provider_store import ApiProviders
from session_store import now
from zai_monitor import stamp
from store import ProjectFault

def same(current,expected):
    return current['enabled'] and all(current.get(k)==expected.get(k) for k in ('id','kind','baseUrl','protocol','auth','revision','credentialRevision'))

def read(providers,wait):
    p=ApiProviders(providers).get(wait['providerId'])
    if not same(p,wait['providerBinding']):raise ProjectFault('The original quota account/credential selection changed.',409)
    kind=p['kind'];windows=[];holds=[];started=None;observed=None;source=None;error=None;current=False
    if kind=='zai-coding-plan':
        from zai_quota import Quota
        q=Quota(providers).listing(p['id']);monitor=q['monitor'];observed=q['checkedAt'];current=q['state']=='current';error=q['error'];holds=q['holds'];source=q['scopeId']
        # A failed/active later attempt must never relabel an older positive observation.
        with Quota(providers).api.connect() as db:
            record=db.execute("SELECT binding FROM catalog_requests WHERE provider_id=? AND operation='quota_refresh' AND phase='complete' AND json_extract(binding,'$.quotaObservedAt')=? AND json_extract(binding,'$.quotaOriginal') IS NOT NULL ORDER BY created_at DESC LIMIT 1",(p['id'],observed)).fetchone() if observed else None
            original=json.loads(record[0]) if record else {};started=original.get('quotaAttemptedAt')
        windows=[{'id':str(w['type'])+':'+str(w['nativeUnit'])+':'+str(w['nativeCount']),'label':w['window'],'remaining':w['remaining'],'resetAt':w['resetAt']} for w in q['limits'] if w['type'] in ('CREDIT_LIMIT','TOKENS_LIMIT')]
        next_check=monitor.get('nextAutoAt')
    elif kind in ('claude-plan','openrouter'):
        from connection_limits import Limits
        reader=Limits(providers);q=reader.listing(p['id']);raw=reader.record(p);current=q['state']=='current';error=q['error'];observed=q['checkedAt'];started=(raw or {}).get('attemptedAt');source=(raw or {}).get('identity');next_check=None
        if kind=='claude-plan':
            c=q.get('claude') or {};source=c.get('accountIdentity')
            windows=[{'id':w['id'],'label':w.get('label',w['id']),'remaining':w['remainingPercent'],'resetAt':w.get('resetsAt')} for w in c.get('windows',[])]
            if c.get('coverage')!='available':current=False
        else:
            budget=q.get('openrouter') or {};rows=[budget.get('keyBudget'),budget.get('effectiveBudget'),*budget.get('budgets',[])]
            windows=[{'id':str(w.get('scope'))+':'+str(w.get('resetInterval')),'label':w.get('scope','Budget'),'remaining':1 if w.get('unlimited') is True else w.get('remainingUsd'),'resetAt':w.get('resetsAt')} for w in rows if w]
            daily=budget.get('freeModelDailyRequests')
            if daily:windows.append({'id':'free-model-daily-requests','label':'Free model daily requests','remaining':daily.get('remaining'),'resetAt':None})
    elif kind=='codex-subscription':
        from native_openai import limits
        data=limits(providers,p['id'],wait['nativeAccount']);q=data['usage'];observed=q['fetchedAt'];started=data['startedAt'];source=q.get('accountScope');current=True;next_check=None
        for meter in q['limits']:
            for name in ('primary','secondary'):
                w=meter.get(name)
                if w:windows.append({'id':meter['id']+':'+name,'label':meter.get('name',meter['id']),'remaining':w.get('remainingPercent'),'resetAt':w.get('resetsAt')})
            if meter.get('limitReached'):holds.append({'reason':'The native account still reports a reached limit.'})
        if q.get('ordinaryUsageAllowed') is False:holds.append({'reason':'Ordinary account usage remains unavailable.'})
    else:return {'state':'unknown','reason':'This connection has no confirmed account-limit reader. No model probe was started.','windows':[],'startedAt':None,'observedAt':None,'source':None,'holds':[],'nextCheckAt':None}
    return {'state':'current' if current else 'stale' if observed else 'unknown','reason':error,'windows':windows,'startedAt':started,'observedAt':observed,'source':source,'holds':holds,'nextCheckAt':next_check}

def summary(value):
    return {'state':value['state'],'checkedAt':value.get('observedAt'),'startedAt':value.get('startedAt'),'nextCheckAt':value.get('nextCheckAt'),'reason':value.get('reason'),
        'windows':[{'id':w['id'],'label':w['label'],'remaining':w['remaining'],'resetAt':w['resetAt']} for w in value.get('windows',[])[:64]]}
