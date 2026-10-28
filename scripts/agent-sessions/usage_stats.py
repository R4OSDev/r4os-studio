"""Qualified response receipts. Cumulative token_count events are never spending."""
import asyncio
import json
import os
from pathlib import Path
import stat
from profile import CODEX_VERSION,CODEX_SHA256
from stats_store import Source,hashed,number
from store import ProjectFault

CAMEL={'total':'totalTokens','input':'inputTokens','output':'outputTokens','cachedInput':'cachedInputTokens','cacheWrite':'cacheWriteInputTokens','reasoningOutput':'reasoningOutputTokens'}
SNAKE={'total':'total_tokens','input':'input_tokens','output':'output_tokens','cachedInput':'cached_input_tokens','cacheWrite':'cache_write_input_tokens','reasoningOutput':'reasoning_output_tokens'}
MAX_LINE=524288
BUDGET=4194304

def qualified(engine):return engine.get('version')==CODEX_VERSION and engine.get('sha256')==CODEX_SHA256

def valid_id(value):return isinstance(value,str) and 0<len(value.encode())<=256 and '\0' not in value

class Usage:
    def __init__(self,store,sid):self.store=store;self.sid=sid
    def schema(self):
        Source(self.store).schema()
        with self.store.db:
            self.store.db.execute('CREATE TABLE IF NOT EXISTS statistic_usage(key TEXT PRIMARY KEY,session_id TEXT NOT NULL,run_id TEXT,turn_id TEXT NOT NULL,origin TEXT NOT NULL)')
            self.store.db.execute('CREATE TABLE IF NOT EXISTS statistic_history(key TEXT PRIMARY KEY,inode TEXT NOT NULL,offset INTEGER NOT NULL,skipping INTEGER NOT NULL)')
    def ingest(self,thread,turn,response,usage,camel=False,run_id=None):
        if thread!=self.store.row(self.sid)['thread_id'] or not all(valid_id(x) for x in (thread,turn,response)):return False
        identity={'source':'codex-response-v1','runtime':CODEX_SHA256,'thread':thread,'response':response}
        self.schema();source=Source(self.store)
        if not isinstance(usage,dict):
            source.put(self.sid,'gap',{'missingUsage':identity},{'missing':1});return False
        fields=CAMEL if camel else SNAKE
        values={key:number(usage[name]) for key,name in fields.items() if name in usage}
        if not values:
            source.put(self.sid,'gap',{'missingUsage':identity},{'missing':1});return False
        try:value=source.put(self.sid,'tokens',identity,values)
        except Exception:
            source.put(self.sid,'gap',{'conflictingUsage':identity},{'missing':1});return False
        if not run_id:
            row=self.store.db.execute('SELECT id FROM runs WHERE session_id=? AND turn_id=? ORDER BY rowid DESC LIMIT 1',(self.sid,turn)).fetchone()
            if not row and self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='goal_turns'").fetchone():
                row=self.store.db.execute('SELECT r.id FROM runs r JOIN goal_turns g ON r.id=g.run_id WHERE r.session_id=? AND g.turn_id=?',(self.sid,turn)).fetchone()
            run_id=row[0] if row else None
        with self.store.db:self.store.db.execute('INSERT OR IGNORE INTO statistic_usage VALUES (?,?,?,?,?)',(value['key'],self.sid,run_id,turn,'raw' if camel else 'nativeRecord'))
        return True
    def scan(self,budget=BUDGET):
        session=self.store.row(self.sid);thread=session['thread_id']
        if not thread or not qualified(json.loads(session['engine'])):return 0
        base=self.store.directory/self.sid/'Codex';files=[]
        for name in ('native','archived'):
            root=base/name
            if not root.is_dir() or root.is_symlink():continue
            for parent,dirs,names in os.walk(root,followlinks=False):
                dirs[:]=[d for d in dirs if not (Path(parent)/d).is_symlink()]
                for name in names:
                    if name.endswith('.jsonl') and thread in name:
                        files.append(Path(parent)/name)
                        if len(files)>=64:break
                if len(files)>=64:break
        if not files:return 0
        self.schema();count=0
        for path in sorted(files):
            if budget<=0:break
            if path.is_symlink():continue
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            with os.fdopen(fd,'rb') as handle:
                info=os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode):continue
                # Bind the original rollout, not merely a chosen filename.
                header=handle.readline(MAX_LINE+1)
                try:meta=json.loads(header)
                except (ValueError,UnicodeError):continue
                if meta.get('type')!='session_meta' or meta.get('payload',{}).get('id')!=thread:continue
                key=hashed({'session':self.sid,'thread':thread,'file':str(path.relative_to(base))})
                inode=str(info.st_dev)+':'+str(info.st_ino)
                cursor=self.store.db.execute('SELECT * FROM statistic_history WHERE key=?',(key,)).fetchone()
                offset=cursor['offset'] if cursor and cursor['inode']==inode and cursor['offset']<=info.st_size else len(header)
                skipping=bool(cursor and cursor['inode']==inode and cursor['skipping']);handle.seek(offset)
                while budget>0:
                    before=handle.tell();line=handle.readline(min(MAX_LINE+1,budget));budget-=len(line)
                    if not line:break
                    if skipping:
                        skipping=not line.endswith(b'\n');offset=handle.tell();continue
                    if not line.endswith(b'\n'):
                        if len(line)>MAX_LINE:skipping=True;offset=handle.tell();continue
                        handle.seek(before);break  # An incomplete append is retried by reading only.
                    offset=handle.tell()
                    try:
                        value=json.loads(line)
                        if value.get('type')=='token_usage_record':
                            record=value['payload']
                            if record.get('session_id')==thread and self.ingest(record.get('thread_id'),record.get('turn_id'),record.get('response_id'),record.get('usage')):count+=1
                    except (ValueError,UnicodeError,KeyError,TypeError,ProjectFault):continue
                with self.store.db:self.store.db.execute('INSERT OR REPLACE INTO statistic_history VALUES (?,?,?,?)',(key,inode,offset,int(skipping)))
        return count

class WorkerUsage:
    def __init__(self,worker):self.w=worker;self.task=None;self.closed=False;self.failed=False
    def notify(self,method,params):
        if not qualified(self.w.config['engine']):return
        try:
            if method=='rawResponse/completed':Usage(self.w.store,self.w.session_id).ingest(params.get('threadId'),params.get('turnId'),params.get('responseId'),params.get('usage'),True,self.w.run_id)
            if method in ('rawResponse/completed','thread/tokenUsage/updated','turn/completed') and not self.closed and (not self.task or self.task.done()):self.task=asyncio.create_task(self.collect())
        except Exception:self.failed=True
    async def collect(self):
        await asyncio.sleep(.05)
        try:
            Usage(self.w.store,self.w.session_id).scan();Source(self.w.store).flush()
        except Exception:self.failed=True
    async def close(self):
        self.closed=True
        if self.task:await asyncio.gather(self.task,return_exceptions=True)
    def finalize(self):
        if not qualified(self.w.config['engine']):return
        try:
            usage=Usage(self.w.store,self.w.session_id);usage.scan();usage.schema()
            if self.w.outcome!='completed' or not self.w.store.db.execute('SELECT 1 FROM statistic_usage WHERE run_id=?',(self.w.run_id,)).fetchone():
                Source(self.w.store).put(self.w.session_id,'gap',{'runWithoutResponseUsage':self.w.run_id},{'missing':1})
            Source(self.w.store).flush()
        except Exception:self.failed=True
