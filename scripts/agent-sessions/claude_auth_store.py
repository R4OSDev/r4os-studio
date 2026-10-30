"""Original native-auth receipts, containing no URL, code or credential bytes."""
from contextlib import contextmanager
import hashlib
import json
import re

from claude_provider_store import ClaudeProviders,valid_account,account_identity
from session_store import identity,encode,now
from store import ProjectFault

ACTIVE=('pending','waiting')


def needs_status(result):
    return (result['state']=='unconfirmed' or result['state'] in ('cancelled','expired')
        and result['action'] in ('connect','disconnect','remove')) and not result.get('reconciledBy')


def browser_owner(value):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):
        raise ProjectFault('Reload provider settings before continuing.',403)
    return hashlib.sha256(value.encode()).hexdigest()


class AuthStore(ClaudeProviders):
    @contextmanager
    def auth_db(self,write=False):
        with self.connect(write=write) as db:
            if db is not None:
                if write:db.execute('CREATE TABLE IF NOT EXISTS auth_requests(id TEXT PRIMARY KEY,provider_id TEXT NOT NULL,owner TEXT NOT NULL,fingerprint TEXT NOT NULL,data TEXT NOT NULL)')
                elif not db.execute("SELECT 1 FROM sqlite_master WHERE name='auth_requests' AND type='table'").fetchone():db=None
            yield db

    def operation(self,ident,rid,owner):
        ident=identity(ident);rid=identity(rid);owner=browser_owner(owner)
        with self.auth_db() as db:
            row=db.execute('SELECT * FROM auth_requests WHERE id=? AND provider_id=? AND owner=?',(rid,ident,owner)).fetchone() if db else None
            if not row:raise ProjectFault('Original Claude sign-in request not found in this browser session.',404)
            result=json.loads(row['data'])
            if self.removed(db,ident) and result['state']!='removed':
                raise ProjectFault('This Claude provider was removed. No original sign-in was repeated.',410)
            return result

    def begin(self,ident,data,owner,allow_new=True):
        ident=identity(ident);owner=browser_owner(owner)
        removing=isinstance(data,dict) and data.get('action')=='remove'
        fields={'requestId','revision','action'}|({'confirmName'} if removing else set())
        if not isinstance(data,dict) or set(data)!=fields or data['action'] not in ('connect','status','disconnect','limits','catalog','remove'):
            raise ProjectFault('Invalid native Claude authentication request.',400)
        rid=identity(data['requestId'])
        if type(data['revision']) is not int or not 1<=data['revision']<=9007199254740991:
            raise ProjectFault('Reload the Claude provider before continuing.',400)
        fingerprint=hashlib.sha256(encode({'id':ident,'owner':owner,'input':data}).encode()).hexdigest()
        with self.auth_db(write=True) as db:
            row=db.execute('SELECT * FROM auth_requests WHERE id=?',(rid,)).fetchone()
            if row:
                if row['fingerprint']!=fingerprint:raise ProjectFault('This original Claude request has different input or browser ownership.',409)
                result=json.loads(row['data'])
                if self.removed(db,ident) and result['state']!='removed':
                    raise ProjectFault('This Claude provider was removed. No original sign-in was repeated.',410)
                return result,False
            value=self.current(db,ident)
            if value['revision']!=data['revision']:raise ProjectFault('The Claude provider changed. Reload before continuing.',409)
            if removing and (data['confirmName']!=value['name'] or value['status']!='not-connected'):
                raise ProjectFault('Disconnect the Claude provider and confirm its exact display name before removing it.',409)
            if (db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='claude_run_leases'").fetchone()
                and db.execute("SELECT 1 FROM claude_run_leases WHERE provider_id=? AND state!='released' LIMIT 1",(ident,)).fetchone()):
                raise ProjectFault('Original Claude worker/queue credential leases are still active or unconfirmed. No authentication change was started.',409)
            for row in db.execute('SELECT data FROM auth_requests WHERE provider_id=?',(ident,)):
                previous=json.loads(row[0])
                if previous['state'] in ACTIVE or needs_status(previous) and data['action'] not in ('status','limits','catalog'):
                    raise ProjectFault('Read the original Claude request, then explicitly check status before signing in again.',409)
            if db.execute('SELECT count(*) FROM auth_requests').fetchone()[0]>=10000:
                raise ProjectFault('The private Claude authentication receipt limit was reached.',409)
            if not allow_new:raise ProjectFault('The native Claude authentication capacity is busy.',429)
            result={'requestId':rid,'providerId':ident,'action':data['action'],'revision':data['revision'],
                'state':'pending','message':None,'createdAt':now(),'updatedAt':now(),'provider':value}
            db.execute('INSERT INTO auth_requests VALUES (?,?,?,?,?)',(rid,ident,owner,fingerprint,encode(result)))
            return result,True

    def finish_removed(self,ident,rid):
        """Retire only the original pending operation after native logout evidence."""
        with self.auth_db(write=True) as db:
            row=db.execute('SELECT * FROM auth_requests WHERE id=? AND provider_id=?',(rid,ident)).fetchone()
            if not row:raise ProjectFault('The original Claude removal receipt is unavailable.',503)
            result=json.loads(row['data'])
            if result['state'] not in ACTIVE:return result
            value=self.current(db,ident)
            if result['action']!='remove' or value['revision']!=result['revision'] or value['status']!='not-connected':
                raise ProjectFault('The original Claude removal binding changed. Existing data was preserved.',409)
            if (db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='claude_run_leases'").fetchone()
                and db.execute("SELECT 1 FROM claude_run_leases WHERE provider_id=? AND state!='released' LIMIT 1",(ident,)).fetchone()):
                raise ProjectFault('Original Claude credential leases must be reconciled before removal.',409)
            value={**value,'revision':value['revision']+1,'updatedAt':now()}
            result.update(state='removed',provider=value,updatedAt=now(),
                message='Claude provider removed. Existing conversations and original receipts were preserved.')
            db.execute('CREATE TABLE IF NOT EXISTS removed_providers(id TEXT PRIMARY KEY,data TEXT NOT NULL)')
            db.execute('INSERT INTO removed_providers VALUES (?,?)',(ident,encode(result)))
            db.execute('INSERT INTO revisions VALUES (?,?,?)',(ident,value['revision'],encode(value)))
            db.execute('DELETE FROM providers WHERE id=?',(ident,))
            db.execute('UPDATE auth_requests SET data=? WHERE id=?',(encode(result),rid))
            return result

    def finish(self,ident,rid,state,message=None,status=None,account=None,usage=None,models=None):
        with self.auth_db(write=True) as db:
            row=db.execute('SELECT * FROM auth_requests WHERE id=? AND provider_id=?',(rid,ident)).fetchone()
            if not row:raise ProjectFault('The original Claude authentication receipt is unavailable.',503)
            result=json.loads(row['data'])
            if result['state'] not in ACTIVE:return result
            value=self.current(db,ident)
            if status is not None:
                if value['revision']!=result['revision'] or not valid_account(account,status):
                    raise ProjectFault('The original Claude authentication binding changed. Read status before continuing.',409)
                value={**value,'revision':value['revision']+1,'updatedAt':now(),'status':status,
                    'auth':{'kind':'native-plan','state':status},'account':account}
            result.update(state=state,message=message,updatedAt=now(),provider=value)
            if result['action'] in ('limits','catalog') and state=='complete':
                from claude_limits_policy import usage_sample
                result['limits']=usage_sample(usage,value,rid)
            if result['action']=='catalog' and state=='complete':
                from claude_catalog import normalize
                try:result['catalog']=normalize(models,value,rid)
                except ProjectFault:result['catalog']=None;result['message']='The native model catalog is unavailable. Existing selections were preserved.'
            if status is not None:
                db.execute('UPDATE providers SET data=? WHERE id=?',(encode(value),ident))
                db.execute('INSERT INTO revisions VALUES (?,?,?)',(ident,value['revision'],encode(value)))
            db.execute('UPDATE auth_requests SET data=? WHERE id=?',(encode(result),rid))
            if result['action'] in ('status','limits','catalog') and state=='complete':
                for old in db.execute('SELECT id,data FROM auth_requests WHERE provider_id=?',(ident,)).fetchall():
                    data=json.loads(old['data'])
                    if needs_status(data):
                        if data['state']=='unconfirmed':data['state']='reconciled'
                        data.update(reconciledBy=rid,message='Native status was checked after the original interrupted operation. No sign-in was repeated.',updatedAt=now())
                        db.execute('UPDATE auth_requests SET data=? WHERE id=?',(encode(data),old['id']))
            return result

    def latest_limits(self,ident):
        from claude_provider_store import account_identity
        provider=self.get(ident);account=account_identity(provider['account'])
        if not account:return None
        with self.auth_db() as db:
            if db is None:return None
            rows=db.execute('SELECT data FROM auth_requests WHERE provider_id=? ORDER BY rowid DESC',(ident,))
            for row in rows:
                sample=json.loads(row[0]).get('limits')
                if sample and sample['accountIdentity']==account:return sample
            return None

    def latest_catalog(self,ident):
        from claude_provider_store import account_identity
        provider=self.get(ident);account=account_identity(provider['account'])
        if not account:return None
        with self.auth_db() as db:
            if db is None:return None
            for row in db.execute('SELECT data FROM auth_requests WHERE provider_id=? ORDER BY rowid DESC',(ident,)):
                result=json.loads(row[0]);catalog=result.get('catalog')
                if (result.get('action')=='catalog' and result.get('state')=='complete'
                    and account_identity(result.get('provider',{}).get('account'))==account):
                    return catalog if (catalog and catalog.get('accountIdentity')==account
                        and catalog.get('runtimeProfileId')==provider['runtimeProfileId']) else None
            return None

    def recover(self):
        with self.auth_db() as db:
            pending=[] if db is None else [(r['provider_id'],r['id']) for r in db.execute('SELECT * FROM auth_requests') if json.loads(r['data'])['state'] in ACTIVE]
        for ident,rid in pending:self.finish(ident,rid,'unconfirmed','The original native process was interrupted. Explicitly check status; no sign-in was restarted.')
