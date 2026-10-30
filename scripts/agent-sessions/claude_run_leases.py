"""Original Claude credential leases; auth changes cannot race bound workers."""
from contextlib import contextmanager
import json

from claude_auth_store import AuthStore,ACTIVE
from claude_provider_store import account_identity
from session_store import identity,encode,now
from store import ProjectFault


def validate(value):
    fields={'providerId','providerRevision','studioSessionId','ownerType','ownerId','runId','requestId','nativeSessionId','runtimeProfileId','accountIdentity'}
    if (not isinstance(value,dict) or set(value)!=fields or type(value['providerRevision']) is not int or value['providerRevision']<1
        or value['ownerType'] not in ('project','skill') or not isinstance(value['runtimeProfileId'],str)
        or not isinstance(value['accountIdentity'],str) or len(value['accountIdentity'])!=64):
        raise ProjectFault('Invalid original Claude credential lease.',400)
    for field in ('providerId','studioSessionId','ownerId','runId','requestId','nativeSessionId'):identity(value[field])
    return value


class ClaudeRunLeases(AuthStore):
    @contextmanager
    def leases(self,write=False):
        with self.auth_db(write) as db:
            if db is not None:
                if write:db.execute('CREATE TABLE IF NOT EXISTS claude_run_leases(run_id TEXT PRIMARY KEY,provider_id TEXT NOT NULL,binding TEXT NOT NULL,state TEXT NOT NULL,worker TEXT,updated_at TEXT NOT NULL)')
                elif not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='claude_run_leases'").fetchone():db=None
            yield db

    def reserve(self,value):
        value=validate(value)
        with self.leases(write=True) as db:
            old=db.execute('SELECT * FROM claude_run_leases WHERE run_id=?',(value['runId'],)).fetchone()
            if old:
                if json.loads(old['binding'])!=value:raise ProjectFault('The original Claude credential lease has different input.',409)
                return {'state':old['state'],'binding':value}
            provider=self.current(db,value['providerId'])
            if (provider['revision']!=value['providerRevision'] or provider['runtimeProfileId']!=value['runtimeProfileId']
                or account_identity(provider['account'])!=value['accountIdentity']
                or provider['status']!='connected' or provider['auth']['state']!='connected' or provider['account'] is None):
                raise ProjectFault('The original native Claude account/revision is unavailable. No model was started.',409)
            for row in db.execute('SELECT data FROM auth_requests WHERE provider_id=?',(value['providerId'],)):
                if json.loads(row[0])['state'] in (*ACTIVE,'unconfirmed'):
                    raise ProjectFault('An original native authentication operation must be reconciled before a worker starts.',409)
            db.execute('INSERT INTO claude_run_leases VALUES (?,?,?,\'reserved\',NULL,?)',
                (value['runId'],value['providerId'],encode(value),now()))
            return {'state':'reserved','binding':value}

    def claim(self,value,worker):
        value=validate(value)
        if (not isinstance(worker,dict) or set(worker)!={'release','pid','birth'} or not isinstance(worker['release'],str)
            or type(worker['pid']) is not int or worker['pid']<1 or not isinstance(worker['birth'],str)):
            raise ProjectFault('The original native worker identity is unavailable.',409)
        with self.leases(write=True) as db:
            row=db.execute('SELECT * FROM claude_run_leases WHERE run_id=?',(value['runId'],)).fetchone()
            provider=self.current(db,value['providerId'])
            if (not row or json.loads(row['binding'])!=value or row['state'] not in ('reserved','active')
                or row['worker'] is not None and json.loads(row['worker'])!=worker
                or provider['revision']!=value['providerRevision'] or provider['status']!='connected'
                or account_identity(provider['account'])!=value['accountIdentity']):
                raise ProjectFault('The original native Claude worker/credential binding changed. No model was started.',409)
            db.execute("UPDATE claude_run_leases SET state='active',worker=?,updated_at=? WHERE run_id=?",(encode(worker),now(),value['runId']))

    def current_lease(self,value,worker):
        value=validate(value)
        with self.leases() as db:
            row=db.execute('SELECT * FROM claude_run_leases WHERE run_id=?',(value['runId'],)).fetchone() if db else None
            if not row:return False
            provider=self.current(db,value['providerId'])
            return (row['state']=='active' and json.loads(row['binding'])==value and json.loads(row['worker'] or 'null')==worker
                and provider['revision']==value['providerRevision'] and provider['status']=='connected'
                and account_identity(provider['account'])==value['accountIdentity'])

    def finish_lease(self,value,worker,confirmed):
        value=validate(value)
        if type(confirmed) is not bool:raise ProjectFault('The original native process end must be confirmed.',409)
        with self.leases(write=True) as db:
            row=db.execute('SELECT * FROM claude_run_leases WHERE run_id=?',(value['runId'],)).fetchone()
            if (not row or json.loads(row['binding'])!=value or json.loads(row['worker'] or 'null')!=worker):
                raise ProjectFault('The original native credential lease cannot be released by another worker.',409)
            if row['state']=='released':return
            db.execute('UPDATE claude_run_leases SET state=?,updated_at=? WHERE run_id=?',('released' if confirmed else 'unknown',now(),value['runId']))
