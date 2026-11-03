"""One durable SDK operation; packages publish independently, defaults commit once."""
import copy
import hashlib
import json
from pathlib import Path
import re
import threading
import uuid

from sdk_sets import SHA256, profile_revision, regular_json, resolve
from service import atomic, now


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
        previous = regular_json(path, 512 * 1024) if path.exists() or path.is_symlink() else None
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
        if previous and previous.get('phase') == 'failed':
            history = list(previous.get('history', []))
            history.append({'phase': 'failed', 'error': previous.get('error'), 'observedAt': now()})
            if len(history) > 16:
                receipt['previousFailuresOmitted'] = receipt.get('previousFailuresOmitted', 0) + len(history) - 16
                history = [history[0], *history[-15:]]
            receipt['history'] = history
        receipt.update(phase='working', error=None)
        atomic(path, receipt)
        manager.busy = True
        manager.job = {'kind': 'sdk', 'action': action, 'requestId': request_id, 'phase': 'working',
                       'message': 'Resolving SDK components…', 'error': None}
        threading.Thread(target=work, args=(manager, path, receipt), daemon=True).start()
        return manager.status()



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
        from sdk_provision import prepare, paths
        records = prepare(manager, selected)
        base, bundle, document, package_paths = paths(manager.root, selected['id'])
        compiler = {**bundle['zig'], 'id': 'sdk-' + bundle['version'],
                    'directory': str(package_paths['install'] / 'Toolchains/Zig'),
                    'binary': str(package_paths['install'] / 'Toolchains/Zig/zig')}
        if request['action'] == 'default':
            with manager.lock:
                if profile_revision(manager.state) != request['expectedRevision']:
                    raise ValueError('The component default changed while the SDK was being prepared. Existing defaults were kept.')
                defaults = copy.deepcopy(manager.state['defaults'])
                defaults.update(records)
                defaults['zig'] = compiler
                from sdk_provision import host_records
                defaults['rust'] = next(record for record in host_records(manager.root, 'rust')
                                        if record['sdkRevision'] == selected['id'])
                state = {**manager.state, 'schema': 1, 'defaults': defaults, 'updatedAt': now(),
                         'sdkSelection': {'requestId': receipt['requestId'], 'id': selected['id'],
                                          'manifestSha256': resolved['manifestSha256']}}
                atomic(manager.profile, state)
                manager.state = state
        receipt.update(phase='complete', completedAt=now())
        atomic(path, receipt)
        manager.progress('The verified SDK package is now the default.' if request['action'] == 'default'
                         else 'The complete SDK package and host tools are verified. Defaults were kept.', phase='complete')
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
