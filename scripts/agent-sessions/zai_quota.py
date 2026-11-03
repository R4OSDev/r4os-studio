"""Original Z.AI subscription observations; inference usage remains separate."""
import datetime
import json
import math
import uuid
from api_catalog import Catalogs, has
from session_store import identity, encode, now
from store import ProjectFault
from zai_policy import require

ERRORS = {'auth':'Z.AI rejected the subscription monitoring credential.',
          'service':'Z.AI subscription limits are temporarily unavailable.',
          'format':'Z.AI returned an unsupported subscription limit response.',
          'timeout':'The Z.AI limit check timed out.', 'cancelled':'The original Z.AI limit check was cancelled.'}


def number(value):
    return value if type(value) in (int,float) and math.isfinite(value) and 0<=value<=9007199254740991 else None


def label(value):
    return value if isinstance(value,str) and 0<len(value)<=80 and not any(ord(c)<32 or ord(c)==127 for c in value) else None


def normalize(body):
    if (not isinstance(body,dict) or body.get('success') is False or body.get('code') not in (None,200,'200')
            or not isinstance(body.get('data'),dict) or not isinstance(body['data'].get('limits'),list)
            or len(body['data']['limits'])>32):raise ValueError('format')
    data=body['data'];rows=[]
    for index,item in enumerate(data['limits']):
        if not isinstance(item,dict):raise ValueError('format')
        typ=label(item.get('type')) or 'UNKNOWN'
        unit=item.get('unit');count=number(item.get('number'))
        # Keep the native codes too; only the observed, documented windows get
        # a human label. Never infer a reset from our local observation time.
        window='5-hour' if unit==3 and count==5 else 'Weekly' if unit==6 and count==1 else 'Provider window'
        maximum=number(item.get('usage'));used=number(item.get('currentValue'))
        remaining=number(item.get('remaining'))
        if remaining is None and maximum is not None and used is not None:remaining=max(0,maximum-used)
        reset=item.get('nextResetTime');reset_at=None
        if number(reset) is not None:
            try:reset_at=datetime.datetime.fromtimestamp(reset/1000,datetime.timezone.utc).isoformat()
            except (ValueError,OverflowError,OSError):pass
        rows.append({'id':str(index),'type':typ,'unit':'credits' if typ=='CREDIT_LIMIT' else 'tokens' if typ=='TOKENS_LIMIT' else 'requests' if typ=='TIME_LIMIT' else 'unknown',
            'window':window,'nativeUnit':unit if type(unit) in (int,str) else None,'nativeCount':count,
            'maximum':maximum,'used':used,'remaining':remaining,'percentage':number(item.get('percentage')),'resetAt':reset_at})
    return {'level':label(data.get('level')),'limits':rows}


def scope(db,binding,create=False):
    if not has(db,'zai_quota_accounts'):return None
    old=db.execute('SELECT scope_id FROM zai_quota_accounts WHERE provider_id=? AND credential_revision=?',
                   (binding['id'],binding['credentialRevision'])).fetchone()
    if old:return old[0]
    if not create:return None
    secret=db.execute('SELECT value FROM secrets.credentials WHERE provider_id=? AND revision=?',
                      (binding['id'],binding['credentialRevision'])).fetchone()
    if secret is None:raise ProjectFault('The original subscription credential revision is unavailable.',409)
    same=db.execute('''SELECT a.scope_id FROM zai_quota_accounts a JOIN secrets.credentials c
        ON c.provider_id=a.provider_id AND c.revision=a.credential_revision WHERE c.value=? LIMIT 1''',(secret[0],)).fetchone()
    ident=same[0] if same else str(uuid.uuid4())
    db.execute('INSERT INTO zai_quota_accounts VALUES (?,?,?)',(binding['id'],binding['credentialRevision'],ident))
    return ident


class Quota(Catalogs):
    def schema(self,db):
        super().schema(db)
        db.execute('CREATE TABLE IF NOT EXISTS zai_quota_accounts(provider_id TEXT NOT NULL,credential_revision INTEGER NOT NULL,scope_id TEXT NOT NULL,PRIMARY KEY(provider_id,credential_revision))')
        db.execute('CREATE TABLE IF NOT EXISTS zai_quota(provider_id TEXT PRIMARY KEY,config_revision INTEGER NOT NULL,credential_revision INTEGER NOT NULL,scope_id TEXT,checked_at TEXT,data TEXT,error TEXT)')

    def receipt(self,ident,rid):
        with self.api.connect() as db:
            row=self.request(db,ident,rid)
            if row['operation']!='quota_refresh':raise ProjectFault('This original request is not a subscription check.',409)
            return json.loads(row['result']) if row['result'] else {'requestId':rid,'providerId':ident,'state':'pending'}

    def listing(self,ident):
        with self.api.connect() as db:
            provider=self.api.current(db,ident);require(provider)
            row=db.execute('SELECT * FROM zai_quota WHERE provider_id=?',(ident,)).fetchone() if has(db,'zai_quota') else None
            exact=row and row['config_revision']==provider['revision'] and row['credential_revision']==provider['credentialRevision']
            value=json.loads(row['data']) if exact and row['data'] else {'level':None,'limits':[]}
            current=False
            if exact and row['checked_at'] and not row['error']:
                try:current=0<=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(row['checked_at'])).total_seconds()<90
                except ValueError:pass
            return {'providerId':ident,'configRevision':provider['revision'],'credentialRevision':provider['credentialRevision'],
                'state':'current' if current else 'stale' if exact and row['data'] else 'unknown',
                'scopeId':row['scope_id'] if exact else None,'checkedAt':row['checked_at'] if exact else None,
                'error':ERRORS.get(row['error'],ERRORS['service']) if exact and row['error'] else None,**value}

    def start_refresh(self,ident,data,allowed=True):
        self.api.get(ident)
        with self.api.connect(write=True) as db:
            self.schema(db);rid,fingerprint,old=self.original(db,ident,data,'quota_refresh')
            if old:return old,False
            provider=self.api.current(db,ident);require(provider)
            if (not isinstance(data,dict) or set(data)!={'requestId','providerRevision'}
                    or type(data['providerRevision']) is not int or data['providerRevision']!=provider['revision']):
                raise ProjectFault('Subscription settings changed. Reload before checking limits.',409)
            if not allowed:raise ProjectFault('Subscription checks are busy. No new request was sent.',429)
            if not provider['enabled']:raise ProjectFault('Connect your Z.AI subscription before checking limits.',409)
            if db.execute("SELECT 1 FROM catalog_requests WHERE provider_id=? AND phase!='complete'",(ident,)).fetchone():
                raise ProjectFault('Read the original provider check before starting another.',409)
            binding={k:provider[k] for k in ('id','kind','baseUrl','protocol','auth','revision','credentialRevision')}
            db.execute("INSERT INTO catalog_requests VALUES (?,?,?,?,?,'reserved',0,NULL,NULL,?)",(rid,ident,'quota_refresh',fingerprint,encode(binding),now()))
            return {'requestId':rid,'providerId':ident,'state':'pending'},True

    def finish(self,ident,rid,body=None,error=None,child=None):
        with self.api.connect(write=True) as db:
            self.schema(db);row=self.request(db,ident,rid)
            if row['phase']=='complete':return json.loads(row['result'])
            if row['operation']!='quota_refresh':raise ProjectFault('This original request is not a subscription check.',409)
            if row['held'] and (not child or json.loads(row['child'] or 'null')!=child or self.alive(child)):
                raise ProjectFault('The original subscription transport has not closed. Its credential was preserved.',503)
            provider=self.api.current(db,ident,retired=True);binding=json.loads(row['binding'])
            if not error and (not provider['enabled'] or any(provider[k]!=v for k,v in binding.items())):error='cancelled'
            value=None;observed=None
            if not error:
                secret=db.execute('SELECT value FROM secrets.credentials WHERE provider_id=? AND revision=?',
                                  (ident,binding['credentialRevision'])).fetchone()
                try:
                    raw=encode(body)
                    if len(raw.encode())>262144 or secret and secret[0] in raw:raise ValueError()
                    value=normalize(body);observed=now()
                except (ValueError,TypeError,UnicodeError):error='format'
            previous=db.execute('SELECT * FROM zai_quota WHERE provider_id=?',(ident,)).fetchone()
            if error and previous and previous['config_revision']==binding['revision'] and previous['credential_revision']==binding['credentialRevision']:
                value=json.loads(previous['data']) if previous['data'] else None;observed=previous['checked_at']
            account=scope(db,binding,create=True) if row['held'] else scope(db,binding)
            if not error:
                from zai_limits import refresh
                refresh(db,binding,value,observed)
            db.execute('INSERT INTO zai_quota VALUES (?,?,?,?,?,?,?) ON CONFLICT(provider_id) DO UPDATE SET config_revision=excluded.config_revision,credential_revision=excluded.credential_revision,scope_id=excluded.scope_id,checked_at=excluded.checked_at,data=excluded.data,error=excluded.error',
                (ident,binding['revision'],binding['credentialRevision'],account,observed,encode(value) if value is not None else None,error))
            # Original native response remains private in this completed request,
            # independently of the current cached projection and run statistics.
            original={**binding,'quotaOriginal':body if not error else None,'quotaObservedAt':observed}
            result={'requestId':rid,'providerId':ident,'state':'failed' if error else 'complete'}
            if error:result['error']=ERRORS.get(error,ERRORS['service'])
            db.execute("UPDATE catalog_requests SET phase='complete',held=0,binding=?,result=? WHERE id=?",(encode(original),encode(result),rid))
            self.api.cleanup(db,provider)
            return result
