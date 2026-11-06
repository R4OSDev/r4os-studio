"""Private agent admission; the sandbox never receives this socket or identity."""
import json
from pathlib import Path
import sqlite3
from contracts import DevelopmentFault, identity, hash_value
from update_authorization import PERMISSIONS as UPDATE_PERMISSIONS, permission as update_permission

PERMISSIONS = {'build': 'build_project', 'deploy': 'deploy_project', 'execution': 'run_project',
    'wait_build': 'build_project', 'wait_deploy': 'deploy_project', 'wait_execution': 'run_project',
    'ssh': 'run_vm_command', 'vm_start': 'start_project_vm', 'wait_vm_start': 'start_project_vm', 'vm_stop':'stop_project_vm','vm_restart':'restart_project_vm','wait_vm_stop':'stop_project_vm','wait_vm_restart':'restart_project_vm',
    'read_job': 'read_development_job', 'artifact': 'read_development_job', 'deployment': 'read_development_job',
    'evidence': 'capture_vm', 'evidence_history': 'capture_vm', 'capture': 'capture_vm', 'assess': 'capture_vm',
    'input': 'send_vm_input', 'stop_job': 'stop_development_job', 'complete_check': 'complete_development_job'}
PERMISSIONS['window'] = 'control_app_window'
PERMISSIONS['session_jobs'] = 'read_development_job'
PERMISSIONS['observation'] = PERMISSIONS['wait_observation'] = 'capture_vm'

PERMISSIONS.update(UPDATE_PERMISSIONS)


def permits(config, project_id, *tools):
    """Frozen owner and explicit permissions, independent of former profiles."""
    return (isinstance(config, dict) and config.get('owner') == {'type': 'project', 'id': project_id}
        and all(config.get('permissions', {}).get('studio.' + tool) is True for tool in tools))


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
    if config['revision'] != row[4] or config['projectPins'] != store.project['pins'] or config.get('owner', {}).get('type') != 'project':
        raise DevelopmentFault('This agent run has no matching project owner or settings.', 403)
    if operation in UPDATE_PERMISSIONS and config.get('owner', {}).get('type') != 'project':
        raise DevelopmentFault('Update tools require an app project.',403)
    required=update_permission(operation,job,recovery_action) if operation in UPDATE_PERMISSIONS else PERMISSIONS.get(operation)
    if not stopping and required and not config['permissions'].get('studio.' + required, False):
        raise DevelopmentFault('This development tool is disabled for this agent run.', 403)
    if operation == 'window' and (config.get('owner', {}).get('type') != 'project' or not config['permissions'].get('studio.run_project')):
        raise DevelopmentFault('Window control requires an app project and its own run/control permissions.', 403)
    if job and (job['projectId'] != store.id or job.get('sessionId') != owner['sessionId']):
        raise DevelopmentFault('This development job belongs to another session.', 403)
    if operation in ('vm_stop','vm_restart','wait_vm_stop','wait_vm_restart'):
        if row[1]!='running' or not row[0]:raise DevelopmentFault('VM lifecycle requires its original active agent run.',403)
        if operation in ('vm_restart','wait_vm_restart') and not permits(config,store.id,'start_project_vm','stop_project_vm','restart_project_vm'):
            raise DevelopmentFault('Restart additionally requires the original start and stop permissions.',403)
    if operation in ('vm_start', 'wait_vm_start') and config.get('owner', {}).get('type') != 'project':
        raise DevelopmentFault('VM startup requires an app project.', 403)
    if operation == 'complete_check' and (config.get('owner', {}).get('type') != 'project' or not all(config['permissions'].get('studio.' + name) for name in ('run_project', 'stop_development_job'))):
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
    try: row = db.execute('SELECT r.session_id,r.state,r.config,r.busy,r.worker,s.revision FROM runs r JOIN sessions s ON s.id=r.session_id WHERE r.id=?', (job['agentRunId'],)).fetchone()
    finally: db.close()
    config = json.loads(row[2]) if row else {}
    permission = update_permission(job['kind'],job) if job['kind'] in UPDATE_PERMISSIONS else PERMISSIONS[job['kind']]
    if (not row or row[0] != job['sessionId'] or (not allow_stopping and row[1] in ('stopping', 'interrupted', 'failed', 'unknown'))
        or config.get('owner', {}).get('type') != 'project' or config.get('projectPins') != job['pins']
        or not config.get('permissions', {}).get('studio.' + permission)):
        raise DevelopmentFault('This job no longer has an authorized agent snapshot.', 403)
    if job['kind'] in UPDATE_PERMISSIONS:
        if config.get('owner', {}).get('type') != 'project':
            raise DevelopmentFault('This original run has no app-project update binding.',403)
        if job.get('recoveryAction')=='resume-batch' and not config['permissions'].get('studio.commit_update'):
            raise DevelopmentFault('This batch resume no longer has its frozen commit permission.',403)
    if job['kind'] in ('vm_stop','vm_restart'):
        if config.get('revision')!=row[5]:raise DevelopmentFault('The original agent settings revision changed.',403)
        from lease import birth
        worker=json.loads(row[4] or '{}')
        try:
            if not worker.get('pid') or worker.get('birth')!=birth(worker['pid']):raise ValueError()
        except (OSError,ValueError):raise DevelopmentFault('The original agent worker ended or its process identity changed.',403) from None
        if not row[3] or row[1]!='running':raise DevelopmentFault('VM lifecycle requires its original active agent run.',403)
        if job['kind']=='vm_restart' and not permits(config,store.id,'start_project_vm','stop_project_vm','restart_project_vm'):
            raise DevelopmentFault('Restart no longer has its frozen start/stop/restart permissions.',403)
    if job['kind'] == 'observation':
        if not row[3] or row[1] != 'running' or config.get('revision') != row[5]:
            raise DevelopmentFault('VM observation requires its original active agent snapshot.', 403)
        from vm_observation import require_context
        require_context(config, {'revision': job['projectRevision'], 'vmId': job['binding']['id']}, job['binding'])
    if job['kind'] == 'vm_start' and (config.get('owner', {}).get('type') != 'project' or not row[3] or row[1] != 'running'):
        raise DevelopmentFault('VM startup requires its original active agent turn.', 403)
