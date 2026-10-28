"""Session-private observations, minimal replay receipts and user-only deletion."""
import hashlib
import json
import re
import unicodedata
import uuid
from session_store import encode,identity,now
from store import ProjectFault
from run_store import event

KINDS=('problem','suggestion')
CATEGORIES=('tools','capabilities','workflow','interface','documentation')
CONTENT=('kind','category','title','description','impact','workaround','suggestion')
MAX_NOTES=200
SECRET=re.compile(r'(?:\bsk-[A-Za-z0-9_-]{16,}|\bBearer\s+[A-Za-z0-9_.-]{16,}|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.|(?<!\S)/(?:root|home|Data|etc|opt|run|var)/\S+|\b[A-Za-z]:\\(?:Users|Data|Windows)\\)',re.I)

def hashed(value):return hashlib.sha256(encode(value).encode()).hexdigest()
def normalize(text):return ' '.join(unicodedata.normalize('NFKC',text).casefold().split())
def content(value):
    if (not isinstance(value,dict) or not {'kind','category','title','description'}<=set(value) or set(value)-set(CONTENT)
            or value['kind'] not in KINDS or value['category'] not in CATEGORIES):raise ProjectFault('Use a supported environment note kind and category.',400)
    result={}
    for key,text in value.items():
        limit=160 if key=='title' else 4000 if key=='description' else 1000
        if (not isinstance(text,str) or len(text)>limit or any(0xD800<=ord(c)<=0xDFFF or ord(c)<32 and c not in '\n\t' for c in text)
                or key=='title' and any(c in text for c in '\n\t')):raise ProjectFault('Keep environment notes short and valid.',400)
        if key in ('title','description') and not text.strip():raise ProjectFault('A factual title and description are required.',400)
        if SECRET.search(text):raise ProjectFault('Remove secrets and private host paths from the note.',400)
        if text.strip():result[key]=text.strip()
    if len(encode(result).encode())>8192:raise ProjectFault('Environment notes are limited to8 KiB.',400)
    return result

class Notes:
    def __init__(self,store):self.store=store
    def exists(self):return bool(self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='environment_notes'").fetchone())
    def schema(self):
        with self.store.db:
            self.store.db.execute('CREATE TABLE IF NOT EXISTS environment_notes(id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),fingerprint TEXT NOT NULL,data TEXT,revision INTEGER NOT NULL,created_at TEXT NOT NULL,deleted_at TEXT)')
            self.store.db.execute('CREATE UNIQUE INDEX IF NOT EXISTS environment_note_duplicate ON environment_notes(session_id,fingerprint) WHERE data IS NOT NULL')
            self.store.db.execute('CREATE TABLE IF NOT EXISTS environment_note_collections(session_id TEXT PRIMARY KEY REFERENCES sessions(id),revision INTEGER NOT NULL)')
            self.store.db.execute('CREATE TABLE IF NOT EXISTS environment_note_reads(run_id TEXT PRIMARY KEY,session_id TEXT NOT NULL,revision INTEGER NOT NULL,call_id TEXT NOT NULL)')
            self.store.db.execute('CREATE TABLE IF NOT EXISTS environment_note_calls(run_id TEXT NOT NULL,call_id TEXT NOT NULL,session_id TEXT NOT NULL,fingerprint TEXT NOT NULL,note_id TEXT NOT NULL,PRIMARY KEY(run_id,call_id))')
            self.store.db.execute('CREATE TABLE IF NOT EXISTS environment_note_deletions(request_id TEXT PRIMARY KEY,session_id TEXT NOT NULL,fingerprint TEXT NOT NULL,response TEXT NOT NULL)')
    def current(self,sid):
        self.store.row(sid)
        if not self.exists():return 0,0
        revision=self.store.db.execute('SELECT revision FROM environment_note_collections WHERE session_id=?',(sid,)).fetchone()
        count=self.store.db.execute('SELECT COUNT(*) FROM environment_notes WHERE session_id=? AND data IS NOT NULL',(sid,)).fetchone()[0]
        return revision[0] if revision else 0,count
    def listing(self,sid,query=None):
        own=not self.store.db.in_transaction
        if own:self.store.db.execute('BEGIN')
        try:return self._listing(sid,query)
        finally:
            if own:self.store.db.commit()
    def _listing(self,sid,query=None):
        query=query or {};revision,count=self.current(sid)
        if not set(query)<={'before','limit','query','kind','category','id'}:raise ProjectFault('Invalid environment note filter.',400)
        limit=query.get('limit',30);before=query.get('before',2**53-1)
        if type(limit) is not int or not 1<=limit<=50 or type(before) is not int or not 1<=before<=2**53-1:raise ProjectFault('Invalid environment note page.',400)
        for key,allowed in [('kind',KINDS),('category',CATEGORIES)]:
            if key in query and query[key] not in allowed:raise ProjectFault('Invalid environment note filter.',400)
        search=query.get('query','')
        if not isinstance(search,str) or len(search)>160:raise ProjectFault('Keep the environment note search short.',400)
        if 'id' in query:identity(query['id'])
        found=[]
        if self.exists():
            for row in self.store.db.execute('SELECT rowid,* FROM environment_notes WHERE session_id=? AND data IS NOT NULL AND rowid<? ORDER BY rowid DESC',(sid,before)):
                value=json.loads(row['data'])
                if any(key in query and query[key]!=value[key] for key in ('kind','category')):continue
                if query.get('id') and row['id']!=query['id']:continue
                if normalize(search) not in normalize(' '.join(str(value.get(k,'')) for k in CONTENT)):continue
                found.append((row['rowid'],value))
                if len(found)>limit:break
        selected=[];size=0
        for rowid,value in found[:limit]:
            length=len(encode(value).encode())
            if selected and size+length>24576:break
            selected.append((rowid,value));size+=length
        return {'schemaVersion':1,'owner':{'type':self.store.owner_type,'id':self.store.owner_id},'sessionId':sid,'revision':revision,'count':count,'entries':[v for _,v in selected],'nextBefore':selected[-1][0] if selected and len(found)>len(selected) else None,'limits':{'maxNotes':MAX_NOTES,'maxTitleCharacters':160,'maxEntryBytes':8192}}
    def live(self,sid,rid,call,tool):
        self.store.row(sid);identity(rid)
        if not isinstance(call,str) or not 1<=len(call)<=256:raise ProjectFault('Invalid note call identity.',400)
        run=self.store.db.execute('SELECT * FROM runs WHERE id=? AND session_id=?',(rid,sid)).fetchone()
        owned=self.store.db.execute('SELECT tool FROM tools WHERE run_id=? AND call_id=?',(rid,call)).fetchone()
        if (not run or not run['busy'] or run['state']!='running' or not owned or owned['tool']!='studio_'+tool
                or json.loads(run['config']).get('owner')!={'type':self.store.owner_type,'id':self.store.owner_id}):raise ProjectFault('This note call does not belong to the active session run.',409)
        if json.loads(run['config']).get('environmentNotesEnabled') is False:raise ProjectFault('Environment notes are disabled for this run.',403)
    def read_tool(self,sid,rid,call,query):
        self.schema();self.live(sid,rid,call,'read_environment_notes');result=self.listing(sid,query)
        with self.store.db:self.store.db.execute('INSERT OR REPLACE INTO environment_note_reads VALUES (?,?,?,?)',(rid,sid,result['revision'],call))
        return result
    def call_receipt(self,sid,rid,call,payload_hash):
        self.store.row(sid)
        if not self.exists():return None
        row=self.store.db.execute('SELECT * FROM environment_note_calls WHERE run_id=? AND call_id=? AND session_id=?',(rid,call,sid)).fetchone()
        if not row:return None
        if row['fingerprint']!=payload_hash:raise ProjectFault('This call ID belongs to another original note request.',409)
        active=self.store.db.execute('SELECT data FROM environment_notes WHERE id=? AND session_id=?',(row['note_id'],sid)).fetchone()
        return {'id':row['note_id'],'state':'active' if active and active['data'] else 'deleted','revision':self.current(sid)[0]}
    def record(self,sid,rid,call,data,version):
        if not isinstance(data,dict) or 'revision' not in data or type(data['revision']) is not int:raise ProjectFault('Read this session’s current notes before recording.',400)
        value=content({k:v for k,v in data.items() if k!='revision'});payload_hash=hashed(data)
        self.schema();previous=self.call_receipt(sid,rid,call,payload_hash)
        if previous:return previous
        self.store.db.execute('BEGIN IMMEDIATE')
        try:
            self.live(sid,rid,call,'record_environment_note');revision,count=self.current(sid)
            read=self.store.db.execute('SELECT revision FROM environment_note_reads WHERE run_id=? AND session_id=?',(rid,sid)).fetchone()
            if data['revision']!=revision or not read or read[0]!=revision:raise ProjectFault('The notes changed or were not read. Read/search the current collection again.',409)
            if self.store.db.execute('SELECT COUNT(*) FROM environment_note_calls WHERE session_id=?',(sid,)).fetchone()[0]>=16384:raise ProjectFault('This session reached its note receipt limit.',409)
            fingerprint=hashed({k:normalize(value.get(k,'')) for k in CONTENT})
            duplicate=self.store.db.execute('SELECT id FROM environment_notes WHERE session_id=? AND fingerprint=? AND data IS NOT NULL',(sid,fingerprint)).fetchone()
            if duplicate:ident=duplicate[0]
            else:
                if count>=MAX_NOTES:raise ProjectFault('This session has200 environment notes. Existing entries were preserved.',409)
                ident=str(uuid.uuid4());stamp=now()
                record={'schemaVersion':1,'id':ident,'revision':1,**value,'createdAt':stamp,'origin':{'owner':{'type':self.store.owner_type,'id':self.store.owner_id},'sessionId':sid,'runId':rid,'callId':call,'studioVersion':version}}
                self.store.db.execute('INSERT INTO environment_notes VALUES (?,?,?,?,1,?,NULL)',(ident,sid,fingerprint,encode(record),stamp))
                revision+=1;self.store.db.execute('INSERT OR REPLACE INTO environment_note_collections VALUES (?,?)',(sid,revision))
                self.publish(sid,revision,count+1)
            self.store.db.execute('INSERT INTO environment_note_calls VALUES (?,?,?,?,?)',(rid,call,sid,payload_hash,ident))
            self.store.db.commit();return {'id':ident,'state':'active','revision':revision}
        finally:
            if self.store.db.in_transaction:self.store.db.rollback()
    def publish(self,sid,revision,count):event(self.store,sid,None,'environmentNotes',{'revision':revision,'count':count},False)
    def deletion_receipt(self,sid,rid):
        self.store.row(sid);identity(rid)
        row=self.store.db.execute('SELECT response FROM environment_note_deletions WHERE request_id=? AND session_id=?',(rid,sid)).fetchone() if self.exists() else None
        if not row:raise ProjectFault('Environment note deletion receipt not found.',404)
        return json.loads(row[0])
    def delete(self,sid,data,note_id=None):
        allowed={'requestId','collectionRevision','revision'} if note_id else {'requestId','collectionRevision','confirmName','count'}
        if not isinstance(data,dict) or set(data)!=allowed or type(data.get('collectionRevision')) is not int:raise ProjectFault('Invalid environment note deletion.',400)
        rid=identity(data['requestId']);identity(note_id) if note_id else None
        fingerprint=hashed({'sessionId':sid,'noteId':note_id,**data});self.schema()
        self.store.db.execute('BEGIN IMMEDIATE')
        try:
            session=self.store.row(sid);previous=self.store.db.execute('SELECT * FROM environment_note_deletions WHERE request_id=?',(rid,)).fetchone()
            if previous:
                if previous['session_id']!=sid or previous['fingerprint']!=fingerprint:raise ProjectFault('This request ID belongs to another original deletion.',409)
                return json.loads(previous['response'])
            revision,count=self.current(sid)
            if data['collectionRevision']!=revision:raise ProjectFault('The notes changed. Reload and confirm the current entries.',409)
            if note_id:
                row=self.store.db.execute('SELECT revision FROM environment_notes WHERE session_id=? AND id=? AND data IS NOT NULL',(sid,note_id)).fetchone()
                if not row or type(data['revision']) is not int or row[0]!=data['revision']:raise ProjectFault('This note changed or was removed. Reload its current state.',409)
                deleted=1
            else:
                if data['confirmName']!=session['name'] or type(data['count']) is not int or data['count']!=count:raise ProjectFault('The session or note count changed. Confirm it again.',409)
                deleted=count
            self.store.db.execute('PRAGMA secure_delete=ON')
            self.store.db.execute('UPDATE environment_notes SET data=NULL,deleted_at=?,revision=revision+1 WHERE session_id=? AND data IS NOT NULL'+(' AND id=?' if note_id else ''),(now(),sid,*([note_id] if note_id else [])))
            revision+=1;self.store.db.execute('INSERT OR REPLACE INTO environment_note_collections VALUES (?,?)',(sid,revision))
            result={'requestId':rid,'state':'confirmed','deleted':deleted,'revision':revision,'count':count-deleted}
            self.store.db.execute('INSERT INTO environment_note_deletions VALUES (?,?,?,?)',(rid,sid,fingerprint,encode(result)))
            self.publish(sid,revision,count-deleted);self.store.db.commit();return result
        finally:
            if self.store.db.in_transaction:self.store.db.rollback()
