"""Only original Z.AI evidence can hold its proven subscription scope."""
import datetime
import json
import os
from api_provider_store import ApiProviders
from api_catalog import has
from session_store import encode,now
from zai_quota import Quota,scope
from store import ProjectFault

REASONS={
 '1308':'The Z.AI subscription usage window is exhausted. Check its actual limits before continuing.',
 '1310':'The Z.AI weekly or monthly subscription allowance is exhausted. Check its actual reset.',
 '1309':'The Z.AI subscription has expired. Renew it and recheck access.',
 '1314':'The Z.AI team subscription has expired. Review it with your account administrator.',
 '1311':'This Z.AI subscription cannot access the selected model. Review its model access.',
 '1313':'Z.AI has restricted this subscription. Review its account status.',
 '1315':'This Z.AI key belongs to a different subscription product.',
 '1316':'The Z.AI 5-hour allowance is exhausted; extra usage is unavailable.',
 '1317':'The Z.AI weekly allowance is exhausted; extra usage is unavailable.',
 '1318':'The Z.AI 5-hour allowance is exhausted; paid extra usage is not available.',
 '1319':'The Z.AI weekly allowance is exhausted; paid extra usage is not available.',
 '1320':'The Z.AI 5-hour allowance is exhausted; paid extra usage is not available.',
 '1321':'The Z.AI weekly allowance is exhausted; paid extra usage is not available.',
}


def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS zai_holds(scope_id TEXT NOT NULL,hold_key TEXT NOT NULL,model TEXT NOT NULL,reason TEXT NOT NULL,reset_at TEXT,observed_at TEXT NOT NULL,PRIMARY KEY(scope_id,hold_key,model))')
    db.execute('CREATE TABLE IF NOT EXISTS zai_native_limits(run_id TEXT NOT NULL,ordinal INTEGER NOT NULL,provider_id TEXT NOT NULL,code TEXT NOT NULL,model TEXT NOT NULL,reset_at TEXT,http_status INTEGER,observed_at TEXT NOT NULL,PRIMARY KEY(run_id,ordinal))')


def expired(value):
    if value is None:return False
    try:return datetime.datetime.fromisoformat(value)<=datetime.datetime.now(datetime.timezone.utc)
    except (TypeError,ValueError):return False


def hold(db,account,model):
    if not account or not has(db,'zai_holds'):return None
    for row in db.execute('SELECT * FROM zai_holds WHERE scope_id=? AND (model=\'\' OR model=?) ORDER BY observed_at DESC',(account,model)):
        if not expired(row['reset_at']):return {'reason':row['reason'],'resetAt':row['reset_at'],'observedAt':row['observed_at']}
    return None


def require_admission(db,binding,model):
    Quota('.').schema(db);schema(db)
    account=scope(db,binding,True)
    blocked=hold(db,account,model)
    if blocked:raise ProjectFault(blocked['reason'],429)


def refresh(db,binding,value,observed):
    schema(db);account=scope(db,binding,True)
    # Only a fresh successful check updates quota evidence. Unknown monitoring
    # cannot remove a native hold or invent zero remaining capacity.
    relevant=[w for w in value['limits'] if w['type'] in ('CREDIT_LIMIT','TOKENS_LIMIT') and w['window'] in ('5-hour','Weekly')]
    for window in relevant:
        if window['remaining'] is None:continue
        key='quota:'+str(window['nativeUnit'])+':'+str(window['nativeCount'])+':'+window['type']
        db.execute('DELETE FROM zai_holds WHERE scope_id=? AND hold_key=?',(account,key))
        if window['remaining']==0:
            db.execute('INSERT OR REPLACE INTO zai_holds VALUES (?,?,?,?,?,?)',(account,key,'',
                'The Z.AI '+window['window']+' subscription allowance is exhausted. Check its actual reset.',window['resetAt'],observed))
    if {w['window'] for w in relevant}=={'5-hour','Weekly'} and all(w['remaining'] is not None and w['remaining']>0 for w in relevant):
        # This permits an explicit new attempt, not a claim of model entitlement
        # or an instruction to start/continue a session or Goal.
        db.execute("DELETE FROM zai_holds WHERE scope_id=? AND hold_key LIKE 'native:%'",(account,))


def observe(providers,binding,model,run_id,value):
    code=value['code'];api=ApiProviders(providers)
    with api.connect(write=True) as db:
        Quota(providers).schema(db);schema(db)
        lease=db.execute('SELECT * FROM leases WHERE run_id=?',(run_id,)).fetchone()
        if (not lease or lease['state']!='active' or lease['provider_id']!=binding['id']
                or lease['config_revision']!=binding['revision'] or lease['credential_revision']!=binding['credentialRevision']
                or json.loads(lease['binding']).get('worker',{}).get('pid')!=os.getpid()):
            raise ProjectFault('The original Z.AI limit observation has no active worker binding.',409)
        account=scope(db,binding,True);stamp=now()
        original=db.execute('SELECT * FROM zai_native_limits WHERE run_id=? AND ordinal=?',(run_id,value['ordinal'])).fetchone()
        if original:
            if original['code']!=code or original['model']!=model:raise ProjectFault('Conflicting original Z.AI limit evidence was preserved.',409)
            return
        db.execute('INSERT INTO zai_native_limits VALUES (?,?,?,?,?,?,?,?)',(run_id,value['ordinal'],binding['id'],code,model,value['resetAt'],value['httpStatus'],stamp))
        if code in REASONS:
            selected=model if code=='1311' else ''
            db.execute('INSERT OR REPLACE INTO zai_holds VALUES (?,?,?,?,?,?)',(account,'native:'+code,selected,REASONS[code],value['resetAt'],stamp))


def state(providers,binding,model):
    api=ApiProviders(providers)
    with api.connect() as db:return hold(db,scope(db,binding),model)
