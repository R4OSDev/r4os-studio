"""Resolve a guest volume only by its exact offline-published Exchange marker."""
import base64
import hashlib
import re
import string
import uuid
from contracts import DevelopmentFault
from sftp import batch, quote, validate_download

async def resolve(ssh, info, target):
    expected = info.get('exchange')
    if not expected or expected.get('schema') != 1 or expected.get('vmId') != target['vmId']:
        raise DevelopmentFault('Exchange identity is not prepared. Stop and start the assigned VM before deploying.')
    try: data = base64.b64decode(expected['markerBase64'], validate=True)
    except (KeyError, ValueError): raise DevelopmentFault('Invalid expected Exchange identity.') from None
    if len(data) > 4096 or hashlib.sha256(data).hexdigest() != expected.get('markerSha256') or expected.get('marker') != 'STXCHG.JSN':
        raise DevelopmentFault('Invalid expected Exchange identity.')
    # All lookups are read-only, on fixed drive candidates, in one bounded batch.
    candidates = [(drive, ssh.runtime / ('marker-' + uuid.uuid4().hex)) for drive in string.ascii_uppercase]
    try:
        await batch(ssh, ['-get ' + quote('/' + drive + '/STXCHG.JSN') + ' ' + quote(local) for drive, local in candidates], maximum=4096)
        matches = []
        for drive, local in candidates:
            if not local.exists(): continue
            validate_download(local, 4096)
            if local.read_bytes() == data: matches.append(drive)
        if len(matches) != 1:
            raise DevelopmentFault('Exchange marker is missing or ambiguous. No guest files were changed.')
        result = {'schema': 1, 'vmId': target['vmId'], 'generation': expected['generation'],
            'markerSha256': expected['markerSha256'], 'drive': matches[0], 'bootId': target['bootId'],
            'accessRevision': ssh.record['revision']}
        ssh.exchange_target = result
        return result
    finally:
        for _, local in candidates: local.unlink(missing_ok=True)

def require_tree(info):
    if info.get('exchangeWorker', {}).get('buildTreeVersion') != 1:
        raise DevelopmentFault('The running VM uses an older Exchange worker. Stop and start this VM before deploying to Build.')

def directory(target, project_name, deployment_name=None):
    exchange = target.get('exchange') or {}
    drive = exchange.get('drive', '')
    if not re.fullmatch('[A-Z]', drive) or not re.fullmatch('P[A-F0-9]{7}', project_name):
        raise DevelopmentFault('No verified Exchange package target.')
    path = '/' + drive + '/Build/' + project_name
    if deployment_name is not None:
        if not re.fullmatch('D[A-F0-9]{7}', deployment_name): raise DevelopmentFault('Invalid deployment directory.')
        path += '/' + deployment_name
    return path

from sftp_inventory import inventory


def preflight(entries, sizes, new_files, new_directories, output_files=0):
    files = [item for item in entries if not item['directory']]
    # Include create-only SFTP stage/backup slots, final receipts, and registered
    # bounded runtime output. No old package is silently removed to make room.
    required = sum(sizes) + max(sizes, default=0) + 32768 + output_files * 65536
    if len(files) + new_files + 2 + output_files > 128 or len(entries) - len(files) + new_directories > 128 or sum(item['bytes'] for item in files) + required > 96 * 1024 * 1024:
        raise DevelopmentFault('Exchange has insufficient quota for this package, receipts, transfer staging and output. Existing files were preserved.')


def sftp_directory(deployment):
    guest = deployment['guestDirectory'].replace('\\', '/')
    drive, separator, path = guest.partition(':/')
    if not separator or not re.fullmatch('[A-Z]', drive): raise DevelopmentFault('Invalid saved guest directory.')
    return '/' + drive + '/' + path
