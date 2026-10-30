"""Private API configuration and separate transactional secret storage.

Both SQLite files use DELETE journals on the same local filesystem. ATTACH plus
one transaction keeps config/secret revisions atomic. No API key enters public
records, request receipts, Run snapshots, argv or a native subscription home.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import uuid

from api_endpoint import endpoint
from session_store import identity, now, encode
from store import ProjectFault

FIELDS = ('id','type','kind','name','baseUrl','protocol','auth','revision','credentialRevision',
          'keyConfigured','enabled','status','createdAt','updatedAt','runtime')
KINDS = ('openrouter','openai-compatible','local')
PROTOCOLS = ('responses','chat-completions')


def private(path, directory=False, create=False):
    if create:
        if directory: path.mkdir(mode=0o700,exist_ok=True)
        else:
            try: os.close(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600))
            except FileExistsError: pass
    mode = 0o700 if directory else 0o600
    value=path.lstat()
    if (path.resolve(strict=True)!=path or value.st_uid!=os.geteuid() or value.st_gid!=os.getegid() or stat.S_IMODE(value.st_mode)!=mode
            or not (stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode) and value.st_nlink==1)):
        raise ProjectFault('The private API provider storage is unavailable. Existing data was preserved.',503)


def name(value):
    if (not isinstance(value,str) or not 1<=len(value.strip())<=80
            or any(ord(c)<32 or ord(c)==127 or 0xd800<=ord(c)<=0xdfff for c in value)):
        raise ProjectFault('Enter an API provider name of at most80 characters.',400)
    return value.strip()


def key(value):
    if not isinstance(value,str) or not 1<=len(value)<=8192 or any(not 33<=ord(c)<=126 for c in value):
        raise ProjectFault('Enter a valid bearer key without whitespace or control characters.',400)
    return value


class ApiProviders:
    def __init__(self,providers): self.parent=Path(providers).absolute(); self.root=self.parent/'ApiProviders'

    @contextmanager
    def connect(self,write=False):
        if not write and not self.root.exists() and not self.root.is_symlink(): yield None;return
        db=None
        try:
            private(self.parent,directory=True)
            private(self.root,directory=True,create=write)
            private(self.root/'Private',directory=True,create=write)
            catalog=self.root/'Providers.sqlite'; secrets=self.root/'Private/Secrets.sqlite'
            for path in (catalog,secrets):
                private(path,create=write)
                for suffix in ('-journal','-wal','-shm'):
                    sidecar=path.with_name(path.name+suffix)
                    if sidecar.exists() or sidecar.is_symlink():private(sidecar)
            if catalog.stat().st_dev!=secrets.stat().st_dev:
                raise ProjectFault('API configuration and secret storage must share one local filesystem.',503)
            db=sqlite3.connect(str(catalog) if write else catalog.as_uri()+'?mode=ro',uri=not write,timeout=5)
            db.row_factory=sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA temp_store=MEMORY')
            db.execute('ATTACH DATABASE ? AS secrets',(str(secrets) if write else secrets.as_uri()+'?mode=ro',))
            if write:
                db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA secrets.journal_mode=DELETE')
                db.execute('PRAGMA synchronous=FULL');db.execute('PRAGMA secrets.synchronous=FULL')
                db.execute('PRAGMA secrets.secure_delete=ON');db.execute('BEGIN IMMEDIATE')
            else: db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            for schema in ('main','secrets'):
                version=db.execute('PRAGMA '+schema+'.user_version').fetchone()[0]
                if version!=1:
                    if not write or version!=0 or db.execute('SELECT 1 FROM '+schema+'.sqlite_master WHERE type=\'table\'').fetchone():
                        raise ProjectFault('The API provider database is unsupported. Existing data was preserved.',503)
                    if schema=='main':
                        db.execute('CREATE TABLE providers(id TEXT PRIMARY KEY,data TEXT NOT NULL,retired INTEGER NOT NULL DEFAULT 0)')
                        db.execute('CREATE TABLE revisions(provider_id TEXT NOT NULL,revision INTEGER NOT NULL,data TEXT NOT NULL,PRIMARY KEY(provider_id,revision))')
                        db.execute('CREATE TABLE requests(id TEXT PRIMARY KEY,provider_id TEXT NOT NULL,operation TEXT NOT NULL,fingerprint TEXT NOT NULL,result TEXT,phase TEXT NOT NULL)')
                        db.execute('CREATE TABLE leases(run_id TEXT PRIMARY KEY,provider_id TEXT NOT NULL,config_revision INTEGER NOT NULL,credential_revision INTEGER NOT NULL,state TEXT NOT NULL,binding TEXT NOT NULL)')
                    else: db.execute('CREATE TABLE secrets.credentials(provider_id TEXT NOT NULL,revision INTEGER NOT NULL,value TEXT NOT NULL,PRIMARY KEY(provider_id,revision))')
                    db.execute('PRAGMA '+schema+'.user_version=1')
            yield db
            if write: db.commit()
        except ProjectFault: raise
        except (OSError,ValueError,TypeError,sqlite3.Error):
            raise ProjectFault('The private API provider storage could not confirm this operation. Read its original request before retrying.',503) from None
        finally:
            if db:
                if db.in_transaction:db.rollback()
                db.close()

    def current(self,db,ident,retired=False):
        ident=identity(ident)
        row=db.execute('SELECT data,retired FROM providers WHERE id=?',(ident,)).fetchone() if db else None
        if row is None: raise ProjectFault('API provider not found.',404)
        if row['retired'] and not retired: raise ProjectFault('This API provider was deleted.',410)
        value=json.loads(row['data'])
        if (not isinstance(value,dict) or set(value)-{'openrouter','server'}!=set(FIELDS) or value['id']!=ident or value['type']!='api'
                or value['kind'] not in KINDS or value['protocol'] not in PROTOCOLS or value['auth'] not in ('none','bearer')
                or type(value['revision']) is not int or value['revision']<1
                or type(value['credentialRevision']) is not int or value['credentialRevision']<0
                or type(value['keyConfigured']) is not bool or type(value['enabled']) is not bool
                or value['status'] not in ('configured','disconnected') or value['runtime']!='not-qualified'
                or not all(isinstance(value[k],str) for k in ('name','baseUrl','createdAt','updatedAt'))):
            raise ProjectFault('The API provider record is unavailable. Existing data was preserved.',503)
        try:
            if name(value['name'])!=value['name'] or endpoint(value['baseUrl'],value['kind'])['baseUrl']!=value['baseUrl']:
                raise ValueError()
        except (ProjectFault,ValueError):
            raise ProjectFault('The API provider record is unavailable. Existing data was preserved.',503) from None
        if value['kind']=='openrouter':
            if 'server' in value:raise ProjectFault('Server presets belong to a different provider kind.',503)
            from openrouter_policy import policy
            try:value['openrouter']=policy(value.get('openrouter'))
            except ProjectFault:raise ProjectFault('The original OpenRouter settings are unavailable. Existing data was preserved.',503) from None
        elif 'openrouter' in value:raise ProjectFault('OpenRouter settings belong to a different provider kind.',503)
        else:
            from api_server import server
            try:value['server']=server(value.get('server','custom'))
            except ProjectFault:raise ProjectFault('The original API server contract is unavailable. Existing data was preserved.',503) from None
        return value

    def listing(self):
        with self.connect() as db:
            return [] if db is None else [self.current(db,row[0]) for row in db.execute('SELECT id FROM providers WHERE retired=0 ORDER BY id')]

    def get(self,ident):
        with self.connect() as db:return self.current(db,ident)

    def receipt(self,ident,rid):
        with self.connect() as db:
            row=db.execute('SELECT * FROM requests WHERE id=? AND provider_id=?',(identity(rid),identity(ident))).fetchone() if db else None
            if row is None: raise ProjectFault('API provider request not found.',404)
            return json.loads(row['result']) if row['result'] else {'requestId':rid,'state':'pending','provider':self.current(db,ident)}

    def save(self,db,value,retired=False):
        value['status']='configured' if value['enabled'] and (value['auth']=='none' or value['keyConfigured']) else 'disconnected'
        db.execute('INSERT INTO providers VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,retired=excluded.retired',
            (value['id'],encode(value),int(retired)))
        db.execute('INSERT INTO revisions VALUES (?,?,?)',(value['id'],value['revision'],encode(value)))

    def cleanup(self,db,value):
        keep=value['credentialRevision'] if value['auth']=='bearer' and value['keyConfigured'] else -1
        extra='';args=(value['id'],keep,value['id'])
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='catalog_requests'").fetchone():
            extra=" AND revision NOT IN (SELECT json_extract(binding,'$.credentialRevision') FROM catalog_requests WHERE provider_id=? AND held=1)"
            args+=(value['id'],)
        db.execute("DELETE FROM secrets.credentials WHERE provider_id=? AND revision!=? AND revision NOT IN (SELECT credential_revision FROM leases WHERE provider_id=? AND state!='released')"+extra,args)

    def mutate(self,operation,ident,data,finish=False):
        if not isinstance(data,dict):raise ProjectFault('Invalid API provider input.',400)
        rid=identity(data.get('requestId'));ident=identity(ident) if ident else None
        if operation=='create':allowed={'requestId','name','kind','baseUrl','protocol','auth','key','openrouter','server'}
        elif operation=='update':allowed={'requestId','revision','name','baseUrl','protocol','auth','key','enabled','openrouter','server'}
        elif operation in ('disconnect','delete'):allowed={'requestId','revision'}
        else:raise ProjectFault('Invalid API provider operation.',400)
        if set(data)-allowed:raise ProjectFault('Unexpected API provider fields.',400)
        try:fingerprint=hashlib.sha256(encode({'operation':operation,'id':ident,'input':data}).encode()).hexdigest()
        except UnicodeError:raise ProjectFault('API provider input contains invalid Unicode.',400) from None
        with self.connect(write=True) as db:
            original=db.execute('SELECT * FROM requests WHERE id=?',(rid,)).fetchone()
            if original:
                if original['fingerprint']!=fingerprint:raise ProjectFault('This request ID belongs to different API provider input.',409)
                if original['result']:return json.loads(original['result'])
                if not finish:return {'requestId':rid,'state':'pending','provider':self.current(db,original['provider_id'])}
            if operation=='create':
                if not {'name','kind','baseUrl','protocol','auth'}<=set(data):raise ProjectFault('Complete the API provider configuration.',400)
                if data['kind'] not in KINDS or data['protocol'] not in PROTOCOLS or data['auth'] not in ('none','bearer'):
                    raise ProjectFault('Choose a supported API kind, protocol and authentication type.',400)
                ident=str(uuid.uuid4());checked=endpoint(data['baseUrl'],data['kind']);stamp=now()
                value={'id':ident,'type':'api','kind':data['kind'],'name':name(data['name']),'baseUrl':checked['baseUrl'],
                    'protocol':data['protocol'],'auth':data['auth'],'revision':1,'credentialRevision':0,'keyConfigured':False,
                    'enabled':data['auth']=='none','status':'disconnected','createdAt':stamp,'updatedAt':stamp,'runtime':'not-qualified'}
            else:
                value=self.current(db,ident)
                if not original:
                    if type(data.get('revision')) is not int or data['revision']!=value['revision']:
                        raise ProjectFault('API provider settings changed. Reload before saving.',409)
                    if db.execute("SELECT 1 FROM requests WHERE provider_id=? AND phase!='complete'",(ident,)).fetchone():
                        raise ProjectFault('An original provider disconnect is unfinished. Read and finish that request first.',409)
                    value['revision']+=1;value['updatedAt']=now()
            if operation in ('disconnect','delete'):
                if not original:
                    value['enabled']=False;self.save(db,value)
                    self.release_unstarted(db,ident)
                    db.execute("INSERT INTO requests VALUES (?,?,?,?,NULL,'admission_closed')",(rid,ident,operation,fingerprint))
                    return {'requestId':rid,'state':'pending','provider':value}
                if db.execute("SELECT 1 FROM leases WHERE provider_id=? AND state!='released'",(ident,)).fetchone():
                    raise ProjectFault('Original API worker leases are still unconfirmed. Credentials were preserved.',503)
                if (db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='catalog_requests'").fetchone()
                        and db.execute('SELECT 1 FROM catalog_requests WHERE provider_id=? AND held=1',(ident,)).fetchone()):
                    raise ProjectFault('An original metadata transport is unconfirmed. Credentials were preserved.',503)
                value['revision']+=1;value['updatedAt']=now();value['enabled']=False
                value['credentialRevision']+=1;value['keyConfigured']=False;self.cleanup(db,value);self.save(db,value,operation=='delete')
            else:
                if 'name' in data:value['name']=name(data['name'])
                if value['kind']=='openrouter':
                    if 'server' in data:raise ProjectFault('Server presets require a Custom or Local API connection.',400)
                    from openrouter_policy import policy
                    value['openrouter']=policy(data.get('openrouter',value.get('openrouter')))
                elif 'openrouter' in data:raise ProjectFault('Routing settings require an OpenRouter connection.',400)
                else:
                    from api_server import server
                    value['server']=server(data.get('server',value.get('server','custom')))
                old_endpoint=endpoint(value['baseUrl'],value['kind']);new_endpoint=endpoint(data.get('baseUrl',value['baseUrl']),value['kind'])
                if old_endpoint['origin']!=new_endpoint['origin'] and value['keyConfigured'] and 'key' not in data:
                    raise ProjectFault('Changing API origin requires a replacement key or explicit key removal.',400)
                value['baseUrl']=new_endpoint['baseUrl']
                for field,choices in (('protocol',PROTOCOLS),('auth',('none','bearer'))):
                    if field in data:
                        if data[field] not in choices:raise ProjectFault('Choose a supported API protocol and authentication type.',400)
                        value[field]=data[field]
                if 'key' in data and data['key'] is not None:
                    if value['auth']!='bearer':raise ProjectFault('A bearer key requires bearer authentication.',400)
                    secret=key(data['key']);value['credentialRevision']+=1;value['keyConfigured']=True
                    db.execute('INSERT INTO secrets.credentials VALUES (?,?,?)',(ident,value['credentialRevision'],secret))
                    if operation=='create':value['enabled']=True
                elif 'key' in data or value['auth']=='none' and value['keyConfigured']:
                    value['credentialRevision']+=1;value['keyConfigured']=False
                if 'enabled' in data:
                    if type(data['enabled']) is not bool:raise ProjectFault('Invalid API enabled state.',400)
                    value['enabled']=data['enabled']
                if value['auth']=='bearer' and not value['keyConfigured']:
                    if data.get('enabled') is True:raise ProjectFault('Configure a bearer key before enabling this provider.',400)
                    value['enabled']=False
                self.cleanup(db,value);self.save(db,value)
            result={'requestId':rid,'state':'complete','provider':value}
            if original:db.execute("UPDATE requests SET result=?,phase='complete' WHERE id=?",(encode(result),rid))
            else:db.execute("INSERT INTO requests VALUES (?,?,?,?,?,'complete')",(rid,ident,operation,fingerprint,encode(result)))
            return result

    def run_binding(self,run_id,owner_type,owner_id,sid,rid,snapshot):
        if owner_type not in ('project','skill') or snapshot.get('apiRunId')!=identity(run_id):
            raise ProjectFault('The original API run binding is unavailable.',409)
        return {'schema':1,'owner':{'type':owner_type,'id':identity(owner_id)},'sessionId':identity(sid),
            'requestId':identity(rid),'configSha256':hashlib.sha256(encode(snapshot).encode()).hexdigest()}

    def creation_receipt(self,rid):
        with self.connect() as db:
            row=db.execute("SELECT result FROM requests WHERE id=? AND operation='create'",(identity(rid),)).fetchone() if db else None
            if row is None or not row[0]:raise ProjectFault('Original API provider creation not found.',404)
            return json.loads(row[0])

    def reserve(self,run_id,owner_type,owner_id,sid,rid,snapshot):
        binding=self.run_binding(run_id,owner_type,owner_id,sid,rid,snapshot);selected=snapshot['apiProvider']
        with self.connect(write=True) as db:
            value=self.current(db,selected['id'])
            if not value['enabled'] or any(value[k]!=v for k,v in selected.items()):
                raise ProjectFault('The API connection changed before admission. No model request was started.',409)
            previous=db.execute('SELECT * FROM leases WHERE run_id=?',(run_id,)).fetchone()
            if previous:
                if (previous['state']!='reserved' or previous['provider_id']!=value['id']
                        or json.loads(previous['binding'])!=binding):
                    raise ProjectFault('The original API reservation has changed. It was not replaced.',409)
                return
            db.execute("INSERT INTO leases VALUES (?,?,?,?,'reserved',?)",(run_id,value['id'],value['revision'],value['credentialRevision'],encode(binding)))

    def claim(self,run_id,owner_type,owner_id,sid,rid,snapshot,worker):
        binding=self.run_binding(run_id,owner_type,owner_id,sid,rid,snapshot)
        from attachment_store import birth
        if (set(worker)!={'pid','birth','release'} or worker['pid']!=os.getpid() or worker['birth']!=birth(os.getpid())
                or not isinstance(worker['release'],str) or not worker['release']):
            raise ProjectFault('The original API worker identity is unavailable.',409)
        with self.connect(write=True) as db:
            row=db.execute('SELECT * FROM leases WHERE run_id=?',(run_id,)).fetchone()
            selected=snapshot['apiProvider'];value=self.current(db,selected['id'])
            if (not value['enabled'] or row is None or row['state']!='reserved' or row['provider_id']!=selected['id']
                    or row['config_revision']!=selected['revision'] or row['credential_revision']!=selected['credentialRevision']
                    or json.loads(row['binding'])!=binding):
                raise ProjectFault('The original API admission is no longer available. No replacement request was started.',409)
            credential=None
            if selected['auth']=='bearer':
                secret=db.execute('SELECT value FROM secrets.credentials WHERE provider_id=? AND revision=?',
                    (selected['id'],selected['credentialRevision'])).fetchone()
                if not secret:raise ProjectFault('The original API credential revision is unavailable.',409)
                credential=key(secret[0])
            db.execute("UPDATE leases SET state='active',binding=? WHERE run_id=?",(encode(binding|{'worker':worker}),run_id))
            return credential

    def validate_active(self,run_id,owner_type,owner_id,sid,rid,snapshot,worker):
        binding=self.run_binding(run_id,owner_type,owner_id,sid,rid,snapshot)
        selected=snapshot['apiProvider']
        with self.connect() as db:
            row=db.execute('SELECT * FROM leases WHERE run_id=?',(run_id,)).fetchone() if db else None
            value=self.current(db,selected['id']) if db else None
            if (not value or not value['enabled'] or any(value[k]!=v for k,v in selected.items())
                    or row is None or row['state']!='active' or row['provider_id']!=selected['id']
                    or row['config_revision']!=selected['revision'] or row['credential_revision']!=selected['credentialRevision']
                    or json.loads(row['binding'])!=binding|{'worker':worker}):
                raise ProjectFault('The original API worker lease changed. No continuation was submitted.',409)

    def release(self,run_id,owner_type,owner_id,sid,rid,snapshot,worker=None):
        binding=self.run_binding(run_id,owner_type,owner_id,sid,rid,snapshot)
        with self.connect(write=True) as db:
            row=db.execute('SELECT * FROM leases WHERE run_id=?',(run_id,)).fetchone()
            if row is None or row['state']=='released':return
            expected=binding if row['state']=='reserved' else binding|{'worker':worker}
            if row['state'] not in ('reserved','active') or json.loads(row['binding'])!=expected:
                raise ProjectFault('API transport closure could not be bound to its original worker. Credentials were preserved.',503)
            db.execute("UPDATE leases SET state='released' WHERE run_id=?",(run_id,))
            self.cleanup(db,self.current(db,row['provider_id'],retired=True))

    def release_unstarted(self,db,ident):
        # Called only after this transaction closed admission. Claim checks
        # enabled under the same lock before exposing a credential to a worker.
        for row in db.execute("SELECT run_id,binding FROM leases WHERE provider_id=? AND state='reserved'",(ident,)).fetchall():
            try:
                value=json.loads(row['binding'])
                if (set(value)!={'schema','owner','sessionId','requestId','configSha256'} or type(value['schema']) is not int or value['schema']!=1
                        or set(value['owner'])!={'type','id'} or value['owner']['type'] not in ('project','skill')
                        or len(value['configSha256'])!=64):continue
                for candidate in (row['run_id'],value['owner']['id'],value['sessionId'],value['requestId']):identity(candidate)
            except (ValueError,KeyError,TypeError,ProjectFault):continue
            db.execute("UPDATE leases SET state='released' WHERE run_id=?",(row['run_id'],))

    def held_session(self,provider_id,owner_type,owner_id,sid):
        with self.connect() as db:
            if db is None:return False
            for row in db.execute("SELECT binding FROM leases WHERE provider_id=? AND state!='released'",(identity(provider_id),)):
                try:
                    value=json.loads(row['binding'])
                    if value['owner']=={'type':owner_type,'id':owner_id} and value['sessionId']==sid:return True
                except (ValueError,TypeError,KeyError):return True
            return False
