"""Immutable package proposals from native-confirmed project artifacts, no guest effects."""
import json
import re
import stat
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1] / "components"))
from r4upack import pin as pin_packer
import uuid
from contracts import DevelopmentFault, digest, encode, hash_value, identity, LIMITS
from jobs import now

MAX_PAYLOADS = 32
MAX_REQUIREMENTS = 32
MAX_MANIFEST = 32768
MAX_PACKAGE = min(LIMITS['packageBytes'], 128 * 1024 * 1024)
KINDS = {'R4X': {'software', 'service'}, 'R4L': {'system-library'}, 'R4D': {'driver'}, 'R4P': {'protocol'}, 'KERNEL': {'boot-kernel'}}


def plain(value, limit, label):
    if (not isinstance(value, str) or not value or len(value.encode()) > limit
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 or c in '<>' for c in value)):
        raise DevelopmentFault('Use bounded single-line plain UTF-8 ' + label + '.', 400)
    return value


def token(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]{0,47}', value):
        raise DevelopmentFault('Use an ASCII ' + label + ' of at most 48 characters.', 400)
    return value


def version(value):
    if (not isinstance(value, str) or len(value) > 24 or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value)
            or any(int(part) > 4294967295 for part in value.split('.'))):
        raise DevelopmentFault('Use a native three-part numeric version of at most 24 bytes.', 400)
    return value


def target(value):
    if not isinstance(value, str) or len(value) > 1023 or not value.isascii():
        raise DevelopmentFault('Use a bounded ASCII system installation target.', 400)
    value = value.replace('\\', '/')
    if re.match(r'^[A-Za-z]:', value):
        if not value.startswith('C:/'): raise DevelopmentFault('Only the system drive C: is supported.', 400)
        value = value[2:]
    if not value.startswith('/') or value.endswith('/'): raise DevelopmentFault('Use an absolute system target.', 400)
    parts = [part for part in value.split('/') if part]
    if not parts or any(part in ('.', '..') or part[-1] in '. ' or any(ord(c) < 32 or ord(c) >= 127 or c in '"*:;<>?|=' for c in part) for part in parts):
        raise DevelopmentFault('Invalid system installation target.', 400)
    canonical = '/' + '/'.join(parts)
    if canonical.casefold() in ('/r4os/config/version.r4s', '/r4os/config/modules.json'):
        raise DevelopmentFault('Updater-managed release/inventory files cannot be payloads.', 400)
    return canonical


def kind_target(kind, path):
    path = path.upper()
    if kind == 'KERNEL': return path == '/BOOT/R4OS.ELF'
    if kind == 'R4L': return path.startswith('/R4OS/LIBS/') and path.endswith('.R4L')
    if kind == 'R4D': return path.startswith('/R4OS/DRIVERS/') and path.endswith('.R4D')
    if kind == 'R4P': return path.startswith('/R4OS/PROTOCOLS/') and path.endswith('.R4P')
    return kind == 'R4X' and path.endswith('.R4X') and path.startswith(('/R4OS/SOFTWARE/', '/SOFTWARE/', '/R4OS/SERVICES/', '/R4OS/SUBSYSTEMS/'))


def requirement(value):
    if not isinstance(value, dict) or set(value) != {'kind', 'name', 'target', 'minVersion', 'state'}:
        raise DevelopmentFault('A requirement needs exactly kind, name, target, minVersion and state.', 400)
    kind = value['kind']
    if not isinstance(kind, str) or kind not in KINDS or value['state'] not in ('installed', 'active') or (value['state'] == 'active' and kind != 'KERNEL'):
        raise DevelopmentFault('Only kernel requirements can require active state.', 400)
    canonical = target(value['target']); name = token(value['name'], 'component name')
    if not kind_target(kind, canonical): raise DevelopmentFault('The requirement kind and target do not match.', 400)
    if (kind == 'KERNEL' and name != 'KERNEL') or (kind != 'KERNEL' and canonical.rsplit('/', 1)[-1].rsplit('.', 1)[0].casefold() != name.casefold()):
        raise DevelopmentFault('The requirement name and target do not match.', 400)
    result = {**value, 'target': canonical, 'minVersion': version(value['minVersion'])}
    result['spec'] = '|'.join([kind, name, canonical, result['minVersion'], value['state']])
    return result


def tables(store):
    with store.db:
        store.db.execute('CREATE TABLE IF NOT EXISTS update_settings(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,payload TEXT NOT NULL)')
        store.db.execute('INSERT OR IGNORE INTO update_settings VALUES(1,1,?)', (encode({'metadata': None, 'requirements': []}),))
        store.db.execute('''CREATE TABLE IF NOT EXISTS update_plans(id TEXT PRIMARY KEY,request_id TEXT UNIQUE NOT NULL,
            request_hash TEXT NOT NULL,payload TEXT NOT NULL)''')


def settings(store):
    tables(store)
    row = store.db.execute('SELECT revision,payload FROM update_settings WHERE id=1').fetchone()
    return {'revision': row['revision'], **json.loads(row['payload'])}


def read(store, ident):
    tables(store)
    row = store.db.execute('SELECT payload FROM update_plans WHERE id=?', (identity(ident),)).fetchone()
    if not row: raise DevelopmentFault('Update package plan not found.', 404)
    value = json.loads(row[0]); expected = value['sha256']
    if value['projectId'] != store.id or hash_value({key: item for key, item in value.items() if key != 'sha256'}) != expected:
        raise DevelopmentFault('The update package plan identity changed. Existing data was preserved.', 503)
    return value


def options(store):
    return {'settings': settings(store), 'projectRevision': store.project['revision'], 'limits': {
        'payloads': MAX_PAYLOADS, 'requirements': MAX_REQUIREMENTS, 'manifestBytes': MAX_MANIFEST,
        'packageBytes': MAX_PACKAGE, 'nativeContainerBytes': 4294967295, 'batchPackages': 16, 'batchComponents': 32, 'batchRequirements': 32},
        'artifacts': [artifact_option(store, row['id']) for row in store.db.execute('SELECT id FROM artifacts ORDER BY rowid DESC LIMIT 20')],
        'plans': [json.loads(row[0]) for row in store.db.execute('SELECT payload FROM update_plans ORDER BY rowid DESC LIMIT 10')]}


def artifact_option(store, ident):
    value = store.artifact_metadata(ident)
    native = value.get('updateMetadata', {})
    return {key: entry for key, entry in value.items() if key not in ('plan', 'updateMetadata')} | {
        'updateMetadata': {key: entry for key, entry in native.items() if key != 'manifest'}}

def payload(store, artifact_id):
    record = store.artifact(identity(artifact_id))
    if record.get('projectId') != store.id or record.get('pins') != store.project['pins']:
        raise DevelopmentFault('Use an artifact from this project and its current pins.')
    native = record.get('updateMetadata', {})
    if not native.get('available'):
        raise DevelopmentFault('This build has no native update identity. Build the project with Studio0.4.12 or newer before planning a package.')
    value = native['identity']; manifest = native['manifest']
    if (native.get('sdkRevision') != record['pins']['sdk']['revision'] or value.get('schema') != 1
            or value.get('kind') != record['kind'] or value.get('name', '').casefold() != manifest.get('name', '').casefold()
            or value.get('version') != manifest.get('module_version') or value.get('target') != target(manifest.get('target'))
            or manifest.get('kind') != record['kind']):
        raise DevelopmentFault('The native artifact identity differs from its captured SDK manifest.')
    canonical = target(value['target']); kind = native.get('payloadKind')
    if kind not in KINDS.get(value['kind'], set()) or not kind_target(value['kind'], canonical):
        raise DevelopmentFault('This native component kind/target is not supported.')
    if (kind == 'service') != canonical.upper().startswith('/R4OS/SERVICES/'):
        raise DevelopmentFault('Service payloads require their native service target.')
    name = canonical.rsplit('/', 1)[-1].rsplit('.', 1)[0]
    if name.casefold() != value['name'].casefold(): raise DevelopmentFault('Artifact name differs from the native installation target.')
    version(value['version']); token(value['name'], 'component name')
    if value.get('activation') not in ('live', 'restart') or value.get('priority') not in ('normal', 'foundation'):
        raise DevelopmentFault('The native update activation/priority is unavailable.')
    build = store.get(record['buildId']); source = build.get('source')
    manifest_file = store.root / 'Inputs' / record['buildId'] / 'module.R4MF'
    try:
        info = manifest_file.lstat()
        if (not source or record['manifestSha256'] != source['manifestSha256'] or source['sha256'] != record['sourceSha256']
                or manifest_file.resolve(strict=True) != manifest_file or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_size > 65536 or digest(manifest_file) != record['manifestSha256']):
            raise ValueError()
    except (OSError, ValueError): raise DevelopmentFault('The captured module manifest is missing or changed; no plan was created.') from None
    files = record['files']
    entry = next((file for file in files if file['path'] == record['entry']), None)
    if entry is None: raise DevelopmentFault('The artifact entry is absent from its confirmed file receipt.')
    return {'artifactId': record['id'], 'buildId': record['buildId'], 'file': entry, 'kind': kind,
        'target': 'C:' + canonical.replace('/', '\\'), 'canonicalTarget': canonical, 'component': value,
        'sourceSha256': record['sourceSha256'], 'manifestSha256': record['manifestSha256'],
        'artifactPackageSha256': record['packageSha256'], 'buildProof': record['buildProof'],
        'nativeInspectorSha256': native['inspectorSha256'], 'nativeAdapterSha256': native['adapterSha256']}


def selected_packer(store):
    config = Path('/etc/r4os-studio-components/config.json')
    external = None
    if config.is_file():
        info = config.lstat()
        if config.resolve(strict=True) != config or info.st_uid != 0 or info.st_mode & 0o022 or info.st_size > 65536:
            raise DevelopmentFault('The administrator component configuration is not trusted.', 503)
        value = json.loads(config.read_text())
        if value.get('root') == str(store.r4os):
            external = value.get('external', {}).get('r4upack')
    try: return pin_packer(store.r4os, external)
    except (OSError, ValueError, KeyError, TypeError) as error: raise DevelopmentFault(str(error), 409) from None

def create(store, request):
    expected = {'requestId', 'projectRevision', 'configurationRevision', 'metadata', 'artifactIds', 'requirements'}
    if not isinstance(request, dict) or set(request) != expected: raise DevelopmentFault('Unexpected update plan fields.', 400)
    key = identity(request['requestId']); fingerprint = hash_value(request)
    tables(store)
    previous = store.db.execute('SELECT id,request_hash FROM update_plans WHERE request_id=?', (key,)).fetchone()
    if previous:
        if previous['request_hash'] != fingerprint: raise DevelopmentFault('This plan request ID belongs to different input.')
        return read(store, previous['id'])
    current = settings(store)
    if (type(request['projectRevision']) is not int or type(request['configurationRevision']) is not int
            or request['projectRevision'] != store.project['revision'] or request['configurationRevision'] != current['revision']):
        raise DevelopmentFault('Project or update package configuration changed. Reload before planning.')
    metadata = request['metadata']
    if not isinstance(metadata, dict) or set(metadata) != {'packageId', 'packageVersion', 'targetRelease', 'title', 'description'}:
        raise DevelopmentFault('Supply explicit package ID/version, target release, title and description.', 400)
    metadata = {'packageId': token(metadata['packageId'], 'package ID'), 'packageVersion': version(metadata['packageVersion']),
        'targetRelease': version(metadata['targetRelease']), 'title': plain(metadata['title'], 96, 'title'),
        'description': plain(metadata['description'], 2048, 'description')}
    ids = request['artifactIds']; requirements = request['requirements']
    if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_PAYLOADS or not all(isinstance(value, str) for value in ids) or len(set(ids)) != len(ids):
        raise DevelopmentFault('Select1–32 distinct confirmed artifacts.', 400)
    if not isinstance(requirements, list) or len(requirements) > MAX_REQUIREMENTS: raise DevelopmentFault('At most32 concrete requirements are supported.', 400)
    payloads = [payload(store, value) for value in ids]
    targets = [value['canonicalTarget'].casefold() for value in payloads]
    if len(set(targets)) != len(targets): raise DevelopmentFault('Payload installation targets must be distinct.', 400)
    needs = [requirement(value) for value in requirements]
    if len({(value['kind'], value['name'].casefold()) for value in needs}) != len(needs) or len({value['target'].casefold() for value in needs}) != len(needs):
        raise DevelopmentFault('Requirements must have distinct component identities and targets.', 400)
    # Conservative Studio bound, followed by native validation during packaging.
    manifest_bound = 1024 + sum(len(value.encode()) for value in metadata.values())
    manifest_bound += sum(512 + len(value['target']) + len(value['component']['name']) + len(value['component']['version']) for value in payloads)
    manifest_bound += sum(256 + len(value['spec']) for value in needs)
    total = 64 + manifest_bound + sum(value['file']['bytes'] for value in payloads)
    if manifest_bound > MAX_MANIFEST or total > MAX_PACKAGE or total > 4294967295:
        raise DevelopmentFault('The proposed package exceeds the manifest/container or128-MiB Studio quota.', 400)
    packer = selected_packer(store)
    plan = {'schema': 1, 'id': str(uuid.uuid4()), 'projectId': store.id, 'projectRevision': store.project['revision'],
        'configurationRevision': current['revision'] + 1, 'createdAt': now(), 'metadata': metadata,
        'payloads': payloads, 'requirements': needs, 'pins': store.project['pins'],
        'packer': {key: packer[key] for key in ('id', 'version', 'revision', 'sdkRevision', 'host', 'sha256', 'profileSha256')},
        'activation': 'restart' if any(value['component']['activation'] == 'restart' for value in payloads) else 'live',
        'priority': 'foundation' if any(value['component']['priority'] == 'foundation' for value in payloads) else 'normal',
        'manifestByteUpperBound': manifest_bound, 'containerByteUpperBound': total,
        'batch': {'packages': 1, 'components': len(payloads), 'requirements': len(needs)},
        'nativeValidation': 'required-at-build', 'targetReleaseSource': 'explicit-offline-selection'}
    plan['sha256'] = hash_value(plan)
    store.db.execute('BEGIN IMMEDIATE')
    try:
        actual = store.db.execute('SELECT revision FROM update_settings WHERE id=1').fetchone()[0]
        if actual != current['revision']: raise DevelopmentFault('Update package configuration changed. Reload before planning.')
        store.db.execute('INSERT INTO update_plans VALUES(?,?,?,?)', (plan['id'], key, fingerprint, encode(plan)))
        store.db.execute('UPDATE update_settings SET revision=?,payload=? WHERE id=1', (plan['configurationRevision'], encode({'metadata': metadata, 'requirements': requirements})))
        store.db.commit()
    except BaseException: store.db.rollback(); raise
    return plan


def batch(store, ids):
    if not isinstance(ids, list) or not 1 <= len(ids) <= 16 or not all(isinstance(value, str) for value in ids) or len(set(ids)) != len(ids): raise DevelopmentFault('Select1–16 distinct package plans.', 400)
    values = [read(store, ident) for ident in ids]
    if len({value['metadata']['targetRelease'] for value in values}) != 1: raise DevelopmentFault('A batch must have one explicit target release.', 400)
    components = sum(len(value['payloads']) for value in values); needs = sum(len(value['requirements']) for value in values)
    if components > 32 or needs > 32: raise DevelopmentFault('The aggregate batch exceeds32 components or requirements.', 400)
    targets = [part['canonicalTarget'].casefold() for value in values for part in value['payloads']]
    if len(set(targets)) != len(targets): raise DevelopmentFault('A batch cannot replace the same target twice.', 400)
    return {'planIds': ids, 'packages': len(values), 'components': components, 'requirements': needs,
        'guestVerificationRequired': True, 'crossPackageRequirementsDeferred': False}
