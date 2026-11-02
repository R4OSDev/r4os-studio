"""Read original saved DESKRUN admission only; no guest command or new key."""
import base64
import uuid
from contracts import DevelopmentFault


def original(store, job):
    from recovery import read
    from deskrun import command, receipt, DEFAULT_WAIT_MS
    if job.get('desktopLaunchAttempt') or job.get('kind') != 'execution': return None
    work = store.root / 'ExecutionWork' / job['id']
    try:
        intent = read(work / 'intent.json')
        sent = read(work / 'deskrun-1.intent.json')
        transport = read(work / 'deskrun-1.transport.json')
        deployment = store.deployment(job['deploymentId'])
        if (intent.get('schema') != 1 or intent.get('jobId') != job['id']
            or any(intent.get(key) != job.get(key) for key in ('deploymentId','target','settings'))
            or sent.get('operation') != 'start' or sent.get('request') is not None): return None
        execution_id = str(uuid.UUID(intent['executionId']))
        hello = read(work / 'controller.json')
        if hello.get('instance') != execution_id or hello.get('success') is not True: return None
        controller = hello['result'] if ' /CONTROLLER:' in sent['command'] else None
        expected = command(deployment, job['settings']['arguments'],
            min(DEFAULT_WAIT_MS, job['settings']['timeoutSeconds'] * 1000), controller)
        if sent['command'] != expected: return None
        raw = base64.b64decode(transport['stdout'], validate=True)
        if len(raw) > 65536: return None
        native = receipt(raw)
        if native.get('phase') == 'before_submit': return None
        previous = job.get('desktopLaunch') or {}
        if previous.get('request') not in (None, native['request']): return None
        attempt = {'schema': 1, 'hostAttemptId': str(uuid.uuid5(uuid.UUID(execution_id), 'desktop-launch')),
            'jobId': job['id'], 'projectId': store.id, 'executionId': execution_id,
            'deploymentId': job['deploymentId'], 'phase': 'original_transport_read',
            'createdAt': intent['createdAt'], 'observedAt': sent['createdAt'],
            'nativeRequest': native['request'], 'nativeRequestConfirmed': True,
            'nativePhase': native['phase'], 'nativeErrorlevel': native['errorlevel'],
            'process': {'instanceId': native['process_id'], 'generation': native['process_generation']} if native['process_id'] else None,
            'source': 'original-deskrun-transport', 'statusOnly': True}
        fields = {'desktopLaunchAttempt': attempt}
        if not previous:
            fields['desktopLaunch'] = {**native, 'adapter': 'DESKRUN', 'contract': '0.1.1',
                'checkedAt': sent['createdAt'], 'sshExitCode': transport.get('sshExitCode'),
                'transportUncertain': transport.get('transportUncertain') is True}
        return fields
    except (DevelopmentFault, OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
