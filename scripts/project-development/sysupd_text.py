"""Source-bound text protocol. Native R4OS retains validation/install authority."""
import json
import re
from contracts import DevelopmentFault
from update_plans import version, target, token

OPERATIONS = {'STATUS', 'VERIFY', 'APPLY', 'STAGE', 'COMMIT', 'RESUME', 'RESUME-BATCH', 'ABORT-BATCH', 'ROLLBACK-LAST'}
KEYS = set('state package package-version current-release release payloads bytes streamed reboot activation priority components requires inbox staged transaction generation journal applied source batch-state batch batch-progress progress reason phase payload resume packages stages current required target archive checksum total payload-read-bytes'.split())
COUNTERS = set('payloads bytes streamed components requires transaction generation batch payload packages stages total payload-read-bytes'.split())
JOURNAL_PHASES = {'prepare', 'stage', 'commit', 'verify', 'inventory', 'applied', 'post_boot', 'cleanup', 'rollback', 'rolled_back'}
BATCH_PHASES = {'staged', 'verifying', 'staging', 'committing', 'pending-restart', 'installed', 'failed', 'rolling-back', 'rolled-back'}
JOURNAL_TERMINAL = {'cleanup', 'rolled_back'}
BATCH_TERMINAL = {'installed', 'rolled-back'}
INBOX = 'C:\\R4OS\\UPDATE\\INBOX'
STAGED = 'C:\\R4OS\\UPDATE\\STAGED'


def fault(message='The SYSUPD text protocol is unknown or contradictory. No further update effect was authorized.'):
    return DevelopmentFault(message, 409, reason_code='sysupd_protocol_unconfirmed')


def u64(value):
    if not isinstance(value, str) or not re.fullmatch(r'0|[1-9][0-9]{0,19}', value) or int(value) > 18446744073709551615:
        raise fault('A native SYSUPD counter is outside the unsigned64-bit text contract.')
    return value  # Never round through a JSON number.


def fields(text):
    matches = list(re.finditer(r'(?:^| )([a-z][a-z0-9-]*)=', text))
    head = text[:matches[0].start()].strip() if matches else text.strip()
    values = {}
    for index, match in enumerate(matches):
        key = match[1]; end = matches[index+1].start() if index+1 < len(matches) else len(text)
        value = text[match.end():end].strip()
        if key not in KEYS or key in values or not value: raise fault()
        values[key] = value
    for key in COUNTERS & values.keys(): u64(values[key])
    for key in {'applied', 'progress', 'batch-progress'} & values.keys():
        parts = values[key].split('/')
        if key == 'applied' and len(parts) == 1:
            u64(parts[0]); continue
        if len(parts) != 2: raise fault()
        a, b = map(u64, parts)
        if int(a) > int(b): raise fault()
    for key in {'release', 'package-version', 'current-release'} & values.keys():
        if key != 'current-release' or values[key] != 'unknown': version(values[key])
    if 'dirs' in values and values['dirs'] not in ('ok', 'missing'): raise fault()
    if 'reboot' in values and values['reboot'] not in ('yes', 'no'): raise fault()
    if 'activation' in values and values['activation'] not in ('live', 'restart'): raise fault()
    if 'priority' in values and values['priority'] not in ('normal', 'foundation'): raise fault()
    return head, values


# dirs is status-only, but remains a known delimiter in mixed diagnostic text.
KEYS.add('dirs')


def status_line(text):
    head, values = fields(text)
    base = {'mode': head, 'fields': values, 'transactionId': values.get('transaction'), 'batchId': values.get('batch')}
    if values.get('dirs') not in ('ok', 'missing'): raise fault()
    if head == 'idle':
        if set(values) != {'inbox', 'staged', 'dirs'}: raise fault()
    elif head == 'batch':
        required = {'state', 'batch', 'progress', 'release', 'inbox', 'staged', 'dirs'}
        if not required <= values.keys() or set(values) - required - {'reason'}: raise fault()
        if values['state'] not in BATCH_PHASES: raise fault()
        base['batchPhase'] = values['state']
    elif head == 'journal':
        required = {'state', 'transaction', 'generation', 'release', 'package-version', 'components', 'priority', 'applied', 'reboot', 'source', 'dirs'}
        optional = {'batch-state', 'batch', 'batch-progress', 'reason'}
        if not required <= values.keys() or set(values) - required - optional or values['state'] not in JOURNAL_PHASES: raise fault()
        if '/' not in values['applied']: raise fault()
        base['journalPhase'] = values['state']
        if set(values) & {'batch-state', 'batch', 'batch-progress'}:
            if not {'batch-state', 'batch', 'batch-progress'} <= values.keys() or values['batch-state'] not in BATCH_PHASES: raise fault()
            base['batchPhase'] = values['batch-state']
    else: raise fault()
    for key, expected in [('inbox', INBOX), ('staged', STAGED)]:
        if key in values and values[key].upper() != expected: raise fault('SYSUPD reports an unsupported update directory.')
    journal_active = bool(base.get('journalPhase') and base['journalPhase'] not in JOURNAL_TERMINAL)
    batch_active = bool(base.get('batchPhase') and base['batchPhase'] not in BATCH_TERMINAL)
    base.update(directoriesReady=values['dirs']=='ok', activeOrRecoverable=journal_active or batch_active,
        historicalRollback=base.get('journalPhase')=='rolled_back' or base.get('batchPhase')=='rolled-back')
    return base


def parse(operation, capture):
    if operation not in OPERATIONS: raise fault('This native update command is not supported.')
    if capture.get('truncated') or capture.get('timedOut'): raise fault('The native SYSUPD response is incomplete; inspect its saved channels.')
    stdout = capture.get('stdout', capture.get('output', '')); stderr = capture.get('stderr', '')
    if not isinstance(stdout, str) or not isinstance(stderr, str) or len((stdout+stderr).encode()) > 262144: raise fault()
    lines = [line.strip() for line in (stdout+'\n'+stderr).splitlines() if line.strip()]
    candidates = []
    for line in lines:
        if line.startswith('SYSUPD STATUS:'):
            if operation != 'STATUS': raise fault()
            candidates.append(('STATUS', 'STATUS', line.partition(':')[2].strip(), line))
        else:
            match = re.fullmatch(r'SYSUPD ([A-Z-]+) result: (.*)', line)
            if match:
                actual = match[1]
                if actual != operation and not (operation=='STAGE' and actual=='APPLY'): raise fault()
                candidates.append(('result', actual, match[2], line))
            elif line.startswith('SYSUPD') and not line.startswith('SYSUPD I/O:'):
                raise fault('The guest SYSUPD command does not expose the supported text interface.')
    if len(candidates) != 1: raise fault()
    kind, actual, body, raw = candidates[0]; code = capture.get('exitCode')
    if kind == 'STATUS':
        value = status_line(body)
        if code != 0 or not value['directoriesReady']: raise fault('SYSUPD STATUS did not confirm usable update directories.')
        return {'schema': 1, 'operation': operation, 'effectiveOperation': actual, 'kind': 'status', 'confirmed': True,
            'success': True, 'sshExitCode': code, 'status': value, 'rawLine': raw}
    head, values = fields(body)
    if head not in {'OK', 'FAILED', 'INCOMPATIBLE', 'INTERRUPTED'}: raise fault()
    if head != 'OK' and code == 0: raise fault()
    if head == 'OK' and code not in (0, 255, None): raise fault()
    if head in {'FAILED', 'INCOMPATIBLE'} and 'reason' not in values: raise fault()
    if 'state' in values and values['state'] not in JOURNAL_PHASES | BATCH_PHASES | {'Idle', 'Staged', 'Pending restart', 'Installed', 'Rolled back', 'Pending rollback; rebooting', 'inventory-complete'}:
        raise fault()
    if actual == 'APPLY' and 'staged' in values: u64(values['staged'])
    uncertain = code in (None, 255) or bool(capture.get('transportUncertain'))
    if head == 'OK' and actual in ('VERIFY', 'APPLY', 'STAGE') and 'package' not in values: raise fault()
    state = values.get('state')
    outcome = 'rolled-back' if state in ('Rolled back', 'rolled-back', 'rolled_back') else 'pending-restart' if state in ('Pending restart', 'Pending rollback; rebooting') else 'installed' if state in ('Installed', 'installed') else 'staged' if state in ('Staged', 'staged') else 'applied' if actual == 'APPLY' and head == 'OK' else 'unknown'
    return {'schema': 1, 'operation': operation, 'effectiveOperation': actual, 'kind': 'result',
        'result': head, 'fields': values, 'reportedOutcome': outcome, 'installationConfirmed': False, 'confirmed': not uncertain, 'success': head=='OK' and not uncertain,
        'transportUncertain': uncertain, 'sshExitCode': code, 'rawLine': raw}


def may_upload(status, owner=None):
    value = status['status']
    if not value['directoriesReady']: return False
    if not value['activeOrRecoverable']: return True
    # An own active transaction still requires its recovery path, never a new upload.
    return False


def ownership(status, owner=None):
    value = status['status']; observed = {key: value[key] for key in ('transactionId', 'batchId') if value.get(key) is not None}
    own = bool(owner and observed and all(owner.get(key) == ident for key, ident in observed.items()))
    active = value['activeOrRecoverable']
    return {'matchesOwnRecord': own, 'activeOrRecoverable': active, 'mayUpload': may_upload(status, owner),
        'reason': ('An owned active update requires its recovery path.' if own else 'A foreign or unowned active/recoverable update blocks new work.') if active else None,
        'terminalHistoryRetained': not active and value['mode'] != 'idle', 'externalWriterLock': False}

def release_file(text):
    if not isinstance(text, str) or len(text.encode()) > 256: raise fault('The observed VERSION.R4S is invalid.')
    matches = re.findall(r'^RELEASE_VERSION=([^\r\n]+)$', text.lstrip('\ufeff').replace('\r\n', '\n'), re.M)
    if len(matches) != 1: raise fault('The observed VERSION.R4S has no unique release version.')
    return version(matches[0].strip())


def inventory(text):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value: raise fault('The observed inventory has duplicate JSON keys.')
            value[key] = item
        return value
    try: value = json.loads(text.lstrip('\ufeff'), object_pairs_hook=unique)
    except (ValueError, TypeError): raise fault('The observed MODULES.JSON is not valid bounded JSON.') from None
    if (not isinstance(value, dict) or type(value.get('schema')) is not int or value.get('schema') not in (2, 3, 4) or type(value.get('count')) is not int
            or not isinstance(value.get('entries'), list) or not 1 <= value['count'] <= 192 or value['count'] != len(value['entries'])):
        raise fault('The observed MODULES.JSON schema/count is unsupported.')
    seen_names = set(); seen_targets = set()
    for entry in value['entries']:
        if not isinstance(entry, dict) or not isinstance(entry.get('kind'), str) or entry.get('kind') not in {'KERNEL', 'R4X', 'R4L', 'R4D', 'R4P'}: raise fault()
        name = token(entry.get('name'), 'inventory component'); version(entry.get('version')); path = target(entry.get('target'))
        key = (entry['kind'], name.casefold())
        if key in seen_names or path.casefold() in seen_targets: raise fault('The observed inventory contains conflicting component identities.')
        seen_names.add(key); seen_targets.add(path.casefold())
    # Observation only. Native VERIFY remains the compatibility/format authority.
    return value
