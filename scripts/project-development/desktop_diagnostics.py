"""Small read-only facts from saved receipts; no new guest observation or repair."""
import re


def fields(value, names):
    return {key: value[key][:300] if isinstance(value[key], str) else value[key]
        for key in names if key in value and (value[key] is None or type(value[key]) in (str, int, bool))}


def identity(value):
    return (isinstance(value, dict) and type(value.get('instanceId')) is int and value['instanceId'] > 0
        and isinstance(value.get('generation'), str) and re.fullmatch(r'[1-9][0-9]{0,19}', value['generation']) is not None)


def describe(job, evidence=None):
    launch = job.get('desktopLaunch') or {}
    attempt = job.get('desktopLaunchAttempt') or {}
    if not launch and not attempt: return None
    if not launch: launch = attempt.get('nativeDiagnostic') or {}
    evidence = evidence or {}
    native = launch.get('adapter') == 'DESKRUN' and launch.get('contract') == '0.1.1'
    process = {'instanceId': launch.get('process_id'), 'generation': launch.get('process_generation')}
    confirmed = native and identity(process)
    request = launch.get('request') if native else None
    guest = job.get('guestState') or {}
    matching = confirmed and all(guest.get(k) == process[k] for k in ('instanceId', 'generation'))
    current = ({k: guest[k] for k in ('state', 'windowId', 'windowWidth', 'windowHeight', 'windowVisible', 'windowFocused') if k in guest}
        if matching else {'state': 'unknown'})
    code = evidence.get('exitCode')
    exit_confirmed = evidence.get('exitStatusConfirmed') is True and type(code) is int
    completion = evidence.get('completion') or {}
    return {'version': 1, 'source': 'original-deskrun-receipt' if native else 'unconfirmed-legacy-receipt',
        'launch': {'state': 'process-confirmed' if confirmed else 'not-submitted' if attempt.get('phase') == 'not_submitted' else 'request-confirmed' if request else 'unknown',
            'adapter': launch.get('adapter'), 'contract': launch.get('contract'), 'request': request,
            **fields(launch, ('phase', 'error', 'errorlevel', 'terminal', 'sshExitCode', 'transportUncertain', 'statusError', 'statusErrorlevel'))},
        'process': {'confirmed': confirmed, **(process if confirmed else {})},
        'window': {'earlier': {**{k: launch[k] for k in ('window', 'content', 'checkedAt') if k in launch},
            'contentConfirmed': native and launch.get('phase') == 'content' and str(launch.get('content', '0')).isdigit() and int(launch['content']) > 0},
            'current': current},
        'appExit': {'confirmed': exit_confirmed, 'code': code if exit_confirmed else None,
            'source': evidence.get('source', 'unconfirmed'),
            **{k: completion[k] for k in ('stopReason', 'exitReason') if k in completion},
            'interpretation': 'Original native value; no POSIX signal or crash-cause inference.'},
        'processEndConfirmed': evidence.get('processEndConfirmed') is True,
        'cleanupConfirmed': evidence.get('cleanupConfirmed') is True,
        'console': evidence.get('output', {'state': 'unconfirmed'}),
        'jobState': job.get('state'), 'checkState': (job.get('check') or {}).get('state', 'not-run'),
        'cause': 'unresolved',
        'notice': 'DESKRUN terminal/errorlevel/SSH exit describe the launch request, not the app exit. A confirmed process does not prove user code or content readiness. Observation completion and cleanup do not prove test success. Missing window evidence does not establish that the VM has no Desktop.'}
