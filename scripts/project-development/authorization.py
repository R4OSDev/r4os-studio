"""Private agent admission; the sandbox never receives this socket or identity."""
import json
from pathlib import Path
import sqlite3
from contracts import DevelopmentFault, identity, hash_value
from update_authorization import PERMISSIONS as UPDATE_PERMISSIONS, permission as update_permission

PERMISSIONS = {'build': 'build_project', 'deploy': 'deploy_project', 'execution': 'run_project',
    'wait_build': 'build_project', 'wait_deploy': 'deploy_project', 'wait_execution': 'run_project',
    'vm_start': 'start_project_vm', 'wait_vm_start': 'start_project_vm',
    'read_job': 'read_development_job', 'artifact': 'read_development_job', 'deployment': 'read_development_job',
    'evidence': 'capture_vm', 'evidence_history': 'capture_vm', 'capture': 'capture_vm', 'assess': 'capture_vm',
    'input': 'send_vm_input', 'stop_job': 'stop_development_job', 'complete_check': 'complete_development_job'}

PERMISSIONS.update(UPDATE_PERMISSIONS)

def authorize(store, owner, operation, peer_pid, job=None, stopping=False, recovery_action=None):
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
    if config['revision'] != row[4] or config['projectPins'] != store.project['pins'] or config['engine']['profile'] not in ('studio-tools-v2', 'studio-tools-v3', 'studio-tools-v4', 'studio-tools-v5', 'studio-tools-v6', 'studio-tools-v7', 'studio-tools-v8', 'studio-tools-v9', 'studio-tools-v10','studio-tools-v11'):
        raise DevelopmentFault('This agent run has no matching development profile or settings.', 403)
    if operation in UPDATE_PERMISSIONS and config['engine']['profile'] not in ('studio-tools-v5', 'studio-tools-v6', 'studio-tools-v7', 'studio-tools-v8', 'studio-tools-v9', 'studio-tools-v10','studio-tools-v11'):
        raise DevelopmentFault('Create a new project session for update tools. Existing history remains in its original profile.',403)
    required=update_permission(operation,job,recovery_action) if operation in UPDATE_PERMISSIONS else PERMISSIONS.get(operation)
    if not stopping and required and not config['permissions'].get('studio.' + required, False):
        raise DevelopmentFault('This development tool is disabled for this agent run.', 403)
    if job and (job['projectId'] != store.id or job.get('sessionId') != owner['sessionId']):
        raise DevelopmentFault('This development job belongs to another session.', 403)
    if operation in ('vm_start', 'wait_vm_start') and config['engine']['profile'] not in ('studio-tools-v3', 'studio-tools-v4', 'studio-tools-v5', 'studio-tools-v6', 'studio-tools-v7', 'studio-tools-v8', 'studio-tools-v9', 'studio-tools-v10','studio-tools-v11'):
        raise DevelopmentFault('Create a new session to enable the VM start tool.', 403)
    if operation == 'complete_check' and (config['engine']['profile'] not in ('studio-tools-v4','studio-tools-v5','studio-tools-v6', 'studio-tools-v7', 'studio-tools-v8', 'studio-tools-v9', 'studio-tools-v10','studio-tools-v11') or not all(config['permissions'].get('studio.' + name) for name in ('run_project', 'stop_development_job'))):
        raise DevelopmentFault('Check completion requires its completion, run and stop permissions.', 403)
    action=recovery_action or (job or {}).get('recoveryAction')
    if operation in ('update_recovery','wait_update') and action=='resume-batch' and not config['permissions'].get('studio.commit_update'):
        raise DevelopmentFault('Batch resume may commit/reboot and additionally requires this run\'s commit permission.',403)
    return config


def authorize_job(store, job, allow_stopping=False):
    if not job.get('agentRunId'): return
    path = store.projects / store.id / 'Sessions/Sessions.sqlite'
    if path.resolve(strict=True) != path: raise DevelopmentFault('Invalid delegated session storage.', 403)
    db = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)
    try: row = db.execute('SELECT session_id,state,config,busy FROM runs WHERE id=?', (job['agentRunId'],)).fetchone()
    finally: db.close()
    config = json.loads(row[2]) if row else {}
    permission = update_permission(job['kind'],job) if job['kind'] in UPDATE_PERMISSIONS else PERMISSIONS[job['kind']]
    if (not row or row[0] != job['sessionId'] or (not allow_stopping and row[1] in ('stopping', 'interrupted', 'failed', 'unknown'))
        or config.get('engine', {}).get('profile') not in ('studio-tools-v2', 'studio-tools-v3', 'studio-tools-v4', 'studio-tools-v5', 'studio-tools-v6', 'studio-tools-v7', 'studio-tools-v8', 'studio-tools-v9', 'studio-tools-v10','studio-tools-v11') or config.get('projectPins') != job['pins']
        or not config.get('permissions', {}).get('studio.' + permission)):
        raise DevelopmentFault('This job no longer has an authorized agent snapshot.', 403)
    if job['kind'] in UPDATE_PERMISSIONS:
        if config.get('engine',{}).get('profile') not in ('studio-tools-v5', 'studio-tools-v6', 'studio-tools-v7', 'studio-tools-v8', 'studio-tools-v9', 'studio-tools-v10','studio-tools-v11'):
            raise DevelopmentFault('This original agent profile has no update capability.',403)
        if job.get('recoveryAction')=='resume-batch' and not config['permissions'].get('studio.commit_update'):
            raise DevelopmentFault('This batch resume no longer has its frozen commit permission.',403)
    if job['kind'] == 'vm_start' and (config['engine']['profile'] not in ('studio-tools-v3', 'studio-tools-v4', 'studio-tools-v5', 'studio-tools-v6', 'studio-tools-v7', 'studio-tools-v8', 'studio-tools-v9', 'studio-tools-v10','studio-tools-v11') or not row[3] or row[1] != 'running'):
        raise DevelopmentFault('VM startup requires its original active agent turn.', 403)
