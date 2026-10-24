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
        await batch(ssh, ['-get ' + quote('/' + drive + '/STXCHG.JSN') + ' ' + quote(local) for drive, local in candidates])
        matches = []
        for drive, local in candidates:
            if not local.exists(): continue
            validate_download(local, 4096)
            if local.read_bytes() == data: matches.append(drive)
        if len(matches) != 1:
            raise DevelopmentFault('Exchange marker is missing or ambiguous. No guest files were changed.')
        return {'schema': 1, 'vmId': target['vmId'], 'generation': expected['generation'],
            'markerSha256': expected['markerSha256'], 'drive': matches[0], 'bootId': target['bootId'],
            'accessRevision': ssh.record['revision']}
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
