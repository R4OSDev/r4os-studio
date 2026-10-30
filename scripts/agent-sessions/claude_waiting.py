"""Explicit after-response targets; never pretend simultaneous native delivery."""
import json
import os
from pathlib import Path

from attachment_store import birth
from session_store import encode,identity,now
from store import ProjectFault


def validate(value):
    if not isinstance(value,dict) or set(value)!={'runId','nativeSessionId'}:
        raise ProjectFault('An after-response message needs its original Claude run and native session.',400)
    identity(value['runId']);identity(value['nativeSessionId'])
    return value


def public_target(store,run):
    """Read metadata only; admission still checks the actual original lease.

    Do not call store.get/ClaudeHistory.get from run_present: they present this
    same run recursively. No history files or provider credentials are read.
    """
    try:
        config=json.loads(run['config']);meta=json.loads(run['worker'] or '{}')
        if (config['engine'].get('kind')!='claude-code' or not run['busy'] or run['state']!='running'
            or type(meta.get('pid')) is not int or meta['pid']<=0 or not meta.get('birth') or not meta.get('release')
            or birth(meta['pid'])!=meta['birth'] or Path('/proc',str(meta['pid'])).stat().st_uid!=os.geteuid()):return None
        row=store.row(run['session_id']);engine=json.loads(row['engine'])
        if not store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='claude_sessions'").fetchone():return None
        saved=store.db.execute('SELECT data FROM claude_sessions WHERE session_id=?',(row['id'],)).fetchone()
        if not saved:return None
        value=json.loads(saved[0])
        if (engine!=config['engine'] or value.get('schema')!=1 or value.get('phase') not in ('opening','active')
            or value.get('sessionId')!=row['id'] or value.get('activeRunId')!=run['id']
            or value.get('owner')!={'type':store.owner_type,'id':store.owner_id}
            or value.get('providerId')!=config['providerId'] or value.get('runtime')!=engine.get('claude')
            or value.get('accountIdentity')!=config.get('claudeProvider',{}).get('accountIdentity')):return None
        return {'runId':run['id'],'nativeSessionId':engine['claude']['nativeSessionId']}
    except (KeyError,ValueError,TypeError,OSError):return None


def bind(value,context):
    validate(value);source=context.get('source')
    if not source or value!={'runId':source['runId'],'nativeSessionId':context['nativeSessionId']}:
        raise ProjectFault('The original Claude response ended or changed. The message was not moved to another response.',409)
    return value


def saved_message(store,sid,frozen):
    from claude_messages import digest
    row=store.db.execute('SELECT * FROM session_messages WHERE request_id=? AND session_id=?',
        (frozen['runInput']['requestId'],sid)).fetchone()
    data=json.loads(row['input']) if row else {}
    if (not row or row['mode']!='queue' or data.get('afterRun')!=frozen.get('afterRun')
        or json.loads(row['frozen'])!=frozen or row['input_hash']!=digest({'sessionId':sid,**data})):
        raise ProjectFault('The original after-response message binding changed. Its input was not replayed.',409)


def record_resume(store,sid,command,command_hash):
    """A new explicit queue control may authorize only still-unsent inputs.

    This is not native acceptance or account/quota release. Its original time
    must follow a failed/interrupted source before that input can be admitted.
    """
    from claude_messages import digest
    rows=store.db.execute("SELECT request_id,frozen FROM session_messages WHERE session_id=? AND state='queued'",(sid,)).fetchall()
    selected=[(row,json.loads(row['frozen'])) for row in rows if 'afterRun' in json.loads(row['frozen'])]
    if not selected:return
    store.db.execute('''CREATE TABLE IF NOT EXISTS claude_wait_resumes(message_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id),request_id TEXT NOT NULL,command_hash TEXT NOT NULL,
        frozen_hash TEXT NOT NULL,command TEXT NOT NULL,created_at TEXT NOT NULL)''')
    for row,frozen in selected:
        bind(frozen['afterRun'],frozen['claudeQueue'])
        store.db.execute('INSERT INTO claude_wait_resumes VALUES (?,?,?,?,?,?,?) ON CONFLICT(message_id) DO UPDATE SET request_id=excluded.request_id,command_hash=excluded.command_hash,frozen_hash=excluded.frozen_hash,command=excluded.command,created_at=excluded.created_at',
            (row['request_id'],sid,command['requestId'],command_hash,digest(frozen),encode(command),now()))


def resumed_after_source(store,sid,frozen,run):
    from claude_messages import digest
    if not run['completed_at'] or run['state'] not in ('failed','interrupted'):return False
    if not store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='claude_wait_resumes'").fetchone():return False
    row=store.db.execute('SELECT * FROM claude_wait_resumes WHERE message_id=? AND session_id=?',
        (frozen['runInput']['requestId'],sid)).fetchone()
    if not row or row['frozen_hash']!=digest(frozen) or row['created_at']<=run['completed_at']:return False
    command=json.loads(row['command'])
    if (set(command)!={'requestId','revision','action'} or command['requestId']!=row['request_id'] or command['action']!='resume'
        or type(command['revision']) is not int or command['revision']<1
        or digest({'sessionId':sid,**command})!=row['command_hash']):return False
    original=store.db.execute("SELECT payload_hash FROM requests WHERE request_id=? AND session_id=? AND kind='message_control'",(row['request_id'],sid)).fetchone()
    return bool(original and original[0]==row['command_hash'])
