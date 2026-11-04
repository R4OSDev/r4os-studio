"""Original session/run ownership for independent managed MCP services."""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import types
import uuid

from owner import skills_root
from skill_mcp_client import McpFault, encoded, directory

RIGHTS=('studio.exec_command','studio.read_file','studio.write_file','studio.read_attachment',
        'studio.skill_call','studio.skill_discover','studio.skill_network')


def identity(value):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}',value):
        raise McpFault('Invalid managed analysis identity.')
    return value


def birth(pid):
    try:return (Path('/proc')/str(pid)/'stat').read_text().rsplit(') ',1)[1].split()[19]
    except (OSError,IndexError):return None


def scope(config,entry):
    value=dict(schema=1,skillId=identity(entry['id']),packageHash=entry['activeHash'],mcp=entry['mcp'],
               permissions={key:config['permissions'].get(key) is True for key in RIGHTS},
               attachments=config.get('attachmentFileAccess'))
    return hashlib.sha256(encoded(value)).hexdigest()


def service_id(session_id,config,entry,generation=None):
    name=scope(config,entry)+((':'+identity(generation)) if generation else '')
    return str(uuid.uuid5(uuid.UUID(identity(session_id)),name))


def registry(projects,ident):
    return skills_root(projects)/'.mcp'/identity(ident)


def paths(projects,launch,create=False):
    kind=launch['ownerType'];owner=identity(launch['ownerId']);sid=identity(launch['sessionId'])
    if kind not in ('project','skill'):raise McpFault('Invalid managed analysis owner.')
    parent=(Path(projects) if kind=='project' else skills_root(projects))/owner
    if parent.resolve(strict=True)!=parent:raise McpFault('The analysis owner directory changed.')
    workspace=parent/'Workspace';sessions=parent/'Sessions';database=sessions/'Sessions.sqlite'
    for path in (workspace,sessions,database):
        if path.resolve(strict=True)!=path:raise McpFault('A managed analysis owner path is linked or missing.')
    state=sessions/sid/'SkillMCP'/identity(launch['skillId'])/identity(launch['serviceId'])
    if create:directory(state)
    return workspace,sessions,database,state


def original(projects,launch,run_id,peer,uid,effects=True):
    workspace,sessions,database,state=paths(projects,launch)
    db=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=5,check_same_thread=False);db.row_factory=sqlite3.Row
    try:
        row=db.execute('SELECT * FROM runs WHERE id=? AND session_id=?',(identity(run_id),launch['sessionId'])).fetchone()
        session=db.execute('SELECT * FROM sessions WHERE id=? AND project_id=?',(launch['sessionId'],launch['ownerId'])).fetchone()
        from session_lifetime import state as retired
        if row is None or session is None or effects and retired(db,launch['sessionId']):
            raise McpFault('The original analysis session or run is unavailable.')
        worker=json.loads(row['worker'] or '{}');config=json.loads(row['config'])
        if (peer[1]!=uid or worker.get('pid')!=peer[0] or birth(peer[0])!=worker.get('birth')
                or (Path('/proc')/str(peer[0])).stat().st_uid!=uid):
            raise McpFault('This analysis request does not come from its original live Studio worker.')
        if effects and (not row['busy'] or row['state']=='stopping'):
            raise McpFault('The original run no longer admits analysis effects.')
        entry=next((e for e in config.get('skillAccess',{}).get('entries',[]) if e['id']==launch['skillId'] and e.get('mcp')),None)
        if entry is None or scope(config,entry)!=launch['namespaceHash'] or service_id(launch['sessionId'],config,entry,launch.get('generation'))!=launch['serviceId']:
            raise McpFault('The original frozen analysis namespace or runtime differs.')
        if effects and not all(config['permissions'].get(k) for k in ('studio.exec_command','studio.read_file')):
            raise McpFault('Managed analysis requires the original execution and file permissions.')
        store=types.SimpleNamespace(projects=Path(projects),workspace=workspace,directory=sessions,db=db,
            owner_type=launch['ownerType'],owner_id=launch['ownerId'],selected_profile=launch['ownerType'])
        value=types.SimpleNamespace(store=store,config=config,session_id=launch['sessionId'],run_id=run_id,
            stopping=False,lease=types.SimpleNamespace(closed=False),entry=entry,state=state)
        return value
    except BaseException:
        db.close();raise


def launch_record(worker,entry,generation):
    ident=service_id(worker.session_id,worker.config,entry,generation)
    return dict(schema=1,serviceId=ident,ownerType=worker.store.owner_type,ownerId=worker.store.owner_id,
                sessionId=worker.session_id,skillId=entry['id'],namespaceHash=scope(worker.config,entry),generation=generation)
