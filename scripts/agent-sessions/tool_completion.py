"""Later lifecycle evidence for original tool results in a summary."""
import json
import sqlite3

from store import ProjectFault


ACTIVE = ('queued', 'starting', 'running', 'stopping')
JOBS = {
    'studio_build_project': 'build',
    'studio_deploy_project': 'deploy',
    'studio_run_project': 'execution',
    'studio_start_project_vm': 'vm_start',
    'studio_stop_project_vm': 'vm_stop',
    'studio_restart_project_vm': 'vm_restart',
    'studio_capture_vm': 'observation',
}


def terminal_end(worker, record, process):
    from session_store import identity
    identity(process)
    row = worker.store.db.execute(
        'SELECT payload FROM items WHERE session_id=? AND run_id=? AND item_id=?',
        (worker.session_id, record['runId'], 'process-' + process)).fetchone()
    if row is None:
        return None
    item = json.loads(row[0])
    if (item.get('type') == 'terminal' and item.get('tool') == 'studio.exec_command'
            and item.get('runId') == record['runId'] and item.get('processId') == process
            and item.get('status') in ('completed', 'failed')
            and type(item.get('exitCode')) is int and item.get('processEndConfirmed') is True):
        return {'processId': process, 'state': 'exited', 'exitCode': item['exitCode']}
    return None


def job_end(worker, record, tool, original):
    from development_references import reader
    entries = reader().listing(worker.store.projects, worker.store.owner_id, worker.session_id, {
        'originRunId': record['runId'], 'toolCallId': original['studioReceiptId'],
        'kind': JOBS[tool], 'limit': 1,
    })['entries']
    if not entries:
        return None
    job = entries[0]
    previous = original['development']
    if (job['id'] == previous['jobId'] and job['agentRunId'] == record['runId']
            and previous.get('requestId') in (None, job['requestId'])
            and job['state'] in ('completed', 'failed') and job['completedAt']):
        return {'jobId': job['id'], 'state': job['state'], 'completedAt': job['completedAt']}
    return None


def completions(worker, record):
    """Bind later evidence to the exact original result and its owning run."""
    from context_results import load, reference
    from context_result_ids import resolve
    later = {}
    for index, part in enumerate(record['content']):
        if part['type'] != 'tool_result':
            continue
        result = part['result']
        terminal = result.get('state') == 'running' and isinstance(result.get('processId'), str)
        development = result.get('development') or {}
        job = (worker.store.owner_type == 'project' and isinstance(development, dict)
               and development.get('state') in ACTIVE and development.get('kind') in JOBS.values())
        if not (terminal or job):
            continue
        try:
            ref = resolve(worker,result.get('contextArchive') or {}) or reference(worker, record, index)
            if ref['sequence'] != record['sequence'] or ref['partIndex'] != index or ref['callId'] != part['callId']:
                continue
            _, original, receipt = load(worker, ref)
            original = original['result']
            tool = receipt['tool']
            proof = None
            if terminal and tool == 'studio_exec_command' and original.get('state') == 'running':
                proof = terminal_end(worker, record, original['processId'])
            if job and tool in JOBS and original['development'].get('kind') == JOBS[tool]:
                proof = job_end(worker, record, tool, original)
            if proof is not None:
                later[index] = proof
        except (ImportError, OSError, sqlite3.Error, ProjectFault, ValueError, KeyError, TypeError):
            continue
    return later


def with_completion(result, proof):
    """Evaluate the lifecycle fields covered by the later receipt."""
    if 'processId' in proof:
        return {**result, 'state': 'exited', 'exitCode': proof['exitCode'], 'processEndConfirmed': True}
    updated = {**result, 'development': {**result['development'], 'state': proof['state']}}
    output = result.get('output')
    if isinstance(output, str) and output.lstrip().startswith('{'):
        from model_transport import dumps
        try:
            data = json.loads(output)
        except (ValueError, RecursionError):
            return updated
        job = data.get('job')
        if isinstance(job, dict) and job.get('id') == proof['jobId'] and job.get('state') in ACTIVE:
            data['job'] = {**job, 'state': proof['state']}
            updated['output'] = dumps(data)
    return updated
