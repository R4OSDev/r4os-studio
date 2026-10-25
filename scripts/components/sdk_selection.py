"""One durable SDK operation; packages publish independently, defaults commit once."""
import copy
import hashlib
import json
from pathlib import Path
import re
import tempfile
import threading
import uuid

from common import download, publish, unpack
from sdk_sets import PARTS, SHA256, profile_revision, regular_json, resolve
from service import FOLDERS, atomic, now, package_info, run


def receipt_path(manager, request_id):
    if not isinstance(request_id, str) or str(uuid.UUID(request_id)) != request_id:
        raise ValueError('Invalid SDK operation identity.')
    directory = manager.root / 'Profiles/SDK-Operations'
    if directory.is_symlink() or (directory.exists() and directory.resolve() != directory):
        raise ValueError('Invalid SDK operation directory.')
    directory.mkdir(parents=True, exist_ok=True)
    return directory / (request_id + '.json')


def start(manager, action, identity, request_id=None, expected_revision=None, manifest_hash=None):
    if action not in ('download', 'default') or not isinstance(identity, str) or not re.fullmatch('[a-f0-9]{40}', identity):
        raise ValueError('Invalid SDK operation.')
    if request_id is not None and (not isinstance(expected_revision, str) or not SHA256.fullmatch(expected_revision)):
        raise ValueError('An SDK operation must bind the expected component profile.')
    if manifest_hash is not None and (not isinstance(manifest_hash, str) or not SHA256.fullmatch(manifest_hash)):
        raise ValueError('Invalid SDK release checksum.')
    with manager.lock:
        request_id = request_id or str(uuid.uuid4())
        path = receipt_path(manager, request_id)
        previous = regular_json(path, 65536) if path.exists() or path.is_symlink() else None
        expected_revision = expected_revision or profile_revision(manager.state)
        request = {'id': identity, 'action': action, 'expectedRevision': expected_revision, 'manifestSha256': manifest_hash}
        if previous and (previous.get('schema') != 1 or previous.get('request') != request):
            raise ValueError('This SDK operation identity belongs to a different request.')
        if previous and (previous.get('phase') == 'complete'
                         or manager.state.get('sdkSelection', {}).get('requestId') == request_id):
            if previous.get('phase') != 'complete':
                previous.update(phase='complete', completedAt=now())
                atomic(path, previous)
            return {**manager.status(), 'sdkOperation': {'requestId': request_id, 'phase': 'complete'}}
        if manager.busy:
            if manager.job.get('requestId') == request_id:
                return manager.status()
            raise ValueError('Another component operation is already running.')
        if action == 'default' and profile_revision(manager.state) != expected_revision:
            raise ValueError('The component default changed. Refresh before selecting an SDK again.')
        selected = next((value for value in manager.installed('sdk') + manager.catalogs.get('sdk', {}).get('versions', [])
                         if value['id'] == identity), None)
        if not selected and previous:
            selected = previous.get('selected')
        if not selected or selected.get('id') != identity:
            raise ValueError('Check the official SDK version list before selecting this version.')
        releases = manager.catalogs.get('sdk', {}).get('sdkReleases')
        if releases is not None:
            selected = {**selected, 'sdkRelease': releases.get(identity, {'published': False})}
        receipt = previous or {'schema': 1, 'requestId': request_id, 'request': request, 'selected': selected, 'createdAt': now()}
        receipt.update(phase='working', error=None)
        atomic(path, receipt)
        manager.busy = True
        manager.job = {'kind': 'sdk', 'action': action, 'requestId': request_id, 'phase': 'working',
                       'message': 'Resolving SDK components…', 'error': None}
        threading.Thread(target=work, args=(manager, path, receipt), daemon=True).start()
        return manager.status()


def compiler_for(manager, version):
    compiler = next((value for value in manager.installed('zig') if value['version'] == version), None)
    if not compiler:
        raise ValueError(f'Download Zig {version} before verifying this SDK set.')
    return compiler


def verify_contents(manager, kind, source, expected, selected, temporary, installed=None):
    info = package_info(source)
    if info['version'] != expected['version']:
        raise ValueError(f'The {kind} package version contradicts the SDK release.')
    metadata_hash = hashlib.sha256((source / 'build.zig.zon').read_text().strip().encode()).hexdigest()
    if installed and installed.get('metadataHash') and installed['metadataHash'] != metadata_hash:
        raise ValueError(f'The installed {kind} package metadata has changed.')
    if kind == 'sdk' and (info != {key: selected[key] for key in ('version', 'minZigVersion', 'dependencies') if key in selected}
                          or selected.get('metadataHash') and selected['metadataHash'] != metadata_hash):
        raise ValueError('SDK archive contents contradict the selected official source metadata.')
    pin = info.get('dependencies', {}).get('contract')
    contract = manager.sdk_sets[selected['id']]['components']['contract']
    if pin and (pin.get('revision') != contract['revision'] or pin.get('packageHash') != contract['packageHash']):
        raise ValueError(f'The {kind} package requires a different Contract identity.')
    compiler = compiler_for(manager, info.get('minZigVersion') or selected.get('minZigVersion'))
    verification = temporary / 'verify'
    verification.mkdir()
    (verification / 'build.zig').write_text('pub fn build(_: *@import("std").Build) void {}\n')
    manager.progress(f'Verifying {kind} package contents…', received=0, total=0)
    hashed = run([compiler['binary'], 'fetch', '--global-cache-dir', str(verification / 'cache'), str(source)],
                 cwd=verification, timeout=180)
    if not re.fullmatch('[A-Za-z0-9_.+-]+', hashed):
        raise ValueError('The compiler returned an invalid package hash.')
    previous_hash = (installed.get('zigPackageHash') or installed.get('packageHash')) if installed else None
    if installed and (not previous_hash or hashed != previous_hash):
        raise ValueError(f'The installed {kind} package contents no longer match their recorded hash.')
    if expected.get('packageHash') and hashed != expected['packageHash']:
        raise ValueError(f'The {kind} package contents contradict the SDK package pin.')
    return {**info, 'metadataHash': metadata_hash, 'packageHash': hashed}


def ensure_package(manager, kind, expected, selected):
    root = manager.root / FOLDERS[kind]
    if root.is_symlink() or root.resolve() != root:
        raise ValueError('Invalid component directory.')
    root.mkdir(parents=True, exist_ok=True)
    target = root / expected['revision']
    installed = next((value for value in manager.installed(kind) if value['id'] == expected['revision']), None)
    with tempfile.TemporaryDirectory(prefix='.sdk-set-', dir=root) as name:
        temporary = Path(name)
        if installed:
            if (target.is_symlink() or target.resolve() != target or installed.get('revision') != expected['revision']
                    or installed['version'] != expected['version'] or installed.get('sourceUrl') != expected['sourceUrl']):
                raise ValueError(f'The installed {kind} identity does not match the SDK release.')
            verify_contents(manager, kind, target, expected, selected, temporary, installed)
            # Preserve the archive origin and checksum of the existing layout.
            return installed
        if target.exists() or target.is_symlink():
            raise ValueError(f'An incomplete {kind} installation exists and will not be overwritten.')
        archive = temporary / 'package.tar.gz'
        manager.progress(f'Downloading SDK component: {kind}…', received=0, total=expected['bytes'])
        archive_hash = download(manager, expected['url'], archive, expected['sha256'], limit=expected['bytes'])
        if archive.stat().st_size != expected['bytes']:
            raise ValueError(f'The {kind} archive size contradicts the SDK release.')
        source = unpack(archive, temporary / 'unpacked')
        info = verify_contents(manager, kind, source, expected, selected, temporary)
        record = {**info, 'id': expected['revision'], 'revision': expected['revision'],
                  'sourceUrl': expected['sourceUrl'], 'archiveUrl': expected['url'], 'sha256': archive_hash,
                  'sdkReleaseManifestSha256': manager.sdk_sets[selected['id']]['manifestSha256'], 'installedAt': now()}
        (source / '.studio-component.json').write_text(json.dumps(record, indent=2) + '\n')
        publish(source, target)
        return {**record, 'directory': str(target)}


def work(manager, path, receipt):
    request, selected = receipt['request'], receipt['selected']
    try:
        resolved = resolve(manager, selected)
        expected_hash = receipt.get('resolvedManifestSha256') or request.get('manifestSha256')
        if expected_hash and expected_hash != resolved['manifestSha256']:
            raise ValueError('The SDK release metadata changed. Start a new selection after refreshing.')
        receipt['resolvedManifestSha256'] = resolved['manifestSha256']
        atomic(path, receipt)
        with manager.lock:
            manager.sdk_sets[selected['id']] = resolved
        compiler = compiler_for(manager, selected.get('minZigVersion'))
        records = {kind: ensure_package(manager, kind, resolved['components'][kind], selected) for kind in PARTS}
        library = records['libraries']
        minimum = library.get('minZigVersion')
        if minimum and tuple(map(int, minimum.split('.'))) > tuple(map(int, compiler['version'].split('.'))):
            raise ValueError('The Libraries require a newer compiler than the SDK profile.')
        if request['action'] == 'default':
            with manager.lock:
                if profile_revision(manager.state) != request['expectedRevision']:
                    raise ValueError('The component default changed while the SDK was being prepared. Existing defaults were kept.')
                defaults = copy.deepcopy(manager.state['defaults'])
                defaults.update(records)
                defaults['zig'] = compiler
                state = {**manager.state, 'schema': 1, 'defaults': defaults, 'updatedAt': now(),
                         'sdkSelection': {'requestId': receipt['requestId'], 'id': selected['id'],
                                          'manifestSha256': resolved['manifestSha256']}}
                atomic(manager.profile, state)
                manager.state = state
        receipt.update(phase='complete', completedAt=now())
        atomic(path, receipt)
        manager.progress('SDK, Contract and Libraries are now the default.' if request['action'] == 'default'
                         else 'SDK, Contract and Libraries downloaded and verified. Defaults were kept.', phase='complete')
    except Exception as error:
        # A directory fsync may fail after the atomic profile replacement.
        # Inspect that publication before deciding whether a retry may commit.
        try:
            published = regular_json(manager.profile, 16 * 1024 * 1024)
            if published.get('sdkSelection', {}).get('requestId') == receipt['requestId']:
                with manager.lock:
                    manager.state = published
        except (OSError, ValueError, TypeError):
            pass
        committed = manager.state.get('sdkSelection', {}).get('requestId') == receipt['requestId']
        receipt.update(phase='complete' if committed else 'failed', error=str(error)[:1600])
        try:
            atomic(path, receipt)
        except OSError:
            pass
        manager.progress('SDK defaults committed; retry this operation to recover its receipt.' if committed
                         else 'The SDK operation failed. Existing defaults and installations were kept.',
                         phase='complete' if committed else 'failed', error=None if committed else str(error)[:1600])
    finally:
        with manager.lock:
            manager.busy = False
