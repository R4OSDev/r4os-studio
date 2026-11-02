"""Check completion and retained end observation; no implicit stop rights."""
import asyncio
from contracts import DevelopmentFault, hash_value
from checks import evaluate
from evidence import read
from jobs import now
from frame_binding import current


def retained_natural_end(execution, job, state):
    """Only an acknowledged original native lease qualifies for an end wait."""
    from desktop_evidence import unpack
    from recovery import read as read_receipt
    if state.get('stopReason') is not None or job.get('kind') != 'execution': return False
    try:
        record = read_receipt(execution.work / 'desktop-evidence.json')
        launch = record['launch']; fields = unpack(record['token'])
        original = job['desktopLaunch']['request']
        process = job['process']
        return (record.get('phase') == 4 and record.get('result') in (0, -7)
            and launch['request'] == original
            and fields[2:6] == tuple(int(part) for part in original.split(':'))
            and fields[13] > 0
            and (fields[6], str(fields[7])) == (process['instanceId'], process['generation'])
            and (record.get('instanceId'), record.get('generation'), record.get('serial'))
                == (fields[6], str(fields[7]), str(fields[13]))
            and (launch['process_id'], launch['process_generation']) == (process['instanceId'], process['generation']))
    except (DevelopmentFault, OSError, ValueError, KeyError, TypeError): return False


async def await_original_close(execution, control, state, lease, *, natural=False):
    """A retained completion can arrive after Desktop detached the process."""
    from vm_worker import guard
    from layout import save
    marker = execution.completion
    job = execution.store.get(execution.job['id'])
    pending = job.get('checkCompletion') or {}
    if (state.get('state') != 'unknown' or state.get('desktopEvidenceRetained') is not True
        or state.get('closeConfirmed') is True): return state
    if natural:
        if marker or not retained_natural_end(execution, job, state): return state
    elif (not marker or pending.get('requestId') != marker.get('requestId')
        or pending.get('state') != 'closing' or state.get('stopReason') != 'user_stop'): return state
    process = job.get('process') or {}
    if any(state.get(key) != process.get(key) for key in ('instanceId', 'generation')): return state
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 5
    polls = 0
    while loop.time() < deadline and not execution.stop_requested:
        guard(execution.store, job, lease, allow_stopping=True)
        await asyncio.sleep(min(.1, max(0, deadline - loop.time())))
        remaining = deadline - loop.time()
        if remaining <= 0: break
        try: observed = await asyncio.wait_for(control.call('poll'), remaining)
        except asyncio.TimeoutError: break  # Abandon this controller; never submit another close.
        if any(observed.get(key) != process.get(key) for key in ('instanceId', 'generation')): return state
        polls += 1
        save(execution.work / ('natural-end-observation.json' if natural else 'completion-close-observation.json'),
            {'schema': 1, 'jobId': job['id'], 'requestId': job['desktopLaunch']['request'] if natural else marker['requestId'],
                'target': job['target'], 'statusOnly': True, 'maximumWaitMilliseconds': 5000,
                'polls': polls, 'observedAt': now(), 'state': observed})
        execution.output(observed); observed['outputBase64'] = ''
        state = observed
        if state.get('state') != 'unknown': break
    return state


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
            or not current(image, job, state, maximum_age=120)):
            raise DevelopmentFault('The assessed image is older than 120 seconds or its process, window geometry or focus changed. Capture and assess it again.')
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
