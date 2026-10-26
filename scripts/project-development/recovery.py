"""Conservative receipt reconciliation. No compilation, transfer or app launch."""
import hashlib
import json
from pathlib import Path
import uuid
import re
from contracts import DevelopmentFault, digest, generation, identity
from jobs import now
from quarantine import resolve


def read(path):
    if path.resolve(strict=True) != path or path.stat().st_nlink != 1 or path.stat().st_size > 2097152:
        raise DevelopmentFault('The recovery receipt is invalid. Existing data was preserved.')
    return json.loads(path.read_text())


def receipt(kind, **fields):
    return {'schema': 1, 'id': str(uuid.uuid4()), 'source': kind, 'replayed': False, 'recordedAt': now(), **fields}


def complete_files(store, job):
    from evidence import read as evidence
    files = []
    for item in job.get('outputFiles', []):
        try: evidence(store, job['id'], item['id']); files.append(item)
        except (DevelopmentFault, OSError, KeyError): files.append({'name': item.get('name', ''), 'error': 'The saved output file evidence is unavailable.'})
    visual = job.get('visualAssessment')
    if visual:
        try: evidence(store, job['id'], visual['evidenceId'])
        except (DevelopmentFault, OSError, KeyError): visual = None
    return files, visual


def local(store, job):
    """Only already committed, privately attested results may become final."""
    if job['state'] != 'unknown': return None
    if (job.get('recovery') or {}).get('guestEndConfirmed'): return job
    if job['kind'] == 'build':
        row = store.db.execute('SELECT id FROM artifacts WHERE build_id=?', (job['id'],)).fetchone()
        if not row: return None
        artifact = store.artifact(row[0], recovering=True); source = job.get('source') or {}
        if (artifact.get('projectId') != store.id or artifact.get('pins') != job['pins']
            or artifact.get('sourceSha256') != source.get('sha256') or artifact.get('manifestSha256') != source.get('manifestSha256')):
            raise DevelopmentFault('The committed artifact differs from its original job inputs.')
        proof = read(store.root / 'Artifacts' / artifact['id'] / 'build-proof.json')
        if proof.get('schema') != 1 or proof.get('status') != 'success': raise DevelopmentFault('The build success receipt is missing.')
        if artifact['buildProof']['format'] == 'r4os-studio-sdk-build-v1':
            valid = proof.get('interface') == 'r4os-studio-sdk-build' and proof.get('pins') == job['pins'] and proof.get('sourceSha256') == source['sha256'] and proof.get('artifact') == artifact['files'][0]
        elif artifact['buildProof']['format'] == 'r4os-sdk-rust-build-v1':
            valid = (proof.get('technical') is False and proof['module']['name'] == store.project['moduleName']
                and proof['artifact']['sha256'] == artifact['files'][0]['sha256']
                and proof['sdk']['source']['commit'] == job['pins']['sdk']['revision']
                and proof['contract']['source']['commit'] == job['pins']['contract']['revision']
                and proof['cargo']['lock_sha256'] == digest(store.root / 'Inputs' / job['id'] / 'Cargo.lock'))
        else: valid = False
        if not valid: raise DevelopmentFault('The original build proof does not match. It was preserved.')
        return store.recovered(job['id'], 'completed', receipt('committed-build-proof', artifactId=artifact['id']), artifactId=artifact['id'], exitCode=0, error=None)
    if job['kind'] == 'deploy':
        row = store.db.execute('SELECT id FROM deployments WHERE job_id=?', (job['id'],)).fetchone()
        if not row: return None
        value = store.deployment(row[0], recovering=True)
        artifact = store.artifact(value['artifactId'])
        directory = 'C:\\P' + hashlib.sha256(store.id.encode()).hexdigest()[:7].upper() + '\\D' + identity(value['id']).replace('-', '')[:7].upper()
        if value.get('format') == 'exchange-build-v1':
            from exchange import directory as exchange_directory
            path = exchange_directory(value['target'], 'P' + hashlib.sha256(store.id.encode()).hexdigest()[:7].upper(), 'D' + identity(value['id']).replace('-', '')[:7].upper())
            directory = path[1] + ':' + chr(92) + chr(92).join(path.split('/')[2:])
        normalize = lambda text: re.sub(r'\\+', lambda _: chr(92), text.replace('/', chr(92))).upper()
        if (read(store.root / 'DeployWork' / job['id'] / 'deployment.json') != value
            or value['projectId'] != store.id or value['artifactId'] != job['artifactId'] or value['pins'] != job['pins']
            or normalize(value['guestDirectory']) != directory or value['packageSha256'] != artifact['packageSha256']
            or value['sourceSha256'] != artifact['sourceSha256'] or value['manifestSha256'] != artifact['manifestSha256']
            or value['target']['vmId'] != job['binding']['id'] or value['target']['imageSha256'] != job['binding']['imageSha256']
            or not value['files'] or any(v.get('fullReadbackVerified') is not True for v in value['files'])):
            raise DevelopmentFault('The deployment publication receipt is incomplete. Guest files were preserved.')
        return store.recovered(job['id'], 'completed', receipt('committed-deployment-readback', deploymentId=value['id'], historical=True),
            deploymentId=value['id'], target=value['target'], exitCode=0, error=None)
    if job['kind'] != 'execution': return None
    work = store.root / 'ExecutionWork' / job['id']; closed = work / 'closed.json'
    if not closed.exists(): return None
    value = read(closed); intent = read(work / 'intent.json')
    if (value.get('state') != 'closed' or value.get('jobId') != job['id'] or value.get('deploymentId') != job['deploymentId']
        or value.get('executionId') != intent.get('executionId') or value.get('target') != job.get('target')
        or value.get('settings') != job['settings']): raise DevelopmentFault('The guest close receipt has a different execution identity.')
    identity(value['executionId'])
    from checks import evaluate
    output = store.evidence(job['id']) / 'output.log'; data = output.read_bytes() if output.exists() else b''
    if value.get('applicationStarted') is False:
        rejected = value.get('launchRejected') is True
        state = {'state': 'completed', 'exitCode': None, 'closeConfirmed': True, 'outputIncomplete': True, 'stopReason': None if rejected else 'user_stop'}
        outcome, process = ('failed' if rejected else 'interrupted'), None
    else:
        started = read(work / 'started.json'); process = started['process']; generation(process['generation'])
        state = value.get('completion') or {}
        if (started.get('executionId') != value['executionId'] or state.get('closeConfirmed') is not True
            or state.get('instanceId') != process['instanceId'] or state.get('generation') != process['generation']):
            raise DevelopmentFault('The process closure proof is incomplete.')
        proof = value.get('outputReceipt')
        if not proof or proof != {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}: state = {**state, 'outputIncomplete': True}
        stopped = state.get('stopReason'); code = state.get('exitCode')
        outcome = 'interrupted' if stopped == 'user_stop' else ('failed' if stopped == 'timeout' or code is not None and code != 0 else ('completed' if code == 0 else 'unknown'))
    files, visual = complete_files(store, job)
    completion_fields = {}
    if value.get('checkCompletionIntent'):
        from completion import result as completion_result
        marker = read(work / 'complete-intent.json')
        if marker != value['checkCompletionIntent'] or not all(value.get('cleanupReceipt', {}).get(k) is True for k in ('closed', 'serviceRemoved', 'watchdogRemoved')):
            raise DevelopmentFault('The original check completion cleanup receipt is incomplete.')
        completion = completion_result(store, job, state, data, files, marker, cancelled=bool(value.get('checkCompletion', {}).get('cancelled')))
        completion_fields['checkCompletion'] = completion
        if state.get('stopReason') == 'user_stop': outcome = 'interrupted' if completion['cancelled'] else completion['state']
    result = store.recovered(job['id'], outcome, receipt('private-guest-close-receipt', guestEndConfirmed=True), process=process,
        guestState=state, exitCode=state.get('exitCode'), check=evaluate(job['settings'], state, data, files, visual), error=None, **completion_fields)
    resolve(store.projects, value['target']['vmId'], job['id'], 'private-guest-close-receipt')
    return result


async def reconcile(store, job, host=None):
    if job['kind'] in ('update_install','update_commit','update_verify','update_recovery'):
        if host is None:raise DevelopmentFault('Current update observation support is required.')
        from update_recovery import reconcile as update_reconcile
        return await update_reconcile(store,job,host)
    if job['kind'] == 'update_transfer':
        if host is None: raise DevelopmentFault('The current VM observer is required for Inbox reconciliation.')
        from update_transfer import reconcile as inbox_reconcile
        return await inbox_reconcile(store, job, host)
    try:
        result = local(store, job)
        if result: return result
    except (OSError, ValueError, KeyError): raise DevelopmentFault('The saved recovery evidence is damaged. Existing files were preserved.') from None
    if job['kind'] == 'vm_start':
        return store.recovered(job['id'], 'unknown', receipt('unconfirmed-vm-start', guestEndConfirmed=False,
            reason='This VM start has no terminal SSH readiness receipt. Its state remains unknown; no start or SSH probe was repeated.'))
    if job['kind'] != 'execution' or not job.get('binding'):
        return store.recovered(job['id'], 'unknown', receipt('unconfirmed-publication', guestEndConfirmed=False,
            reason='No committed publication receipt. Inputs and partial outputs remain preserved; nothing was repeated.'))
    from access import vm_config
    from lease import VmLease
    from vm_client import vm_call
    from checks import evaluate
    vm = vm_config(store.r4os, job['binding']['id'])
    scope = {'kind': 'recovery', 'vmRevision': vm['revision'], 'imageId': vm['imageId'], 'imageSha256': vm['imageSha256']}
    with VmLease(store.projects, vm['id'], scope) as lease:
        from forwards import cleanup
        await cleanup(lease)
        info = await vm_call(lease, 'info'); work = store.root / 'ExecutionWork' / job['id']
        intent = read(work / 'intent.json') if (work / 'intent.json').exists() else {}
        replaced = bool(intent.get('vmInvocationId') and info['invocationId'] and intent['vmInvocationId'] != info['invocationId'])
        if info['vm']['state'] != 'stopped' and not replaced:
            return store.recovered(job['id'], 'unknown', receipt('unconfirmed-guest', guestEndConfirmed=False,
                reason='The guest end is unconfirmed. Its watchdog may still be cleaning up. Stop the assigned VM explicitly if no private close receipt becomes available.'))
        state = {'state': 'completed', 'exitCode': None, 'closeConfirmed': True, 'outputIncomplete': True,
            'closeSource': 'vm-replaced' if replaced else 'vm-stopped'}
        data = (store.evidence(job['id']) / 'output.log').read_bytes() if (store.evidence(job['id']) / 'output.log').exists() else b''
        check = evaluate(job['settings'], state, data)
        if check['state'] != 'not-run': check = {**check, 'state': 'inconclusive', 'findings': ['The VM ended; the application test result is unavailable.']}
        result = store.recovered(job['id'], 'interrupted', receipt(state['closeSource'], guestEndConfirmed=True), guestState=state,
            exitCode=None, check=check, error='The VM ended after an unconfirmed execution. Its app result remains unavailable.')
        resolve(store.projects, vm['id'], job['id'], state['closeSource']); return result
