"""Lossless WINSVC lease handoff, tied to the original DESKRUN epoch.

Host records precede every native mutation. Status is the only reconciliation
after transport loss; a lost serial/epoch never authorizes a new reservation.
"""
import asyncio
import base64
import secrets
import struct
from contracts import DevelopmentFault, UnconfirmedGuestEffect
from jobs import now
from layout import save

TOKEN = struct.Struct('<II I4xQ I4xQ I4xQ I4xQ 3Q Q 3Q')


def unpack(text):
    try:
        raw = base64.b64decode(text, validate=True)
        values = TOKEN.unpack(raw)
        if values[:2] != (1, 128) or any(raw[i:i+4] != b'\0'*4 for i in (12, 28, 44, 60)):
            raise ValueError()
        return values
    except (ValueError, TypeError, struct.error):
        raise DevelopmentFault('The original Desktop evidence token is invalid.') from None


def prepare(launch, intent=None):
    if launch.get('evidence_scope_available') is not True:
        return None
    key = [int(v) for v in launch['request'].split(':')]
    epoch = [int(v) for v in launch['evidence_epoch']]
    receiver = intent or [secrets.randbits(64) for _ in range(3)]
    raw = TOKEN.pack(1, 128, *key, 0, 0, 0, 0, *epoch, 0, *receiver)
    return base64.b64encode(raw).decode()


def bound(previous, result):
    a, b = unpack(previous), unpack(result['token'])
    if (type(result.get('phase')) is not int or not 0 <= result['phase'] <= 7
        or type(result.get('result')) is not int or not -9 <= result['result'] <= 0):
        raise UnconfirmedGuestEffect('Desktop evidence returned an invalid native outcome.')
    # The native service may fill canonical process/Desktop and serial only.
    if (a[:6] != b[:6] or a[10:13] != b[10:13] or a[14:] != b[14:]
        or a[13] and a[13] != b[13] or a[6] and a[6:10] != b[6:10]):
        raise UnconfirmedGuestEffect('Desktop evidence changed its original scope. No retain or launch was repeated.')
    if result.get('instanceId') != b[6] or result.get('generation') != str(b[7]) or result.get('serial') != str(b[13]):
        raise UnconfirmedGuestEffect('Desktop evidence returned an inconsistent process or serial.')
    return result


async def handoff(control, work, launch):
    token = prepare(launch)
    if token is None:
        return None  # Legacy deployment: no invented scope or retroactive retain.
    record = {'schema': 1, 'launch': launch, 'token': token, 'phase': 'intent', 'createdAt': now()}
    path = work / 'desktop-evidence.json'
    async def call(op):
        nonlocal record, token
        save(work / ('desktop-evidence-' + op + '-intent.json'), {**record, 'operation': op})
        result = await control.call('evidence', evidenceOperation=op, evidenceToken=token)
        if 'transportError' in result:
            # The channel survived the RPC failure. Resolve the exact pre-intent
            # once, without another reference or a replacement app.
            result = await control.call('evidence', evidenceOperation='status', evidenceToken=token)
        if 'transportError' in result:
            raise UnconfirmedGuestEffect('Desktop evidence transport is unconfirmed. Its original token was preserved.')
        result = bound(token, result)
        token = result['token']; record = {**record, **result, 'observedAt': now()}
        save(path, record)
        return result
    save(path, record)
    result = await call('reserve')
    if result['phase'] != 1 or result['result'] not in (0, -7) or result['serial'] == '0':
        return None
    result = await call('offer')
    # A pending launch can promote its already reserved Offer. Polling never
    # creates a new reservation. Keep this bounded by the launch deadline.
    for _ in range(20):
        if result['phase'] != 2: break
        await asyncio.sleep(.1); result = await call('status')
    if result['phase'] != 3 or result['result'] not in (0, -7):
        await call('release')
        return None
    expected = (launch['process_id'], launch['process_generation'])
    if (result['instanceId'], result['generation']) != expected:
        raise UnconfirmedGuestEffect('The retained completion belongs to a different Desktop child.')
    # Canonical token is durable here before ACK makes the lease indefinite.
    result = await call('ack')
    if result['phase'] != 4 or result['result'] not in (0, -7):
        raise UnconfirmedGuestEffect('The original Desktop evidence acknowledgement is unconfirmed.')
    return token


async def release(control, work):
    from recovery import read
    path = work / 'desktop-evidence.json'
    if not path.exists(): return
    record = read(path)
    token = record['token']
    if unpack(token)[13] == 0: return
    save(work / 'desktop-evidence-release-intent.json', record)
    result = await control.call('evidence', evidenceOperation='release', evidenceToken=token)
    if 'transportError' not in result:
        bound(token, result)
        save(work / 'desktop-evidence-release.json', result)


async def query_saved(ssh, deployment, execution_id, work, token, operation='status', offset=0):
    """Fresh observer, fixed own package files; never creates a lease or app."""
    import json
    import re
    from sftp import batch, quote
    from deskrun import exchange
    import uuid
    directory = deployment['guestDirectory']
    if not re.fullmatch(r'[A-Z]:\\Build\\P[A-F0-9]{7}\\D[A-F0-9]{7}', directory, re.IGNORECASE):
        raise DevelopmentFault('The retained observer has no verified deployment directory.')
    from contracts import identity
    identity(execution_id); unpack(token)
    if deployment.get('helperCapabilities', {}).get('desktopEvidenceRecoveryVersion') != 1:
        raise DevelopmentFault('The original observer does not support 8.3 recovery files. Read its original watchdog completion instead; no helper was replaced.')
    if operation not in ('status', 'read', 'release'):
        raise DevelopmentFault('Recovery cannot create or acknowledge evidence.')
    attempt = work / ('evidence-observer-' + uuid.uuid4().hex)
    local = attempt.with_suffix('.intent.json')
    save(local, {'instance': execution_id, 'token': token, 'operation': operation, 'offset': offset})
    guest = '/' + directory[0] + directory[2:].replace(chr(92), '/') + '/E' + execution_id[:7].upper() + '.JSN'
    # Guest SFTP publication is create-only. Replace only this exact own
    # nonce-bound control file while the VM lease excludes another observer.
    await batch(ssh, ['-rm ' + quote(guest), 'put ' + quote(local) + ' ' + quote(guest)])
    response = await exchange(ssh, directory + chr(92) + 'STHELP.R4X ' + execution_id + ' evidence', 10)
    save(attempt.with_suffix('.transport.json'),
        {k: base64.b64encode(v).decode() if isinstance(v, bytes) else v for k, v in response.items()})
    if response['transportUncertain'] or response['sshExitCode'] != 0:
        raise UnconfirmedGuestEffect('The saved evidence observer response is unavailable. No app was restarted.')
    try:
        value = json.loads(response['stdout'].decode().strip().splitlines()[-1])
        if value['version'] != 1 or value['instance'] != execution_id or value['sequence'] != 0 or value['success'] is not True:
            raise ValueError()
        result = value['result']
        if 'transportError' in result: raise ValueError()
    except (ValueError, KeyError, TypeError, IndexError):
        raise UnconfirmedGuestEffect('The saved evidence observer returned no matching receipt.') from None
    return bound(token, result)


async def recover(store, job, host, vm, lease, info):
    """Only read an acknowledged original lease, after exact boot/byte checks."""
    import hashlib
    import os
    from recovery import read, receipt
    from access import SshTransport
    from sftp import download
    from contracts import LIMITS, digest
    from checks import evaluate
    work = store.root / 'ExecutionWork' / job['id']
    path = work / 'desktop-evidence.json'
    if not host or not path.exists(): return None
    record = read(path)
    if record.get('phase') not in (3, 4): return None
    intent = read(work / 'intent.json'); token = record['token']; fields = unpack(token)
    deployment = store.deployment(job['deploymentId'])
    if (intent.get('jobId') != job['id'] or intent.get('target') != job.get('target')
        or intent.get('deploymentId') != deployment['id'] or record['launch']['request'] != (job.get('desktopLaunch') or {}).get('request')
        or (fields[6], str(fields[7])) != (record['launch']['process_id'], record['launch']['process_generation'])):
        raise DevelopmentFault('The saved evidence scope differs from its original job.')
    boot = await host.boots.ensure(vm, info['invocationId'])
    target = intent['target']
    if any(target.get(k) != boot.get(k) for k in ('vmId', 'vmRevision', 'imageId', 'imageSha256', 'bootId')):
        return None  # Never combine an old token with a newly observed boot.
    helper = next((f for f in deployment['files'] if f.get('path', '').endswith('/STHELP.R4X')), None)
    if not helper or deployment.get('helperCapabilities', {}).get('desktopEvidenceVersion') != 1: return None
    directory = deployment['guestDirectory']
    async with SshTransport(host.access, vm, lease) as ssh:
        from exchange import rebind
        deployment, owner_path = await rebind(ssh, info, target, deployment, store.id)
        ssh.package_root = owner_path.rsplit('/', 1)[0]
        directory = deployment['guestDirectory']
        # Read the exact original helper; no helper is replaced for recovery.
        verification = work / ('evidence-helper-' + now().replace(':', '') + '.R4X')
        remote = '/' + directory[0] + directory[2:].replace(chr(92), '/') + '/STHELP.R4X'
        await download(ssh, remote, verification, helper['bytes'])
        if verification.stat().st_size != helper['bytes'] or digest(verification) != helper['sha256']:
            raise DevelopmentFault('The saved observer helper changed; evidence was preserved.')
        verification.unlink()
        # Older immutable observers use a nine-character basename. Their own
        # independent watchdog still leaves a valid 8.3 completion receipt.
        if deployment.get('helperCapabilities', {}).get('desktopEvidenceRecoveryVersion') != 1:
            from watchdog_recovery import recover as watchdog_completion
            try: return await watchdog_completion(store, job, deployment, ssh, work, intent)
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                raise DevelopmentFault('The original watchdog evidence is missing or damaged. Existing receipts and quarantine were preserved.') from None
        async def query(op='status', offset=0):
            return await query_saved(ssh, deployment, intent['executionId'], work, token, op, offset)
        status = await query()
        if status['phase'] != 4 or status['result'] != 0 or status['completionSequence'] == '0': return None
        length = status['outputLength']
        if type(length) is not int or not 0 <= length <= LIMITS['outputBytes']: return None
        data = bytearray()
        while len(data) < length:
            part = await query('read', len(data))
            if part['result'] != 0 or part['completionSequence'] != status['completionSequence'] or part['outputFlags'] != status['outputFlags']:
                raise DevelopmentFault('The retained completion changed during recovery.')
            chunk = base64.b64decode(part['outputBase64'], validate=True)
            if not chunk or len(chunk) > length - len(data): raise DevelopmentFault('The retained output is incomplete.')
            data.extend(chunk)
        incomplete = status.get('outputComplete') is not True
        state = {'state': 'completed', 'closeConfirmed': True, 'exitCode': status['exitCode'],
            'exitReason': status['exitReason'], 'instanceId': fields[6], 'generation': str(fields[7]),
            'outputIncomplete': incomplete, 'completionObserved': True, 'desktopEvidenceRetained': True,
            'completionSequence': int(status['completionSequence']), 'completionFlags': status['outputFlags']}
        # Keep the previous stream, then atomically publish the authoritative
        # native tail and its explicit completeness; never duplicate prefixes.
        output = store.evidence(job['id']) / 'output.log'
        if output.exists() and not (work/'output-before-evidence-recovery.bin').exists():
            from shutil import copyfile
            copyfile(output, work/'output-before-evidence-recovery.bin')
        temporary = output.with_name('retained-' + secrets.token_hex(8) + '.tmp')
        with temporary.open('xb') as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, output)
        from layout import sync
        sync(output.parent)
        process = {**(job.get('process') or {}), 'instanceId': fields[6], 'generation': str(fields[7])}
        proof = {**intent, 'state': 'retained-completion', 'completion': state,
            'outputReceipt': {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}}
        save(work/'retained-completion.json', proof)
        if not (work/'started.json').exists(): save(work/'started.json', {**intent, 'state': 'started', 'process': process})
        result = store.recovered(job['id'], 'completed' if status['exitCode'] == 0 else 'failed',
            receipt('native-retained-completion', guestEndConfirmed=True, cleanupConfirmed=False),
            process=process, guestState=state, exitCode=status['exitCode'], check=evaluate(job['settings'], state, data), error=None)
        # Host output and original completion are durable before last Release.
        try:
            released = await query('release')
            save(work/'desktop-evidence-release.json', released)
        except DevelopmentFault:
            # The durable app result survives a lost last-reference response.
            save(work/'desktop-evidence-release-pending.json', {'token': token, 'observedAt': now()})
        from quarantine import resolve
        resolve(store.projects, vm['id'], job['id'], 'native-retained-completion')
        return result
