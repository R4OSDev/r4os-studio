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


def contexts(db,sid,current_run,owner):
    cursor=db.execute('SELECT id,config FROM runs WHERE session_id=? ORDER BY rowid DESC',(sid,))
    try:
        for row in cursor:
            config=json.loads(row[1])
            # A new Play chooses its own objective. Older Play objectives remain
            # verifiable for existing receipts, not fresh implicit cleanup grants.
            if config.get('goalExecution') and row[0]!=current_run:continue
            value=text(db,sid,row[0],owner)
            if value is not None:yield {'runId':row[0],'text':value}
    finally:cursor.close()
