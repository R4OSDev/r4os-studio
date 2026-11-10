"""Global context budget, frozen only for newly accepted Studio runs."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
import os
import sqlite3
from system_prompt import location
from session_store import encode, identity
from store import ProjectFault

DEFAULT = 250000
MAXIMUM = 10000000
OPTIMIZATION = 3


def optimized(policy, version):
    value = (policy or {}).get('optimization')
    return type(value) is int and version <= value <= OPTIMIZATION

def budget(value):
    if type(value) is not int or not 1 <= value <= MAXIMUM:
        raise ProjectFault('budgetTokens must be a whole number from 1 to 10000000.',400)
    return value

def current(db):
    empty={'revision':0,'enabled':True,'budgetTokens':DEFAULT,'defaultEnabled':True,'defaultBudgetTokens':DEFAULT,'maxBudgetTokens':MAXIMUM}
    if db is None:return empty
    version=db.execute('PRAGMA user_version').fetchone()[0]
    if version==0 and not db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():return empty
    if version!=1:raise ProjectFault('Context settings storage is unavailable.',503)
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='global_context' AND type='table'").fetchone():return empty
    columns={v[1] for v in db.execute('PRAGMA table_info(global_context)')}
    row=db.execute('SELECT revision,budget_tokens'+(',enabled' if 'enabled' in columns else ',1')+' FROM global_context WHERE id=1').fetchone()
    if row is None:return empty
    if type(row[0]) is not int or not 1<=row[0]<2**53:raise ProjectFault('Context settings revision is unavailable.',503)
    if type(row[2]) is not int or row[2] not in (0,1):raise ProjectFault('Context limit activation is unavailable.',503)
    return {**empty,'revision':row[0],'budgetTokens':budget(row[1]),'enabled':bool(row[2])}

def read(projects):
    path=location(projects)
    if not path.exists():return current(None)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:return current(db)

def receipt(projects,rid):
    rid=identity(rid);path=location(projects)
    if path.exists():
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='context_requests' AND type='table'").fetchone():
                row=db.execute('SELECT result FROM context_requests WHERE id=?',(rid,)).fetchone()
                if row:return json.loads(row[0])
    raise ProjectFault('Original context settings request not found.',404)

def update(projects,data):
    if (not isinstance(data,dict) or data.get('action') not in ('save','reset')
        or set(data)-{'enabled'}!=({'requestId','revision','action','budgetTokens'} if data.get('action')=='save' else {'requestId','revision','action'})
        or 'enabled' in data and (data.get('action')!='save' or type(data['enabled']) is not bool)
        or type(data['revision']) is not int or not 0<=data['revision']<2**53-1):
        raise ProjectFault('Context settings require requestId, revision, action and budgetTokens for save.',400)
    rid=identity(data['requestId']);chosen=budget(data['budgetTokens']) if data['action']=='save' else DEFAULT
    fingerprint=hashlib.sha256(encode(data).encode()).hexdigest()
    path=location(projects,create=True)
    with closing(sqlite3.connect(path,timeout=5)) as db:
        os.chmod(path,0o600);db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
        version=db.execute('PRAGMA user_version').fetchone()[0]
        if version==0:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():raise ProjectFault('Unrecognized global settings.',503)
            db.execute('CREATE TABLE system_prompt(id INTEGER PRIMARY KEY CHECK(id=1),prompt TEXT,revision INTEGER NOT NULL)');db.execute('PRAGMA user_version=1')
        elif version!=1 or not db.execute("SELECT 1 FROM sqlite_master WHERE name='system_prompt' AND type='table'").fetchone():
            raise ProjectFault('Unsupported global settings.',503)
        db.execute('CREATE TABLE IF NOT EXISTS global_context(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,budget_tokens INTEGER NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS context_requests(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,result TEXT NOT NULL)')
        old=db.execute('SELECT fingerprint,result FROM context_requests WHERE id=?',(rid,)).fetchone()
        if old:
            if old[0]!=fingerprint:raise ProjectFault('This requestId belongs to different context settings.',409)
            return json.loads(old[1])
        value=current(db)
        if data['revision']!=value['revision']:raise ProjectFault('Context settings changed. Your draft was retained; reload before saving.',409)
        enabled=data.get('enabled',value['enabled']) if data['action']=='save' else True
        if 'enabled' not in {v[1] for v in db.execute('PRAGMA table_info(global_context)')}:
            db.execute('ALTER TABLE global_context ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))')
        revision=value['revision']+int(chosen!=value['budgetTokens'] or enabled!=value['enabled'] or value['revision']==0)
        result={**value,'revision':revision,'budgetTokens':chosen,'enabled':enabled,'requestId':rid}
        db.execute('INSERT INTO global_context(id,revision,budget_tokens,enabled) VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,budget_tokens=excluded.budget_tokens,enabled=excluded.enabled',(revision,chosen,int(enabled)))
        db.execute('INSERT INTO context_requests VALUES(?,?,?)',(rid,fingerprint,encode(result)));db.commit();return result

def preference(value=None):
    if value is None:return {'mode':'global','budgetTokens':None}
    if (not isinstance(value,dict) or set(value)!={'mode','budgetTokens'}
            or value['mode'] not in ('off','global','on')):
        raise ProjectFault('Context limit requires mode off, global or on and an optional budgetTokens value.',400)
    return {'mode':value['mode'],'budgetTokens':None if value['budgetTokens'] is None else budget(value['budgetTokens'])}

def resolve(value,session=None):
    chosen=preference((session or {}).get('contextLimit'))
    enabled=chosen['mode']=='on' or chosen['mode']=='global' and value['enabled']
    from input_tokenizer import PROFILE
    return {'schema':4,'counting':PROFILE.copy(),'revision':value['revision'],'enabled':enabled,
        'budgetTokens':chosen['budgetTokens'] if chosen['budgetTokens'] is not None else value['budgetTokens'],
        'globalEnabled':value['enabled'],'globalBudgetTokens':value['budgetTokens'],
        'sessionMode':chosen['mode'],'sessionBudgetTokens':chosen['budgetTokens']}

def freeze(snapshot,projects,original,session=None):
    if original is not None:
        if 'contextPolicy' in original:snapshot['contextPolicy']=deepcopy(original['contextPolicy'])
        return
    snapshot['contextPolicy']=resolve(read(projects),session)
    from provider_count import supported,CONTRACT
    provider=snapshot.get('apiProvider',{})
    snapshot['contextPolicy']['providerCount']={'version':1,'enabled':provider.get('inputTokenCounting') is True and supported(provider),'contract':CONTRACT}
    if snapshot['engine'].get('kind')=='studio':
        snapshot['contextPolicy']['optimization']=OPTIMIZATION
    if snapshot['engine'].get('kind')!='studio' and snapshot['contextPolicy']['enabled']:
        raise ProjectFault('This native connection cannot check the complete provider input against a Studio limit. Review an explicit conversation conversion, or switch the session limit Off. Original history was preserved; no model request was started.',409)

def threshold(config,capacity):
    model_limit=int(capacity*0.8) if capacity is not None else None
    value=config.get('contextPolicy')
    if value is None:return model_limit  # Older accepted configs retain their policy.
    from input_budget import strict,limit
    if strict(value):return limit(value,{**config.get('apiProvider',{}),**config.get('apiModel',{}),'contextWindow':capacity})
    if value.get('enabled',True) is False:return model_limit
    limit=budget(value.get('budgetTokens'))
    return min(limit,model_limit) if model_limit is not None else limit


def compaction_limits(config, capacity):
    maximum = threshold(config, capacity)
    if maximum is None or not optimized(config.get('contextPolicy'), 2):
        return maximum, maximum
    trigger = maximum - min(2048, maximum // 20)
    return trigger, trigger - min(4096, trigger // 10)
