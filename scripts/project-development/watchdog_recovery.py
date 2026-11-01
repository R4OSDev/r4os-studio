"""Read the original watchdog's final frame; never restart a controller or app."""
import hashlib
import re
import uuid

from contracts import DevelopmentFault, LIMITS
from layout import save


async def recover(store, job, deployment, ssh, work, intent):
    from recovery import read, receipt, complete_files
    from sftp import download
    from exchange import sftp_directory
    from checks import evaluate
    from quarantine import resolve

    started = read(work / 'started.json')
    expected = {'schema': 1, 'jobId': job['id'], **{key: job[key] for key in
        ('executionId', 'deploymentId', 'target', 'settings')}}
    process = job.get('process') or {}
    if (not isinstance(intent, dict) or not isinstance(started, dict)
        or intent.get('state') != 'intent' or started.get('state') != 'started'
        or any(type(value.get('schema')) is not int for value in (intent, started))
        or any(value.get(key) != item for value in (intent, started) for key, item in expected.items())
        or type(process.get('instanceId')) is not int or process['instanceId'] <= 0
        or not isinstance(process.get('generation'), str) or not re.fullmatch(r'[1-9][0-9]{0,19}', process['generation'])
        or not isinstance(started.get('process'), dict)
        or any(started.get('process', {}).get(key) != process.get(key) for key in ('instanceId', 'generation'))):
        raise DevelopmentFault('The original watchdog launch binding is incomplete. Existing evidence was preserved.')

    hello = read(work / 'controller.json')
    controller = hello.get('result') if isinstance(hello, dict) else None
    directory = deployment['guestDirectory']
    name = 'A' + job['executionId'][:7].upper() + '.JSN'
    normalize = lambda text: re.sub(r'\\+', lambda _: chr(92), text.replace('/', chr(92))).upper() if isinstance(text, str) else ''
    if (not isinstance(hello, dict) or not isinstance(controller, dict)
        or type(hello.get('version')) is not int or hello['version'] != 1
        or type(hello.get('sequence')) is not int or hello['sequence'] != 0
        or hello.get('instance') != job['executionId'] or hello.get('success') is not True
        or controller.get('controlVersion') != 2 or controller.get('watchdogVersion') != 1
        or normalize(controller.get('modulePath')) != normalize(directory + chr(92) + 'STHELP.R4X')
        or normalize(controller.get('receiptFile')) != normalize(directory + chr(92) + name)):
        raise DevelopmentFault('The saved watchdog receipt does not belong to this original controller.')

    local = work / ('watchdog-original-' + uuid.uuid4().hex + '.json')
    if not await download(ssh, sftp_directory(deployment) + '/' + name, local,
                          maximum=LIMITS['guestFrameBytes'], allow_missing=True):
        return None
    try:
        frame = read(local)
        last = read(work / 'observation.json')
        if not isinstance(frame, dict) or not isinstance(last, dict): raise ValueError()
        state = frame.get('result')
        sequence = frame.get('sequence')
        if (type(frame.get('version')) is not int or frame['version'] != 1 or frame.get('instance') != job['executionId']
            or frame.get('success') is not True or type(sequence) is not int
            or type(last.get('controllerSequence')) is not int or sequence < last['controllerSequence']
            or not isinstance(state, dict)
            or any(state.get(key) != process.get(key) or last.get(key) != process.get(key)
                   for key in ('instanceId', 'generation'))):
            raise ValueError()
        if state.get('state') != 'completed' or state.get('closeConfirmed') is not True:
            return None
        # Only an actual native completion attests an exit. A stale handle or
        # observed disappearance is insufficient for this recovery path.
        if (state.get('completionObserved') is not True
            or type(state.get('completionSequence')) is not int or state['completionSequence'] <= 0
            or type(state.get('exitCode')) is not int or not -2147483648 <= state['exitCode'] <= 2147483647
            or state.get('stopReason') not in (None, 'control_lost', 'timeout', 'user_stop')):
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        raise DevelopmentFault('The original watchdog completion is incomplete or belongs to another execution. Evidence was preserved.') from None

    output = store.evidence(job['id']) / 'output.log'
    data = output.read_bytes() if output.exists() else b''
    if len(data) > LIMITS['outputBytes']:
        raise DevelopmentFault('The preserved execution output exceeds its original limit.')
    # The final frame proves process closure, not every console byte missed
    # after the last live poll. Preserve the original transcript unchanged.
    completion = {key: value for key, value in state.items() if key != 'outputBase64'}
    completion.update(outputIncomplete=True, controllerSequence=sequence)
    raw_hash = hashlib.sha256(local.read_bytes()).hexdigest()
    proof = {**intent, 'state': 'watchdog-completion', 'completion': completion,
        'watchdogReceipt': {'file': local.name, 'sha256': raw_hash},
        'outputReceipt': {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}}
    save(work / 'watchdog-completion.json', proof)
    files, visual = complete_files(store, job)
    check = evaluate(job['settings'], completion, data, files, visual)
    if check['state'] != 'not-run':
        check = {**check, 'state': 'inconclusive', 'findings': [*check['findings'],
            'The original process end is confirmed; interrupted control/output does not establish every app criterion.']}
    stopped = completion.get('stopReason')
    outcome = ('interrupted' if stopped == 'user_stop' else
        'failed' if stopped in ('control_lost', 'timeout') or completion['exitCode'] != 0 else 'completed')
    result = store.recovered(job['id'], outcome,
        receipt('original-watchdog-completion', guestEndConfirmed=True, cleanupConfirmed=False,
                watchdogReceiptSha256=raw_hash),
        guestState=completion, exitCode=completion['exitCode'], check=check,
        error='The original watchdog confirmed process closure after control was lost.' if stopped == 'control_lost' else
              'The original watchdog confirmed execution timeout.' if stopped == 'timeout' else None)
    resolve(store.projects, job['target']['vmId'], job['id'], 'original-watchdog-completion')
    return result
