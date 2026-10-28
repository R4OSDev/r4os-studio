"""Private numeric receipts and lifetime aggregates. No prompts or account metadata."""
import hashlib
import json
from pathlib import Path
import sqlite3
from profile import directory
from session_store import encode, now
from store import ProjectFault

FIELDS=('total','input','output','cachedInput','cacheWrite','reasoningOutput')
MAX_NUMBER=2**53-1
MAX_SOURCE=16384

def hashed(value):return hashlib.sha256(encode(value).encode()).hexdigest()
def scope(owner,sid=None):return hashed({'owner':owner,**({'session':sid} if sid else {})})
def number(value):
    if type(value) is not int or not 0<=value<=MAX_NUMBER:raise ProjectFault('Invalid numeric statistics receipt.',400)
    return value

def validate(value):
    if not isinstance(value,dict) or set(value)!={'kind','key','project','session','at','values'}:raise ProjectFault('Invalid statistics receipt.',400)
    if value['kind'] not in ('tokens','goal','gap'):raise ProjectFault('Unknown statistics receipt kind.',400)
    for k in ('key','session'):
        if not isinstance(value[k],str) or len(value[k])!=64 or any(c not in '0123456789abcdef' for c in value[k]):raise ProjectFault('Invalid statistics identity.',400)
    if value['project'] is not None and (not isinstance(value['project'],str) or len(value['project'])!=64):raise ProjectFault('Invalid statistics scope.',400)
    if not isinstance(value['at'],str) or len(value['at'])>40:raise ProjectFault('Invalid statistics timestamp.',400)
    data=value['values']
    if not isinstance(data,dict):raise ProjectFault('Invalid statistics measurements.',400)
    allowed=FIELDS if value['kind']=='tokens' else ('durationMs','uncertain') if value['kind']=='goal' else ('missing',)
    if not set(data)<=set(allowed):raise ProjectFault('Unexpected statistics metadata.',400)
    for k,v in data.items():
        if k=='uncertain':
            if type(v) is not bool:raise ProjectFault('Invalid statistics coverage.',400)
        elif v is not None:number(v)
    if value['kind']=='goal' and ('durationMs' not in data or data['durationMs'] is None):raise ProjectFault('Missing Goal duration.',400)
    return value


class Statistics:
    def __init__(self,projects,create=False):
        self.path=Path(projects)/'.studio/statistics/Statistics.sqlite';self.db=None
        if not self.path.exists() and not create:return
        if self.path.is_symlink():raise ProjectFault('Statistics storage is unavailable; existing data was preserved.',503)
        if create:directory(self.path.parent)
        try:
            self.db=sqlite3.connect(self.path if create else self.path.absolute().as_uri()+'?mode=ro',uri=not create,timeout=2);self.db.row_factory=sqlite3.Row
            self.db.execute('PRAGMA busy_timeout=2000')
            version=self.db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0,1):raise ValueError('Unsupported statistics schema')
            if version==0:
                if not create:raise ValueError('Uninitialized statistics storage')
                with self.db:
                    self.db.execute('CREATE TABLE receipts(key TEXT PRIMARY KEY,payload TEXT NOT NULL)')
                    self.db.execute('CREATE TABLE totals(scope TEXT PRIMARY KEY,payload TEXT NOT NULL)')
                    self.db.execute('CREATE TABLE conflicts(key TEXT PRIMARY KEY)')
                    self.db.execute('PRAGMA user_version=1')
            self.db.execute('SELECT key FROM receipts LIMIT 1')
        except Exception:
            self.close();raise ProjectFault('Statistics storage is unavailable; existing data was preserved.',503) from None
    def close(self):
        if self.db:self.db.close();self.db=None
    def apply(self,value):
        value=validate(value)
        if self.db is None:raise ProjectFault('Statistics storage is not initialized.',503)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT payload FROM receipts WHERE key=?',(value['key'],)).fetchone()
            old=json.loads(row[0]) if row else None
            if old:
                if old==value:return False
                if value['kind']!='goal' or any(old[k]!=value[k] for k in ('kind','key','project','session')):
                    self.db.execute('INSERT OR IGNORE INTO conflicts VALUES (?)',(value['key'],));self.db.commit()
                    raise ProjectFault('Conflicting statistics receipt was preserved for reconciliation.',409)
                if value['values']['durationMs']<old['values']['durationMs']:return False
            self.db.execute('INSERT OR REPLACE INTO receipts VALUES (?,?)',(value['key'],encode(value)))
            for key in ['global',*(['project:'+value['project']] if value['project'] else []),'session:'+value['session']]:
                row=self.db.execute('SELECT payload FROM totals WHERE scope=?',(key,)).fetchone()
                total=json.loads(row[0]) if row else {'tokens':{k:None for k in FIELDS},'longestGoalMs':None,'since':value['at'],'updatedAt':value['at'],'incomplete':False}
                if value['kind']=='tokens':
                    for field in FIELDS:
                        n=value['values'].get(field)
                        if n is not None:total['tokens'][field]=str(int(total['tokens'][field] or '0')+n)
                    if any(value['values'].get(f) is None for f in ('total','input','output')):total['incomplete']=True
                elif value['kind']=='goal' and not key.startswith('session:'):
                    total['longestGoalMs']=max(total['longestGoalMs'] or 0,value['values']['durationMs'])
                    if value['values'].get('uncertain'):total['incomplete']=True
                elif value['kind']=='gap':total['incomplete']=True
                total['updatedAt']=max(total['updatedAt'],value['at']);total['since']=min(total['since'],value['at'])
                self.db.execute('INSERT OR REPLACE INTO totals VALUES (?,?)',(key,encode(total)))
            return True
        except BaseException:
            if self.db.in_transaction:self.db.rollback()
            raise
        finally:
            if self.db.in_transaction:self.db.commit()
    def read(self,key='global'):
        row=self.db.execute('SELECT payload FROM totals WHERE scope=?',(key,)).fetchone() if self.db else None
        data=json.loads(row[0]) if row else {'tokens':{k:None for k in FIELDS},'longestGoalMs':None,'since':None,'updatedAt':None,'incomplete':True}
        conflicts=bool(self.db and self.db.execute('SELECT 1 FROM conflicts LIMIT 1').fetchone())
        result={'schema':1,'tokens':data['tokens'],'coverage':{'state':'partial' if row else 'notReported','since':data['since'],'updatedAt':data['updatedAt'],'historicalComplete':False,'hasGaps':data['incomplete'] or conflicts}}
        if not key.startswith('session:'):result['longestGoalMs']=data['longestGoalMs']
        return result


class Source:
    def __init__(self,store):self.store=store
    def schema(self):
        with self.store.db:
            self.store.db.execute('CREATE TABLE IF NOT EXISTS statistic_receipts(key TEXT PRIMARY KEY,payload TEXT NOT NULL,acknowledged INTEGER NOT NULL DEFAULT 0)')
    def put(self,sid,kind,identity,values):
        self.schema();self.store.row(sid)
        owner={'type':self.store.owner_type,'id':self.store.owner_id}
        value=validate({'kind':kind,'key':hashed(identity),'project':scope(owner) if owner['type']=='project' else None,'session':scope(owner,sid),'at':now(),'values':values})
        row=self.store.db.execute('SELECT payload FROM statistic_receipts WHERE key=?',(value['key'],)).fetchone()
        if row:
            old=json.loads(row[0]);value['at']=old['at'] if kind!='goal' else value['at']
            if old==value:return value
            if kind!='goal':raise ProjectFault('Conflicting source statistics receipt was preserved.',409)
            if values['durationMs']<old['values']['durationMs']:return old
        elif self.store.db.execute('SELECT COUNT(*) FROM statistic_receipts').fetchone()[0]>=MAX_SOURCE:
            raise ProjectFault('The private statistics receipt limit was reached; coverage is incomplete.',503)
        with self.store.db:self.store.db.execute('INSERT OR REPLACE INTO statistic_receipts VALUES (?,?,0)',(value['key'],encode(value)))
        return value
    def flush(self,limit=128,include_acknowledged=False):
        if not self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='statistic_receipts'").fetchone():return 0
        target=Statistics(self.store.projects,True);count=0
        try:
            for row in self.store.db.execute('SELECT key,payload FROM statistic_receipts '+('' if include_acknowledged else 'WHERE acknowledged=0 ')+'ORDER BY rowid LIMIT ?',(limit,)).fetchall():
                target.apply(json.loads(row['payload']))
                with self.store.db:self.store.db.execute('UPDATE statistic_receipts SET acknowledged=1 WHERE key=? AND payload=?',(row['key'],row['payload']))
                count+=1
            return count
        finally:target.close()


def read(projects,key='global'):
    db=None
    try:
        db=Statistics(projects);return db.read(key)
    finally:
        if db:db.close()
