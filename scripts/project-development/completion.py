"""Explicit check completion; observed success never grants implicit stop rights."""
from contracts import DevelopmentFault, hash_value
from checks import evaluate
from evidence import read
from jobs import now


def snapshot(job):
    value = {key: job.get(key) for key in ('id', 'projectId', 'projectRevision', 'settingsRevision',
        'settings', 'pins', 'target', 'process', 'visualAssessment')}
    # Desktop may detach its window during the requested close. Process
    # identity remains exact; the validated image retains its own window proof.
    value['process'] = {key: (job.get('process') or {}).get(key) for key in ('instanceId', 'generation', 'serviceName')}
    return value


def validate(store, job, state, output, files):
    if job['kind'] != 'execution' or job['state'] != 'running' or state.get('state') != 'running' or state.get('stopReason'):
        raise DevelopmentFault('Only a live, confirmed execution can complete its checks.')
    process = job.get('process') or {}
    if not process.get('instanceId') or any(state.get(k) != process.get(k) for k in ('instanceId', 'generation')):
        raise DevelopmentFault('The check completion process identity changed.')
    visual = job.get('visualAssessment')
    if job['settings'].get('visualCriteria'):
        if not visual: raise DevelopmentFault('Inspect and assess a current screenshot before completing these checks.')
        image = read(store, job['id'], visual['evidenceId'])['metadata']
        if (image['kind'] != 'screenshot' or image['sha256'] != visual.get('imageSha256')
            or image.get('bootId') != (job.get('target') or {}).get('bootId')
            or any((image.get('process') or {}).get(k) != process.get(k) for k in ('instanceId', 'generation'))
            or image.get('guestRevision') != state.get('guiRevision') or not state.get('windowVisible')):
            raise DevelopmentFault('The assessed image no longer matches this process and frame. Capture and assess it again.')
    check = evaluate(job['settings'], state, output, files, visual)
    if check['state'] != 'passed':
        raise DevelopmentFault('All configured checks must be confirmed before completion. Exit criteria require the actual application exit.')
    return {'request': snapshot(job), 'check': check, 'reason': 'criteria_complete', 'createdAt': now()}


def result(store, job, state, output, files, marker, cancelled=False):
    """Recheck after closure; a timeout or real app error cannot become success."""
    visual = job.get('visualAssessment')
    if visual:
        try:
            image = read(store, job['id'], visual['evidenceId'])['metadata']
            if image['sha256'] != visual['imageSha256']: visual = None
        except (DevelopmentFault, OSError, KeyError): visual = None
    check = evaluate(job['settings'], state, output, files, visual)
    same = hash_value(marker['request']) == hash_value(snapshot(job))
    success = (not cancelled and same and state.get('closeConfirmed') is True and state.get('state') == 'completed'
        and state.get('stopReason') == 'user_stop' and state.get('exitCode') in (None, 0)
        and check['state'] == 'passed')
    return {'requestId': marker['requestId'], 'reason': 'criteria_complete',
        'state': 'completed' if success else 'failed', 'cancelled': cancelled, 'closed': state.get('closeConfirmed') is True,
        'check': check, 'completedAt': now()}
