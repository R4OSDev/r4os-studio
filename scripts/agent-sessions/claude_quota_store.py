"""Durable account-scoped holds; clocks and metadata reads never resume work."""
import json
import uuid

from claude_auth_store import AuthStore
from claude_provider_store import account_identity
from session_store import encode,identity,now
from store import ProjectFault


class QuotaStore(AuthStore):
    def table(self,db,write=False):
        if db is None:return False
        if write:db.execute('CREATE TABLE IF NOT EXISTS claude_quota_accounts(account_id TEXT PRIMARY KEY,data TEXT NOT NULL)')
        return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='claude_quota_accounts'").fetchone() is not None

    def read(self,provider_id):
        with self.auth_db() as db:
            provider=self.current(db,provider_id);key=account_identity(provider['account'])
            row=db.execute('SELECT data FROM claude_quota_accounts WHERE account_id=?',(key,)).fetchone() if key and self.table(db) else None
            return json.loads(row[0]) if row else None

    def record(self,provider_id,sample=None,observation=None,denial=None):
        with self.auth_db(write=True) as db:
            provider=self.current(db,provider_id);key=account_identity(provider['account'])
            if not key:raise ProjectFault('The original native quota account is unavailable.',409)
            self.table(db,True)
            row=db.execute('SELECT data FROM claude_quota_accounts WHERE account_id=?',(key,)).fetchone()
            saved=json.loads(row[0]) if row else {'schema':1,'accountIdentity':key,'sample':None,'observation':None,'hold':None}
            if sample:
                if sample.get('accountIdentity')!=key or sample.get('providerId')!=provider_id or sample.get('providerRevision')!=provider['revision']:
                    raise ProjectFault('The original native quota sample binding changed.',409)
                saved['sample']=sample
            if observation:
                if observation.get('accountIdentity')!=key or observation.get('providerId')!=provider_id:
                    raise ProjectFault('The original native quota event binding changed.',409)
                saved['observation']=observation
            cause=denial if denial and denial.get('reasonCode') in ('subscription_limit','overage_unconfirmed') else None
            if observation and (observation.get('status')=='rejected' or observation.get('usingOverage') is True or observation.get('overageEnabled') is True):
                cause={'reasonCode':'subscription_limit' if observation.get('status')=='rejected' else 'overage_unconfirmed',
                    'reason':'The native subscription reported a limit or paid-extra-usage state. Resume explicitly after a fresh check.'}
            if cause:
                saved['hold']={'id':str(uuid.uuid4()),'createdAt':now(),'reasonCode':cause['reasonCode'],'reason':cause['reason'],
                    'providerId':provider_id,'sourceRequestId':sample.get('requestId') if sample else (observation or {}).get('runId')}
            db.execute('INSERT INTO claude_quota_accounts VALUES (?,?) ON CONFLICT(account_id) DO UPDATE SET data=excluded.data',
                (key,encode(saved)))
            return saved

    def release(self,provider_id,expected_hold,request_id):
        identity(request_id)
        with self.auth_db(write=True) as db:
            provider=self.current(db,provider_id);key=account_identity(provider['account'])
            if not key or not self.table(db):raise ProjectFault('The original native quota hold is unavailable.',409)
            row=db.execute('SELECT data FROM claude_quota_accounts WHERE account_id=?',(key,)).fetchone()
            saved=json.loads(row[0]) if row else None
            if not saved or saved['hold']!=expected_hold:raise ProjectFault('The original native quota hold changed. It was not resumed.',409)
            saved['lastReleasedHold']=saved['hold']
            saved['hold']=None;saved['lastExplicitResume']={'requestId':request_id,'providerId':provider_id,'at':now()}
            db.execute('UPDATE claude_quota_accounts SET data=? WHERE account_id=?',(encode(saved),key))
            return saved
