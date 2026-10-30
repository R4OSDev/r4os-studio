"""Claude-plan provider identities; native credentials belong only to its CLI."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

from api_provider_store import private,name
from claude_runtime import installed,profile
from session_store import identity,encode,now
from store import ProjectFault


class ClaudeProviders:
    def __init__(self,providers):self.parent=Path(providers).absolute();self.root=self.parent/'ClaudeSubscriptions'

    @contextmanager
    def connect(self,write=False):
        if not write and not self.root.exists() and not self.root.is_symlink():yield None;return
        db=None
        try:
            private(self.parent,directory=True);private(self.root,directory=True,create=write)
            path=self.root/'Providers.sqlite';private(path,create=write)
            for suffix in ('-journal','-wal','-shm'):
                sidecar=path.with_name(path.name+suffix)
                if sidecar.exists() or sidecar.is_symlink():private(sidecar)
            db=sqlite3.connect(str(path) if write else path.as_uri()+'?mode=ro',uri=not write,timeout=5);db.row_factory=sqlite3.Row
            db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA temp_store=MEMORY')
            if write:
                db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
            else:db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if version!=1:
                if not write or version!=0 or db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                    raise ProjectFault('The Claude provider catalog needs explicit maintenance. Existing data was preserved.',503)
                db.execute('CREATE TABLE providers(id TEXT PRIMARY KEY,data TEXT NOT NULL)')
                db.execute('CREATE TABLE revisions(provider_id TEXT NOT NULL,revision INTEGER NOT NULL,data TEXT NOT NULL,PRIMARY KEY(provider_id,revision))')
                db.execute('CREATE TABLE requests(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,result TEXT NOT NULL)')
                db.execute('PRAGMA user_version=1')
            yield db
            if write:db.commit()
        except ProjectFault:raise
        except (OSError,ValueError,TypeError,sqlite3.Error):
            raise ProjectFault('The original Claude provider result is unconfirmed. Read its original request before retrying.',503) from None
        finally:
            if db:
                if db.in_transaction:db.rollback()
                db.close()

    def current(self,db,ident):
        row=db.execute('SELECT data FROM providers WHERE id=?',(identity(ident),)).fetchone() if db else None
        if not row:raise ProjectFault('Claude provider not found.',404)
        value=json.loads(row[0])
        if (not isinstance(value,dict) or set(value)!={'id','type','name','revision','profileRevision','runtimeProfileId',
                'status','enabled','auth','createdAt','updatedAt','account'}
                or value['id']!=ident or value['type']!='claude-subscription' or type(value['revision']) is not int or value['revision']<1
                or type(value['profileRevision']) is not int or value['profileRevision']!=1
                or value['runtimeProfileId']!=profile()['id'] or value['enabled'] is not False
                or value['status'] not in ('not-connected','connected','reauthentication-required','unsupported')
                or value['auth']!={'kind':'native-plan','state':value['status']}
                or not valid_account(value['account'],value['status'])
                or not all(isinstance(value[k],str) for k in ('name','createdAt','updatedAt')) or name(value['name'])!=value['name']):
            raise ProjectFault('The original Claude provider identity is unavailable. Existing data was preserved.',503)
        return value

    def listing(self):
        with self.connect() as db:return [] if db is None else [self.current(db,row[0]) for row in db.execute('SELECT id FROM providers ORDER BY id')]

    def get(self,ident):
        with self.connect() as db:return self.current(db,ident)

    def receipt(self,rid):
        with self.connect() as db:
            row=db.execute('SELECT result FROM requests WHERE id=?',(identity(rid),)).fetchone() if db else None
            if not row:raise ProjectFault('Original Claude provider request not found.',404)
            return json.loads(row[0])

    def create(self,data):
        if not isinstance(data,dict) or set(data)!={'requestId','name'}:
            raise ProjectFault('Claude-plan creation accepts only a name and original request ID.',400)
        rid=identity(data['requestId']);display=name(data['name']);fingerprint=hashlib.sha256(encode(data).encode()).hexdigest()
        with self.connect() as db:
            original=db.execute('SELECT * FROM requests WHERE id=?',(rid,)).fetchone() if db else None
            if original:
                if original['fingerprint']!=fingerprint:raise ProjectFault('This original Claude request has different input.',409)
                return json.loads(original['result'])
        runtime=installed(self.parent)
        with self.connect(write=True) as db:
            original=db.execute('SELECT * FROM requests WHERE id=?',(rid,)).fetchone()
            if original:
                if original['fingerprint']!=fingerprint:raise ProjectFault('This original Claude request has different input.',409)
                return json.loads(original['result'])
            ident=str(uuid.uuid4());stamp=now()
            value={'id':ident,'type':'claude-subscription','name':display,'revision':1,'profileRevision':1,
                'runtimeProfileId':runtime['id'],'status':'not-connected','enabled':False,
                'auth':{'kind':'native-plan','state':'not-connected'},'createdAt':stamp,'updatedAt':stamp,'account':None}
            result={'requestId':rid,'state':'complete','provider':value}
            db.execute('INSERT INTO providers VALUES (?,?)',(ident,encode(value)))
            db.execute('INSERT INTO revisions VALUES (?,1,?)',(ident,encode(value)))
            db.execute('INSERT INTO requests VALUES (?,?,?)',(rid,fingerprint,encode(result)))
            return result


def valid_account(value,status):
    if status!='connected':return value is None
    return (isinstance(value,dict) and set(value)=={'email','orgId','orgName','plan','authMethod','apiProvider','checkedAt'}
        and value['plan'] in ('pro','max') and value['authMethod']=='claude.ai' and value['apiProvider']=='firstParty'
        and all(value[k] is None or isinstance(value[k],str) and len(value[k])<=320 and all(ord(c)>=32 for c in value[k])
            for k in ('email','orgId','orgName')) and isinstance(value['checkedAt'],str))
