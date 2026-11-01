"""Explicit installed SDK selection; original receipts reconcile file/catalog publication."""
import base64
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from types import SimpleNamespace

from layout import folder, project_directory, save, sync
from project_maintenance import project, require_idle, busy
from project_use import acquire, project_id
from store import connect, public, ProjectFault

sys.path.append(str(Path(__file__).resolve().parents[1] / 'components'))
from sdk_sets import resolve, regular_json


def hashed(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def read(path, limit=65536):
    folder(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise ProjectFault('Invalid project pin metadata. Existing files were preserved.', 409)
        return stream.read(limit + 1)


def marker(path):
    folder(path)
    return json.loads(read(path / '.studio-component.json', 2 * 1024**2))


def component(value, kind):
    pin = {k: value[k] for k in ('version', 'revision', 'sha256') if k in value}
    pin['url'] = value.get('url') or value.get('archiveUrl')
    if kind != 'zig': pin['zigPackageHash'] = value.get('zigPackageHash') or value.get('packageHash')
    elif value.get('binarySha256'): pin['binarySha256'] = value['binarySha256']
    if (not re.fullmatch(r'\d+\.\d+\.\d+', pin.get('version', ''))
            or not re.fullmatch('[a-f0-9]{64}', pin.get('sha256', '')) or not pin['url']
            or kind != 'zig' and (not re.fullmatch('[a-f0-9]{40}', pin.get('revision', '')) or not pin['zigPackageHash'])):
        raise ValueError('Installed component metadata is incomplete.')
    return pin


def choices(root, current):
    defaults = regular_json(root / 'Profiles/versions.json', 4 * 1024**2)['defaults']
    result = []
    for path in sorted((root / 'SDK').iterdir()):
        if not re.fullmatch('[a-f0-9]{40}', path.name): continue
        item = {'sdkId': path.name, 'available': False, 'isDefault': path.name == defaults.get('sdk', {}).get('revision')}
        try:
            sdk = marker(path); item['version'] = sdk['version']
            selection = resolve(SimpleNamespace(root=root), {**sdk, 'id': path.name}, fetch=False)
            if selection['state'] != 'ready': raise ValueError(selection['reason'])
            contract_id = selection['components']['contract']['revision']
            contract = marker(root / 'Contract' / contract_id)
            if contract.get('revision') != contract_id: raise ValueError('The installed Contract identity changed.')
            zig_version = sdk['minZigVersion']; zig = marker(root / 'Toolchains/Zig' / zig_version)
            if zig['version'] != zig_version: raise ValueError('The installed Zig identity changed.')
            if sdk.get('revision') != path.name: raise ValueError('The installed SDK identity changed.')
            selected = {'sdk': component(sdk, 'sdk'), 'contract': component(contract, 'contract'), 'zig': component(zig, 'zig')}
            # Candidate identities stay bound to installed metadata, including Rust's full file inventory.
            identities = [sdk, contract, zig]
            if current['language'] == 'Rust':
                saved = regular_json(root / 'Profiles/SDK-Sets' / (path.name + '.json'), 6 * 1024**2)
                release = json.loads(base64.b64decode(saved['body'], validate=True))
                requirement = release['devkit']
                preferred = [current['pins'].get('rust', {}).get('id'), defaults.get('rust', {}).get('id')]
                installations = sorted((root / 'Toolchains/Rust').iterdir(), key=lambda p: (preferred.index(p.name) if p.name in preferred else len(preferred), p.name))
                for installed in installations:
                    record = marker(installed)
                    if record.get('version') == requirement['rust_version'] and record.get('cargoVersion') == requirement['cargo_version']:
                        selected['rust'] = {'id': installed.name, 'version': record['version']}
                        identities.append(record); break
                if 'rust' not in selected: raise ValueError('Install the SDK-compatible Rust toolchain in System → Updates → Components.')
            item.update(available=True, components=selected,
                        selectionId=hashed({'project': current['id'], 'revision': current['revision'], 'pins': current['pins'],
                                            'manifest': selection['manifestSha256'], 'components': identities}))
        except FileNotFoundError:
            item['reason'] = 'Matching installed Contract or compiler is missing. Prepare this SDK in System → Updates → Components.'
        except (ValueError, KeyError, OSError, ProjectFault) as error:
            item['reason'] = str(error) if isinstance(error, (ValueError, ProjectFault)) else 'The installed SDK set is incomplete. Check System → Updates → Components.'
        result.append(item)
    return sorted(result, key=lambda v: tuple(int(n) for n in v.get('version', '0.0.0').split('.')), reverse=True)


def storage(projects, identity, create=False):
    directory = project_directory(projects, identity)
    base = directory / '.studio/pins'
    for path in (directory / '.studio', base, base / 'Requests'):
        if create: path.mkdir(mode=0o700, exist_ok=True)
        if path.exists() or path.is_symlink(): folder(path)
        if create: sync(path.parent)
    return base


def gate_path(projects, identity):
    path = projects / '.studio/project-pins'
    if path.exists() or path.is_symlink(): folder(path)
    return path / (identity + '.json')


def original(base, identity, request_id):
    path = base / 'Requests' / (request_id + '.json')
    if not path.exists() and not path.is_symlink(): return None
    value = json.loads(read(path, 262144))
    if value.get('schema') != 1 or value.get('projectId') != identity or value.get('requestId') != request_id:
        raise ProjectFault('The original pin-change receipt is invalid.', 503)
    return value


def pending(base, projects, identity):
    gate = gate_path(projects, identity)
    if gate.exists() or gate.is_symlink():
        value = json.loads(read(gate)); project_id(value['requestId'])
        if value.get('projectId') != identity: raise ProjectFault('Invalid pin-change reservation.', 503)
        return value['requestId']
    for path in sorted((base / 'Requests').glob('*.json')):
        value = original(base, identity, project_id(path.stem))
        if not value.get('result'): return value['requestId']
    return None


def receipt(projects, identity, request_id):
    project_id(request_id)
    base = storage(projects, identity)
    value = original(base, identity, request_id)
    if not value: return {'requestId': request_id, 'state': 'missing'}
    return value.get('result') or {'requestId': request_id, 'state': 'unknown', 'input': value['input'],
                                 'message': 'Retry the original pin change to finish publication.'}


def options(projects, root, identity):
    with acquire(projects, identity, pins_recovery=True):
        current = project(projects, identity); base = storage(projects, identity)
        return {'project': current, 'choices': choices(root, current), 'available': not busy(projects, identity),
                'pendingRequestId': pending(base, projects, identity)}


def publish(projects, identity, base, value):
    """A durable project gate keeps readers/workers out until both stores agree."""
    work = folder(project_directory(projects, identity) / 'Workspace')
    parent = folder(work / '.r4os-studio'); target = parent / 'project.json'
    if [work.stat().st_dev, work.stat().st_ino, parent.stat().st_ino] != value['workspaceIdentity']:
        raise ProjectFault('The original Workspace changed. Pin-change data was preserved.', 409)
    raw = read(target) if target.exists() or target.is_symlink() else None
    old = base64.b64decode(value['oldMetadata']) if value['oldMetadata'] is not None else None
    new = base64.b64decode(value['newMetadata'])
    if raw not in (old, new): raise ProjectFault('Portable project metadata changed. The original pin change was preserved.', 409)
    with closing(connect(projects)) as db:
        db.execute('BEGIN IMMEDIATE')
        current = public(db.execute("SELECT * FROM projects WHERE id=? AND state='ready'", (identity,)).fetchone(), db)
        before = current['revision'] == value['revision'] and current['pins'] == value['oldPins']
        after = current['revision'] == value['revision'] + 1 and current['pins'] == value['newPins']
        if not (before or after): raise ProjectFault('The original project revision changed. Pin-change data was preserved.', 409)
        if raw != new:
            tmp = base / 'metadata.new'
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream: stream.write(new); stream.flush(); os.fsync(stream.fileno())
            os.replace(tmp, target); sync(parent); sync(base)
        if before:
            db.execute('UPDATE projects SET pins=?,revision=revision+1,updated_at=? WHERE id=?',
                       (json.dumps(value['newPins']), value['updatedAt'], identity)); db.commit()
        current = public(db.execute('SELECT * FROM projects WHERE id=?', (identity,)).fetchone(), db)
    value['result'] = {'requestId': value['requestId'], 'state': 'complete', 'project': current}
    save(base / 'Requests' / (value['requestId'] + '.json'), value)
    gate = gate_path(projects, identity)
    if gate.exists(): gate.unlink(); sync(gate.parent)
    return value['result']


def apply(projects, root, identity, data, hosts):
    if (not isinstance(data, dict) or set(data) != {'requestId', 'revision', 'sdkId', 'selectionId'}
            or type(data['revision']) is not int or data['revision'] < 1
            or not isinstance(data['sdkId'], str) or not re.fullmatch('[a-f0-9]{40}', data['sdkId'])
            or not isinstance(data['selectionId'], str) or not re.fullmatch('[a-f0-9]{64}', data['selectionId'])):
        raise ProjectFault('Supply a current installed SDK selection.', 400)
    request_id = project_id(data['requestId'])
    with acquire(projects, identity, exclusive=True, pins_recovery=True):
        base = storage(projects, identity, create=True)
        value = original(base, identity, request_id)
        if value and value['input'] != data: raise ProjectFault('This request ID belongs to another pin change.', 409)
        if value and value.get('result'):
            gate = gate_path(projects, identity)
            if gate.exists() and json.loads(read(gate)).get('requestId') == request_id:
                gate.unlink(); sync(gate.parent)
            return value['result']
        previous = pending(base, projects, identity)
        if previous and previous != request_id: raise ProjectFault('Finish the original pin change before selecting another SDK.', 409)
        require_idle(projects, identity)
        from remote_binding import assert_change_safe
        assert_change_safe(projects, identity)
        from clear_cache import worker_admission
        worker_admission(projects, identity, hosts, 'changing project pins')
        if value is None:
            current = project(projects, identity)
            if current['revision'] != data['revision']: raise ProjectFault('Project settings changed. Reload Pins before applying.', 409)
            choice = next((v for v in choices(root, current) if v['sdkId'] == data['sdkId']), None)
            if not choice or not choice['available'] or choice['selectionId'] != data['selectionId']:
                raise ProjectFault('The installed SDK selection changed or is unavailable. Reload Pins.', 409)
            from sdk import profile
            context = profile(root, projects, resolve_rust=current['language'] == 'Rust', selected=choice['components'])
            if current['language'] == 'Rust':
                if not context.get('rust'): raise ProjectFault('The SDK-compatible Rust toolchain is unavailable.', 409)
                context['pins']['rust'] = context['rust']['pin']
            from github_import import manifest
            work = folder(project_directory(projects, identity) / 'Workspace')
            manifest(context, work, current['language'], current['template'], current['moduleName'])
            parent = work / '.r4os-studio'
            if not parent.exists(): parent.mkdir(mode=0o700); sync(work)
            folder(parent); target = parent / 'project.json'
            raw = read(target) if target.exists() or target.is_symlink() else None
            from git_metadata import portable
            metadata = json.loads(raw) if raw is not None else portable(current)
            if not isinstance(metadata, dict) or any(metadata.get(k) != v for k, v in portable(current).items()):
                raise ProjectFault('Portable project pins differ from the catalog. Reconcile .r4os-studio/project.json before changing pins.', 409)
            metadata['pins'] = context['pins']
            updated = (json.dumps(metadata, indent=2) + '\n').encode()
            if len(updated) > 65536: raise ProjectFault('Portable project metadata exceeds the pin-change limit.', 409)
            value = {'schema': 1, 'projectId': identity, 'requestId': request_id, 'input': data,
                     'revision': current['revision'], 'oldPins': current['pins'], 'newPins': context['pins'],
                     'oldMetadata': base64.b64encode(raw).decode() if raw is not None else None,
                     'newMetadata': base64.b64encode(updated).decode(),
                     'workspaceIdentity': [work.stat().st_dev, work.stat().st_ino, parent.stat().st_ino],
                     'updatedAt': datetime.now(timezone.utc).isoformat()}
            save(base / 'Requests' / (request_id + '.json'), value)
        gate = gate_path(projects, identity)
        gate.parent.mkdir(mode=0o700, exist_ok=True); folder(gate.parent); sync(gate.parent.parent)
        save(gate, {'projectId': identity, 'requestId': request_id})
        return publish(projects, identity, base, value)


def main():
    os.umask(0o077)
    raw = sys.stdin.buffer.read(8193)
    if len(raw) > 8192: raise ProjectFault('Pin request exceeds its limit.', 400)
    request = json.loads(raw); projects, root = Path(sys.argv[1]).absolute(), Path(sys.argv[2]).absolute()
    identity = project_id(request.get('id'))
    op = request.get('operation')
    if op == 'options' and set(request) == {'operation', 'id'}: result = options(projects, root, identity)
    elif op == 'receipt' and set(request) == {'operation', 'id', 'requestId'}:
        result = receipt(projects, identity, request['requestId'])
    elif op == 'apply' and set(request) == {'operation', 'id', 'input', 'hosts'}:
        result = apply(projects, root, identity, request['input'], request['hosts'])
    else: raise ProjectFault('Unsupported project pin operation.', 400)
    print(json.dumps({'result': result}))


if __name__ == '__main__':
    try: main()
    except ProjectFault as error:
        print(json.dumps({'error': str(error), 'code': error.code})); sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'The SDK set could not be verified. Check installed components and retry the original request if its result is unconfirmed.', 'code': 503})); sys.exit(1)
