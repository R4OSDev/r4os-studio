"""Bounded read-only original job references within exactly one own session."""
import json
import re
import sqlite3
import uuid
from contextlib import closing

class JobReferenceFault(ValueError):
    def __init__(self, message, code=409):
        super().__init__(message)
        self.code = code


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', value):
        raise JobReferenceFault('Invalid development identity.', 400)
    return str(uuid.UUID(value))

KINDS = ('build','package','update_probe','update_transfer','update_install','update_commit',
    'update_verify','update_recovery','deploy','execution','vm_start','vm_stop','vm_restart','ssh')


def validate(query):
    if not isinstance(query, dict) or set(query) - {'limit','before','requestId','originRunId','toolCallId','kind'}:
        raise JobReferenceFault('Use bounded own-session job lookup fields.', 400)
    if type(query.get('limit',10)) is not int or not 1 <= query.get('limit',10) <= 25:
        raise JobReferenceFault('Job lookup returns 1..25 references per page.', 400)
    if type(query.get('before',2**53-1)) is not int or not 1 <= query.get('before',2**53-1) <= 2**53-1:
        raise JobReferenceFault('Use the original job lookup page cursor.', 400)
    if 'kind' in query and query['kind'] not in KINDS: raise JobReferenceFault('Unknown job kind.', 400)
    if 'requestId' in query: identity(query['requestId'])
    if ('originRunId' in query) != ('toolCallId' in query):
        raise JobReferenceFault('Original tool lookup needs both originRunId and toolCallId.', 400)
    if 'originRunId' in query:
        identity(query['originRunId'])
        call = query['toolCallId']
        if not isinstance(call,str) or not 1 <= len(call.encode()) <= 256 or any(ord(c) <= 32 or ord(c) == 127 for c in call):
            raise JobReferenceFault('Use the original bounded tool-call identity.', 400)
        if 'requestId' in query: raise JobReferenceFault('Choose requestId or the original run/tool-call pair.', 400)
    return query


def listing(projects, project_id, session_id, query=None):
    project_id = identity(project_id); session_id = identity(session_id)
    query = validate({} if query is None else query)
    root = projects / project_id
    session_path = root/'Sessions/Sessions.sqlite'
    if not session_path.is_file(): raise JobReferenceFault('This project session is unavailable.',404)
    if session_path.resolve(strict=True) != session_path or session_path.stat().st_nlink != 1:
        raise JobReferenceFault('Invalid own-session storage.',403)
    with closing(sqlite3.connect(session_path.as_uri()+'?mode=ro',uri=True)) as session_db:
        if not session_db.execute('SELECT 1 FROM sessions WHERE id=?',(session_id,)).fetchone():
            raise JobReferenceFault('This session does not belong to the selected project.',404)
        original_request = query.get('requestId')
        if 'originRunId' in query:
            run = session_db.execute('SELECT 1 FROM runs WHERE id=? AND session_id=?',(query['originRunId'],session_id)).fetchone()
            tool = session_db.execute('SELECT tool FROM tools WHERE run_id=? AND call_id=?',
                                      (query['originRunId'],query['toolCallId'])).fetchone()
            if not run or not tool or tool[0] not in ('studio_build_project','studio_deploy_project','studio_run_project','studio_start_project_vm','studio_stop_project_vm','studio_restart_project_vm'):
                raise JobReferenceFault('The original admission call does not belong to this session.',404)
            original_request = str(uuid.uuid5(uuid.UUID(query['originRunId']),'development:'+query['toolCallId']))
    result = {'schemaVersion':1,'projectId':project_id,'sessionId':session_id,'readOnly':True,
              'entries':[],'nextBefore':None,'hasMore':False}
    path = root/'Development/Development.sqlite'
    if not path.exists(): return result
    if path.resolve(strict=True) != path or path.stat().st_nlink != 1:
        raise JobReferenceFault('Invalid original job storage.',403)
    clauses = ["json_extract(payload,'$.sessionId')=?",'rowid<?']
    parameters = [session_id,query.get('before',2**53-1)]
    if original_request:
        clauses.append('request_id=?');parameters.append(original_request)
    if 'kind' in query:
        clauses.append('kind=?');parameters.append(query['kind'])
    limit = query.get('limit',10)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        rows = db.execute('SELECT rowid,id,request_id,substr(payload,1,2097153) FROM jobs WHERE '
            +' AND '.join(clauses)+' ORDER BY rowid DESC LIMIT ?',(*parameters,limit+1)).fetchall()
    for sequence,job_id,request_id,payload in rows[:limit]:
        if len(payload.encode()) > 2097152: raise JobReferenceFault('The original job metadata exceeds its limit.')
        job = json.loads(payload)
        if job.get('projectId') != project_id or job.get('sessionId') != session_id or job.get('id') != job_id:
            raise JobReferenceFault('The original job ownership receipt is inconsistent.',403)
        if (job.get('requestId') not in (None,request_id) or job.get('kind') not in KINDS
            or job.get('state') not in ('queued','starting','running','stopping','completed','failed','interrupted','unknown')
            or type(job.get('revision')) is not int or not 1 <= job['revision'] <= 2**53-1):
            raise JobReferenceFault('The original job metadata is inconsistent.')
        identity(job_id); identity(request_id)
        for key in ('artifactId','deploymentId','agentRunId'):
            if job.get(key) is not None: identity(job[key])
        for key in ('createdAt','completedAt'):
            if job.get(key) is not None and (not isinstance(job[key],str) or len(job[key]) > 64):
                raise JobReferenceFault('The original job timestamp is invalid.')
        if 'originRunId' in query and job.get('agentRunId') != query['originRunId']:
            raise JobReferenceFault('The original run/job binding is inconsistent.',403)
        entry = {k:job.get(k) for k in ('id','kind','state','revision','artifactId','deploymentId','agentRunId','createdAt','completedAt')}
        entry['requestId'] = request_id
        phase = job.get('phase')
        if isinstance(phase,str) and re.fullmatch('[a-zA-Z0-9_-]{1,64}',phase): entry['phase'] = phase
        if result['entries'] and len(json.dumps({**result,'entries':[*result['entries'],entry]},separators=(',',':')).encode()) > 8000:
            break
        result['entries'].append(entry)
    if len(rows) > len(result['entries']):
        result.update(nextBefore=rows[len(result['entries'])-1][0],hasMore=True)
    return result
