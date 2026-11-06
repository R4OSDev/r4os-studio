"""Read-only presentation of original execution receipts; never grants replay."""
import hashlib
import re
from contracts import DevelopmentFault, LIMITS
from recovery import read


def describe(store, job):
    if job['kind'] != 'execution' or not job.get('process'): return None
    work = store.root / 'ExecutionWork' / job['id']
    result = {'version': 1, 'processEndConfirmed': False, 'cleanupConfirmed': False,
              'exitStatusConfirmed': False, 'exitCode': None,
              'output': {'state': 'unconfirmed', 'reason': 'No matching durable output receipt is available.'}}
    try:
        intent, started = (read(work / name) for name in ('intent.json', 'started.json'))
        expected = {key: job[key] for key in ('executionId', 'deploymentId', 'target', 'settings')}
        expected['jobId'] = job['id']
        process = job['process']
        if any(type(value.get('schema')) is not int or value['schema'] != 1 or any(value.get(key) != val for key, val in expected.items())
               for value in (intent, started)): return result
        if intent.get('state') != 'intent' or started.get('state') != 'started': return result
        if any(started['process'].get(key) != process[key] for key in ('instanceId', 'generation')): return result
        closed = (work / 'closed.json').exists()
        retained = (work / 'retained-completion.json').exists()
        watchdog = (work / 'watchdog-completion.json').exists()
        value = read(work / ('retained-completion.json' if retained else 'watchdog-completion.json' if watchdog else
                            'closed.json' if closed else 'output-observation.json'))
        if any(value.get(key) != val for key, val in expected.items()) or type(value.get('schema')) is not int or value['schema'] != 1: return result
        if closed and not retained and not watchdog and (value.get('state') != 'closed' or value.get('applicationStarted') is False): return result
        if retained and value.get('state') != 'retained-completion': return result
        if watchdog and not retained and value.get('state') != 'watchdog-completion': return result
        if watchdog and not retained:
            reference = value.get('watchdogReceipt') or {}
            if not isinstance(reference.get('file'), str) or not re.fullmatch(r'watchdog-original-[a-f0-9]{32}\.json', reference['file']): return result
            path = work / reference['file']
            raw = read(path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != reference.get('sha256'): return result
            if (not isinstance(raw, dict) or raw.get('instance') != job['executionId'] or raw.get('success') is not True
                or any((raw.get('result') or {}).get(key) != value['completion'].get(key)
                       for key in ('state', 'instanceId', 'generation', 'closeConfirmed', 'exitCode', 'completionSequence'))): return result
        state = value.get('completion') if closed or retained or watchdog else value.get('observation')
        if not isinstance(state, dict) or any(state.get(key) != process[key] for key in ('instanceId', 'generation')): return result
        result['completion'] = {k: state[k] for k in ('stopReason', 'exitReason', 'consoleObserved') if k in state}
        result['source'] = ('native-retained-completion' if retained else 'original-watchdog-completion' if watchdog else
                            'private-guest-close-receipt' if closed else 'private-guest-observation')
        result['processEndConfirmed'] = state.get('state') == 'completed' and state.get('closeConfirmed') is True
        result['cleanupConfirmed'] = bool(not retained and not watchdog and closed and result['processEndConfirmed'] and
            all(value.get('cleanupReceipt', {}).get(key) is True for key in ('closed', 'serviceRemoved', 'watchdogRemoved')))
        code = state.get('exitCode')
        result['exitStatusConfirmed'] = type(code) is int and -2147483648 <= code <= 2147483647
        result['exitCode'] = code if result['exitStatusConfirmed'] else None
        if not result['exitStatusConfirmed']:
            result['exitStatusReason'] = ('Native completion was unavailable for this process generation.'
                if state.get('exitEvidenceUnavailable') is True else 'No native exit status has been observed.')
        path = store.root / 'Evidence' / job['id'] / 'output.log'
        if path.resolve(strict=True) != path or not path.is_file() or path.stat().st_nlink != 1: return result
        with path.open('rb') as stream: data = stream.read(LIMITS['outputBytes'] + 1)
        proof = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        if len(data) > LIMITS['outputBytes'] or value.get('outputReceipt') != proof: return result
        complete = (result['processEndConfirmed'] and state.get('outputIncomplete') is False and
                    (state.get('completionObserved') is True or type(state.get('completionSequence')) is int))
        result['output'] = {**proof, 'state': 'complete' if complete else 'incomplete',
            'reason': ('All retained process-console bytes were captured.' if complete else
                'Only observed process-console bytes are retained; missing routing or completion evidence cannot be reconstructed.')}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, DevelopmentFault):
        pass  # A damaged or historical receipt is never upgraded to success.
    return result
