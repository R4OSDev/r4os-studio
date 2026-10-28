"""Read-only provenance of original admitted user text and explicit Goal Play."""
import hashlib
import json
from goal_contract import native_goal


def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value):return hashlib.sha256(encoded(value).encode()).hexdigest()


def text(db,sid,rid,owner):
    try:
        row=db.execute('''SELECT r.request_id,r.payload_hash,r.config,s.thread_id,s.project_id
            FROM runs r JOIN sessions s ON s.id=r.session_id WHERE r.id=? AND s.id=?''',(rid,sid)).fetchone()
        if not row or row[4]!=owner['id']:return None
        request_id,request_hash,raw,thread,_=row;config=json.loads(raw)
        if config.get('owner')!=owner:return None
        execution=config.get('goalExecution')
        if execution:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='goal_commands'").fetchone():return None
            command=db.execute('SELECT fingerprint,payload,state FROM goal_commands WHERE request_id=? AND session_id=?',(request_id,sid)).fetchone()
            if not command or command[2] not in ('pending','confirmed','unknown'):return None
            data=json.loads(command[1]);captured=data.get('_goal')
            client={key:value for key,value in data.items() if not key.startswith('_')}
            goal=native_goal(captured,thread)
            if (not goal or data.get('action')!='play' or set(client)!={'requestId','revision','action','sessionRevision'}
                    or data['requestId']!=request_id or execution.get('requestId')!=request_id
                    or data['sessionRevision']!=config['revision'] or execution.get('objective')!=goal['objective']
                    or execution.get('threadId')!=thread or execution.get('captureSha256')!=digest(captured)
                    or execution.get('commandFingerprint')!=command[0] or digest({'sessionId':sid,**client})!=command[0]):return None
            original={'sessionId':sid,'requestId':request_id,'revision':config['revision'],'mode':'goal','goalRequestId':request_id}
            return goal['objective'] if digest(original)==request_hash else None
        item=db.execute('SELECT payload FROM items WHERE session_id=? AND run_id=? AND item_id=?',(sid,rid,'user-'+request_id)).fetchone()
        if not item:return None
        value=json.loads(item[0])
        if value.get('type')!='user' or value.get('runId')!=rid or not isinstance(value.get('text'),str):return None
        original={'sessionId':sid,'requestId':request_id,'revision':config['revision'],'text':value['text']}
        if 'attachments' in config:
            original['attachments']=config['attachments']
            if value.get('attachments',[])!=config['attachments']:return None
        return value['text'] if digest(original)==request_hash else None
    except (KeyError,TypeError,ValueError,AttributeError):return None


def steering_texts(db,sid,rid,owner):
    """Only private accepted user intents can add mid-run human authority."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='session_messages'").fetchone(): return
    for row in db.execute("SELECT input,input_hash,frozen FROM session_messages WHERE session_id=? AND run_id=? AND mode='steer' AND state='accepted' ORDER BY seq DESC", (sid,rid)):
        try:
            data=json.loads(row[0]);frozen=json.loads(row[2])
            if (frozen['config'].get('owner')==owner and data['target']['runId']==rid
                    and digest({'sessionId':sid,**data})==row[1] and isinstance(data['text'],str)):
                yield data['text']
        except (KeyError,TypeError,ValueError):continue


def live_text(db,sid,rid,owner):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='goal_activations'").fetchone():return None
    rows=db.execute('''SELECT a.binding,a.goal,a.capture_hash,a.config_hash,c.payload,c.fingerprint,c.state,c.stage,r.config
        FROM goal_activations a JOIN goal_commands c USING(request_id) JOIN runs r ON r.id=a.run_id
        WHERE a.session_id=? AND a.run_id=? ORDER BY a.rowid DESC''',(sid,rid))
    for row in rows:
        try:
            binding,captured,cap_hash,config_hash,raw,fingerprint,state,stage,config=row
            binding=json.loads(binding);captured=json.loads(captured);data=json.loads(raw)
            if state!='confirmed' and not (state=='pending' and stage=='native_live_mutation'):continue
            client={k:v for k,v in data.items() if not k.startswith('_')}
            goal=native_goal(captured,binding['threadId'])
            if (binding['owner']==owner and binding['sessionId']==sid and binding['runId']==rid
                    and data.get('action')=='play' and data.get('target')=={k:binding[k] for k in ('runId','threadId','turnId')}
                    and digest(captured)==cap_hash and captured==data.get('_goal') and digest(json.loads(config))==config_hash
                    and digest({'sessionId':sid,**client})==fingerprint and goal):return goal['objective']
        except (KeyError,TypeError,ValueError):continue
    return None


def contexts(db,sid,current_run,owner):
    cursor=db.execute('SELECT id,config FROM runs WHERE session_id=? ORDER BY rowid DESC',(sid,))
    try:
        for row in cursor:
            config=json.loads(row[1])
            # A new Play chooses its own objective. Older Play objectives remain
            # verifiable for existing receipts, not fresh implicit cleanup grants.
            if config.get('goalExecution') and row[0]!=current_run:continue
            if row[0]==current_run:
                live=live_text(db,sid,row[0],owner)
                if live is not None:yield {'runId':row[0],'text':live}
            for direct in steering_texts(db,sid,row[0],owner):yield {'runId':row[0],'text':direct}
            value=text(db,sid,row[0],owner)
            if value is not None:yield {'runId':row[0],'text':value}
    finally:cursor.close()
