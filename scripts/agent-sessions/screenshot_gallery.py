"""Bounded projection of registered agent captures; never captures or copies PNGs."""
import base64
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import uuid

from session_store import encode,identity
from store import ProjectFault

BATCH=256
LIMIT=32
BOUNDS=json.loads((Path(__file__).resolve().parents[2]/'shared/development-host.json').read_text())['limits']


def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS gallery_state(session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS gallery_entries(session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,publication INTEGER NOT NULL,evidence_id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(session_id,publication),UNIQUE(session_id,evidence_id))')
    db.execute('CREATE TABLE IF NOT EXISTS gallery_gaps(session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,publication INTEGER NOT NULL,evidence_id TEXT NOT NULL,PRIMARY KEY(session_id,publication))')


def has(db,table):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None


def token(state,sid,watermark,before):
    raw=encode({'schema':1,'session':sid,'source':state['source'],'watermark':watermark,'before':before}).encode()
    signed=base64.urlsafe_b64encode(raw).decode().rstrip('=')
    return signed+'.'+hmac.new(bytes.fromhex(state['secret']),signed.encode(),hashlib.sha256).hexdigest()


def cursor(state,sid,value):
    try:
        if not isinstance(value,str) or not 1<=len(value)<=1024:raise ValueError()
        raw,signature=value.split('.')
        expected=hmac.new(bytes.fromhex(state['secret']),raw.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature,expected):raise ValueError()
        data=json.loads(base64.urlsafe_b64decode(raw+'='*((-len(raw))%4)))
        if (set(data)!={'schema','session','source','watermark','before'} or data['schema']!=1 or data['session']!=sid
            or data['source']!=state['source'] or type(data['watermark']) is not int or type(data['before']) is not int
            or not 0<data['before']<=data['watermark']<=state['scanned']):raise ValueError()
        return data['watermark'],data['before']
    except (ValueError,TypeError,KeyError,UnicodeError):raise ProjectFault('The screenshot cursor changed or expired. Reload this gallery.',409) from None


def source_rows(db,where,args):
    return db.execute('SELECT e.rowid AS publication,e.id,e.job_id,e.payload,json_extract(j.payload,\'$.sessionId\') AS job_session,'
        'json_extract(j.payload,\'$.projectId\') AS project,json_extract(j.payload,\'$.target\') AS target '
        'FROM evidence e LEFT JOIN jobs j ON j.id=e.job_id WHERE '+where+' ORDER BY e.rowid LIMIT '+str(BATCH),args).fetchall()


def project(store,source,rows,sid):
    """One batched original-tool read, not a job/transcript request per image."""
    parsed=[];runs=set()
    for row in rows:
        if len(row['payload'].encode())>32768:parsed.append((row,None));continue
        try:
            value=json.loads(row['payload']);observer=value.get('observer') if isinstance(value,dict) else None
            if isinstance(observer,dict) and observer.get('sessionId')==sid:runs.add(identity(observer.get('agentRunId')))
            parsed.append((row,value))
        except (ValueError,ProjectFault):parsed.append((row,None))
    tools={};requests={}
    if runs:
        marks=','.join('?' for _ in runs)
        jobs=sorted({row['job_id'] for row,_ in parsed});job_marks=','.join('?' for _ in jobs)
        query='SELECT t.run_id,t.call_id,t.tool,json_extract(t.intent,\'$.jobId\') AS job_id,json_extract(t.intent,\'$.action\') AS action,json_type(t.intent,\'$.observeAfterStep\') AS observe,json_extract(t.result,\'$.image\') AS image FROM tools t JOIN runs r ON r.id=t.run_id WHERE r.session_id=? AND t.run_id IN ('+marks+") AND t.tool IN ('studio_capture_vm','studio_send_vm_input') AND json_extract(t.intent,'$.jobId') IN ("+job_marks+')'
        for row in store.db.execute(query,(sid,*sorted(runs),*jobs)):
            try:
                arguments={'jobId':row['job_id']};result={'image':json.loads(row['image'])} if row['image'] else None
                if row['tool']=='studio_capture_vm' and row['action'] not in (None,'capture'):continue
                if row['tool']=='studio_send_vm_input' and row['observe'] is None:continue
                request=str(uuid.uuid5(uuid.UUID(row['run_id']),'development:'+row['call_id']))
                tools.setdefault(row['run_id'],[]).append((row['call_id'],request,row['tool'],arguments,result));requests[request]=None
            except (ValueError,TypeError,AttributeError):continue
    if requests and has(source,'actions'):
        # Chunk original receipts independently of the SQLite variable limit.
        keys=list(requests)
        for start in range(0,len(keys),256):
            batch=keys[start:start+256]
            for row in source.execute('SELECT id,job_id,state,result FROM actions WHERE id IN ('+','.join('?' for _ in batch)+')',batch):
                if row['state']=='completed' and row['result']:
                    try:requests[row['id']]={'job':row['job_id'],'result':json.loads(row['result'])}
                    except ValueError:pass
    for row,value in parsed:
        relevant=row['job_session']==sid
        if not isinstance(value,dict):yield row,None,relevant;continue
        observer=value.get('observer')
        if value.get('kind')!='screenshot' or not isinstance(observer,dict) or observer.get('sessionId')!=sid:
            yield row,None,False;continue
        valid=(relevant and row['project']==store.owner_id and value.get('projectId')==store.owner_id and value.get('jobId')==row['job_id']
            and value.get('id')==row['id'] and value.get('source')=='qmp-png' and value.get('scope')=='assigned-vm-screen'
            and type(value.get('bytes')) is int and 0<value['bytes']<=BOUNDS['screenshotBytes']
            and type(value.get('width')) is int and 0<value['width']<=BOUNDS['screenshotMaxWidth']
            and type(value.get('height')) is int and 0<value['height']<=BOUNDS['screenshotMaxHeight']
            and isinstance(value.get('sha256'),str) and len(value['sha256'])==64 and all(c in '0123456789abcdef' for c in value['sha256']))
        match=None
        for call,request,tool,arguments,result in tools.get(observer.get('agentRunId'),[]):
            if arguments.get('jobId')!=row['job_id']:continue
            operation='capture' if tool=='studio_capture_vm' else 'input';origin=value.get('captureOrigin') or {}
            direct=isinstance(origin,dict) and origin.get('requestId')==request and origin.get('operation')==operation
            receipt=requests.get(request);action=(receipt or {}).get('result') or {}
            action_match=(receipt or {}).get('job')==row['job_id'] and action.get('evidenceId' if operation=='capture' else 'observationId')==row['id']
            image=result.get('image') if isinstance(result,dict) else None
            tool_match=isinstance(image,dict) and all(image.get(k)==value.get(k) for k in ('id','jobId','projectId','sha256','bytes','observer'))
            if direct or action_match or tool_match:
                match={'runId':observer['agentRunId'],'toolCallId':call,'requestId':request,'tool':tool.replace('studio_','studio.',1)};break
        if not valid or not match:yield row,None,True;continue
        target=json.loads(row['target']) if row['target'] else {}
        vm=value.get('vmId') or (target.get('vmId') if target.get('bootId')==value.get('bootId') else None)
        entry={'id':row['id'],'projectId':store.owner_id,'sessionId':sid,'jobId':row['job_id'],'publication':row['publication'],
            **match,'vmId':vm,'bootId':value.get('bootId'),'createdAt':value.get('createdAt'),
            'width':value['width'],'height':value['height'],'bytes':value['bytes'],'sha256':value['sha256'],
            'source':'agent-vm-capture','reference':'studio-image:'+row['job_id']+'/'+row['id'],
            **({'diagnosticOnly':True,'contentUnconfirmed':True} if value.get('diagnosticOnly') is True else {})}
        yield row,entry,False


def refresh(store,sid):
    from session_delete import read_db
    path=store.workspace.parent/'Development/Development.sqlite'
    if not path.exists() and not path.is_symlink():return None
    info=path.stat();source_key=hashlib.sha256(encode([info.st_dev,info.st_ino]).encode()).hexdigest()
    with read_db(path) as source:
        source.execute('BEGIN')
        if not has(source,'evidence'):return None
        maximum=source.execute('SELECT COALESCE(MAX(rowid),0) FROM evidence').fetchone()[0]
        with store.db:
            store.db.execute('BEGIN IMMEDIATE');schema(store.db)
            found=store.db.execute('SELECT payload FROM gallery_state WHERE session_id=?',(sid,)).fetchone()
            state=json.loads(found[0]) if found else None
            anchor=source.execute('SELECT id FROM evidence WHERE rowid=?',((state or {}).get('scanned',0),)).fetchone()
            if not state or state['source']!=source_key or state['scanned']>maximum or state['scanned'] and (not anchor or anchor[0]!=state['anchor']):
                store.db.execute('DELETE FROM gallery_entries WHERE session_id=?',(sid,));store.db.execute('DELETE FROM gallery_gaps WHERE session_id=?',(sid,))
                state={'source':source_key,'secret':secrets.token_hex(32),'scanned':0,'anchor':None,'revision':0,'retryAfter':0}
            rows=source_rows(source,'e.rowid>? AND e.rowid<=?',(state['scanned'],maximum))
            retry=store.db.execute('SELECT publication FROM gallery_gaps WHERE session_id=? AND publication>? ORDER BY publication LIMIT 32',(sid,state['retryAfter'])).fetchall()
            if not retry:state['retryAfter']=0
            else:
                state['retryAfter']=retry[-1][0]
                rows+=source_rows(source,'e.rowid IN ('+','.join('?' for _ in retry)+')',tuple(r[0] for r in retry))
            changed=False
            for row,entry,gap in project(store,source,rows,sid):
                if row['publication']>state['scanned']:state.update(scanned=row['publication'],anchor=row['id']);changed=True
                if entry:
                    store.db.execute('DELETE FROM gallery_gaps WHERE session_id=? AND publication=?',(sid,row['publication']))
                    old=store.db.execute('SELECT payload FROM gallery_entries WHERE session_id=? AND publication=?',(sid,row['publication'])).fetchone()
                    if old and json.loads(old[0])!=entry:raise ProjectFault('An original screenshot reference changed. Existing evidence was preserved.',409)
                    if not old:store.db.execute('INSERT INTO gallery_entries VALUES (?,?,?,?)',(sid,row['publication'],row['id'],encode(entry)));changed=True
                elif gap:
                    if store.db.execute('INSERT OR IGNORE INTO gallery_gaps VALUES (?,?,?)',(sid,row['publication'],row['id'])).rowcount:changed=True
            if changed:state['revision']+=1
            state['complete']=state['scanned']>=maximum
            store.db.execute('INSERT INTO gallery_state VALUES (?,?) ON CONFLICT(session_id) DO UPDATE SET payload=excluded.payload',(sid,encode(state)))
            return state


def page(store,sid,after=None,limit=LIMIT):
    store.row(sid)
    if type(limit) is not int or not 1<=limit<=LIMIT:raise ProjectFault('Invalid screenshot page size.',400)
    base={'schema':1,'owner':{'type':store.owner_type,'id':store.owner_id},'sessionId':sid,'items':[],'nextCursor':None,'revision':0,'watermark':0,
        'coverage':{'complete':True,'unqualified':0},'available':store.owner_type=='project','reason':None}
    if store.owner_type!='project':return {**base,'reason':'VM screenshots are not available for skill sessions.'}
    state=refresh(store,sid)
    if not state:
        if after:raise ProjectFault('The screenshot cursor expired. Reload this gallery.',409)
        return base
    watermark,before=cursor(state,sid,after) if after else (state['scanned'],state['scanned']+1)
    rows=store.db.execute('SELECT publication,payload FROM gallery_entries WHERE session_id=? AND publication<=? AND publication<? ORDER BY publication DESC LIMIT ?',
        (sid,watermark,before,limit+1)).fetchall()
    gaps=store.db.execute('SELECT COUNT(*) FROM gallery_gaps WHERE session_id=?',(sid,)).fetchone()[0]
    return {**base,'items':[json.loads(r['payload']) for r in rows[:limit]],'revision':state['revision'],'watermark':watermark,
        'nextCursor':token(state,sid,watermark,rows[limit-1]['publication']) if len(rows)>limit else None,
        'coverage':{'complete':state['complete'],'unqualified':gaps}}


def member(store,sid,job_id,evidence_id):
    store.row(sid);identity(job_id);identity(evidence_id)
    if store.owner_type!='project':raise ProjectFault('This session has no VM screenshots.',404)
    row=store.db.execute('SELECT payload FROM gallery_entries WHERE session_id=? AND evidence_id=?',(sid,evidence_id)).fetchone() if has(store.db,'gallery_entries') else None
    if not row:
        refresh(store,sid)
        row=store.db.execute('SELECT payload FROM gallery_entries WHERE session_id=? AND evidence_id=?',(sid,evidence_id)).fetchone() if has(store.db,'gallery_entries') else None
    value=json.loads(row[0]) if row else None
    if not value or value['jobId']!=job_id:raise ProjectFault('This image is not a registered agent screenshot for this session.',404)
    return value
