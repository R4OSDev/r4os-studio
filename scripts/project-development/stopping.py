"""Command receipts describe Stop separately from the stopped job's outcome."""
from contracts import DevelopmentFault, digest
from jobs import now
from recovery import read


def receipt(store, job, requested, worker_active):
    result = {'version': 1, 'jobId': job['id'], 'requested': requested, 'confirmed': False,
        'outcome': 'unconfirmed', 'scope': 'worker', 'jobState': job['state'], 'recordedAt': now(),
        'reason': 'The original job has no confirmed stop receipt. Inspect it; do not repeat an unknown action.'}
    if worker_active or job['state'] in ('queued', 'starting', 'running', 'stopping', 'unknown'): return result
    if job['kind'] != 'execution':
        result.update(confirmed=True, outcome='stopped' if requested else 'already-ended',
            reason='The host worker has ended. The job outcome and any completed guest writes are retained.',
            guestEffectsMayRemain=job['kind'] not in ('build', 'package'))
        return result
    result['scope'] = 'owned-process'
    work = store.root / 'ExecutionWork' / job['id']
    try:
        closed_path = work / 'closed.json'
        if not (work / 'intent.json').exists():
            if job.get('process') or job.get('executionId'): return result
            result.update(confirmed=True, outcome='not-started', reason='The worker ended before admitting an application launch.')
            return result
        intent = read(work / 'intent.json'); closed = read(closed_path)
        if (closed.get('state') != 'closed' or closed.get('jobId') != job['id']
            or closed.get('deploymentId') != job.get('deploymentId') or closed.get('target') != job.get('target')
            or closed.get('executionId') != intent.get('executionId') or closed.get('settings') != job.get('settings')):
            return result
        if closed.get('applicationStarted') is False:
            # Older workers wrote this only after confirmed watchdog closure.
            confirmed = True
        else:
            process = job.get('process') or {}; state = closed.get('completion') or {}
            cleanup = closed.get('cleanupReceipt') or {}
            confirmed = (bool(process.get('instanceId')) and state.get('state') == 'completed'
                and state.get('closeConfirmed') is True
                and all(state.get(k) == process.get(k) for k in ('instanceId', 'generation'))
                and all(cleanup.get(k) is True for k in ('closed', 'serviceRemoved', 'watchdogRemoved')))
        if confirmed:
            result.update(confirmed=True, outcome='stopped' if requested else 'already-ended',
                source='private-guest-close-receipt', receiptSha256=digest(closed_path),
                reason='The owned process has ended and its cleanup is confirmed. The job result is retained.')
    except (OSError, ValueError, KeyError, DevelopmentFault):
        pass  # Missing or damaged evidence never becomes a successful Stop.
    return result
