"""Observe the known legacy backup-delete failure; never mutate guest files."""
import hashlib
from contracts import DevelopmentFault, digest, hash_value, identity
from jobs import now

LEGACY_HELPER = 'ccc105e60241c024721cc5b4f9cff6ee01feb04520f2d0d11d0bafaa73121f2e'
SOURCE = 'original-desktop-current-files'


def originals(store, job, deployment, pending):
    from recovery import read
    work = store.root / 'DeployWork' / job['id']
    try:
        helper = next((v for v in deployment['files'] if v['path'].endswith('/STHELP.R4X')), None)
        if (job['kind'] != 'deploy' or job.get('desktopShortcutRequested') is not True
                or (job.get('target') or {}).get('helperSha256') != LEGACY_HELPER
                or not helper or helper.get('sha256') != LEGACY_HELPER): raise ValueError()
        transport = read(work / 'desktop-transport.json')
        if (not isinstance(transport, dict)
                or type(transport.get('exitCode')) is not int or transport['exitCode'] != 113
                or transport.get('timedOut') is not False or transport.get('truncated') is not False
                or transport.get('transportUncertain') or transport.get('output') != ''
                or transport.get('stdout') != '' or transport.get('stderr') != ''
                or not isinstance(pending.get('previous'), str)
                or not job['target'].get('bootId') or not pending.get('vmInvocationId')): raise ValueError()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise DevelopmentFault('This publication has no matching known legacy failure. Original effects remain unconfirmed.') from None
    return work


def fields(store, job, deployment, pending):
    work = originals(store, job, deployment, pending)
    return {'schema': 1, 'source': SOURCE, 'projectId': store.id, 'jobId': job['id'],
        'deploymentId': deployment['id'], 'vmId': job['binding']['id'],
        'vmRevision': job['binding']['revision'], 'imageSha256': job['binding']['imageSha256'],
        'vmInvocationId': pending['vmInvocationId'], 'targetSha256': hash_value(job['target']),
        'originalBootId': job['target']['bootId'],
        'originalHelperExitCode': 113, 'nativeCompletionReceiptAvailable': False,
        'guestIntentSha256': digest(work / 'DSKIN.JSN'),
        'originalIntentSha256': digest(work / 'desktop-intent.json'),
        'originalTransportSha256': digest(work / 'desktop-transport.json'),
        'linkPath': pending['path'], 'linkSha256': hashlib.sha256(pending['content'].encode()).hexdigest(),
        'linkBytes': len(pending['content'].encode()), 'publicationMatched': True,
        'originalMarkerReadbackVerified': True, 'packageReadbackVerified': True,
        'stageAbsent': True, 'backupAbsent': True, 'applicationStarted': False}


def file_list(deployment):
    return [{key: item[key] for key in ('path', 'bytes', 'sha256')} for item in deployment['files']]


def verify(store, job, deployment, pending, observation):
    wanted = fields(store, job, deployment, pending)
    if (not isinstance(observation, dict)
            or any(type(observation.get(k)) is not type(v) or observation.get(k) != v for k, v in wanted.items())
            or observation.get('verifiedFiles') != file_list(deployment)
            or not isinstance(observation.get('observedAt'), str) or not observation['observedAt']):
        raise DevelopmentFault('The original publication file observation is incomplete or belongs to another request.')
    identity(observation.get('observedBootId'))


async def observe(store, job, deployment, pending, reader, info, boot_id):
    work = originals(store, job, deployment, pending)
    if info.get('invocationId') != pending['vmInvocationId'] or info['vm']['state'] != 'running':
        raise DevelopmentFault('The original VM service instance changed. Publication was not repeated.')
    guest = '/' + deployment['guestDirectory'][0] + '/' + deployment['guestDirectory'][3:].replace('\\', '/')
    link = pending['path']
    marker = guest + '/DSKINT.JSN'
    reader.paths[marker] = 4096
    request = work / 'DSKIN.JSN'
    original_request = request.read_bytes().decode('utf8')
    if await reader.text(marker) != original_request or await reader.text(link) != pending['content']:
        raise DevelopmentFault('The current guest intent or link differs from the original publication. Files were preserved.')
    # Every original package file is read, including APP, both helpers, the
    # deployment owner and manifest. No newly prepared helper is substituted.
    for item in deployment['files']:
        path, expected = item['path'], item['bytes']
        if (not path.startswith(guest + '/') or type(expected) is not int or expected < 0
                or item.get('fullReadbackVerified') is not True):
            raise DevelopmentFault('The original deployment file binding is incomplete.')
        reader.paths[path] = expected
        before = await reader.stat(path)
        if before is None or not before['regular'] or before['bytes'] != expected:
            raise DevelopmentFault('An original deployment file is missing or changed. Publication remains unconfirmed.')
        handle = await reader.open(path)
        count, hasher = 0, hashlib.sha256()
        try:
            while True:
                chunk = await reader.read(handle, count)
                if not chunk: break
                count += len(chunk)
                if count > expected: raise DevelopmentFault('An original deployment file changed during observation.')
                hasher.update(chunk)
        finally:
            await reader.close(handle)
        if count != expected or hasher.hexdigest() != item['sha256'] or await reader.stat(path) != before:
            raise DevelopmentFault('The original deployment hash changed. Publication remains unconfirmed.')
    if (await reader.text(marker) != original_request or await reader.text(link) != pending['content']
            or await reader.stat(link[:-4] + '.TMP') is not None
            or await reader.stat(link[:-4] + '.BAK') is not None):
        raise DevelopmentFault('The current publication or cleanup differs from the original request. Files were preserved.')
    reader.guard()
    value = {**fields(store, job, deployment, pending), 'verifiedFiles': file_list(deployment),
             'observedBootId': identity(boot_id), 'observedAt': now()}
    verify(store, job, deployment, pending, value)
    return value
