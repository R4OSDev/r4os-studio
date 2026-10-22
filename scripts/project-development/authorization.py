"""Private agent admission; the sandbox never receives this socket or identity."""
import json
from pathlib import Path
import sqlite3
from contracts import DevelopmentFault, identity, hash_value

PERMISSIONS = {'build': 'build_project', 'deploy': 'deploy_project', 'execution': 'run_project',
    'read_job': 'read_development_job', 'artifact': 'read_development_job', 'deployment': 'read_development_job',
    'evidence': 'capture_vm', 'evidence_history': 'capture_vm', 'capture': 'capture_vm', 'assess': 'capture_vm',
    'input': 'send_vm_input', 'stop_job': 'stop_development_job'}

def authorize(store, owner, operation, peer_pid, job=None, stopping=False):
    if operation not in (*PERMISSIONS, 'options', 'settings', 'cancel_owned'):
        raise DevelopmentFault('This operation is not available to agent tools.', 403)
    if not isinstance(owner, dict) or set(owner) != {'sessionId', 'agentRunId'}:
        raise DevelopmentFault('Invalid delegated development owner.', 400)
    for v in owner.values(): identity(v)
    path = store.projects / store.id / 'Sessions/Sessions.sqlite'
    if path.resolve(strict=True) != path: raise DevelopmentFault('Invalid delegated session storage.', 403)
    db = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)
    try:
        row = db.execute('SELECT r.busy,r.state,r.worker,r.config,s.revision FROM runs r JOIN sessions s ON s.id=r.session_id WHERE r.id=? AND r.session_id=?', (owner['agentRunId'], owner['sessionId'])).fetchone()
    finally: db.close()
    if not row or not row[0] or (row[1] == 'stopping' and not stopping) or json.loads(row[2] or '{}').get('pid') != peer_pid:
        raise DevelopmentFault('This request does not belong to the active agent worker.', 403)
    from lease import birth
    worker = json.loads(row[2] or '{}')
    try:
        if worker.get('birth') != birth(peer_pid): raise ValueError()
    except (OSError, ValueError): raise DevelopmentFault('The agent worker process identity changed.', 403)
    config = json.loads(row[3])
    if config['revision'] != row[4] or config['projectPins'] != store.project['pins'] or config['engine']['profile'] != 'studio-tools-v2':
        raise DevelopmentFault('This agent run has no matching development profile or settings.', 403)
    if not stopping and operation in PERMISSIONS and not config['permissions'].get('studio.' + PERMISSIONS[operation], False):
        raise DevelopmentFault('This development tool is disabled for this agent run.', 403)
    if job and (job['projectId'] != store.id or job.get('sessionId') != owner['sessionId']):
        raise DevelopmentFault('This development job belongs to another session.', 403)
    return config


def authorize_job(store, job, allow_stopping=False):
    if not job.get('agentRunId'): return
    path = store.projects / store.id / 'Sessions/Sessions.sqlite'
    if path.resolve(strict=True) != path: raise DevelopmentFault('Invalid delegated session storage.', 403)
    db = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)
    try: row = db.execute('SELECT session_id,state,config FROM runs WHERE id=?', (job['agentRunId'],)).fetchone()
    finally: db.close()
    config = json.loads(row[2]) if row else {}
    permission = PERMISSIONS[job['kind']]
    if (not row or row[0] != job['sessionId'] or (not allow_stopping and row[1] in ('stopping', 'interrupted', 'failed', 'unknown'))
        or config.get('engine', {}).get('profile') != 'studio-tools-v2' or config.get('projectPins') != job['pins']
        or not config.get('permissions', {}).get('studio.' + permission)):
        raise DevelopmentFault('This job no longer has an authorized agent snapshot.', 403)
