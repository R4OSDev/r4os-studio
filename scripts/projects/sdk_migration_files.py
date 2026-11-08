"""Stage SDK-generated file changes; publication remains in the pin journal."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from types import SimpleNamespace

from layout import folder, save
from store import ProjectFault

sys.path.append(str(Path(__file__).resolve().parents[1] / 'project-development'))
from snapshot import capture, inventory
from sdk_inputs import read as sdk_inputs


def freeze(workspace, parent, request_id, pins):
    """Reuse the no-follow bounded build capture, without admitting a user job."""
    capture_store = SimpleNamespace(workspace=workspace, root=parent)
    request = {'id': request_id, 'pins': pins, 'sdkInputs': sdk_inputs(workspace)}
    return capture(capture_store, request)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def stage(context, workspace, parent, request_id, old_pins):
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent = folder(parent)
    selected = {name: context['pins'][name] for name in ('sdk', 'contract', 'libraries', 'zig', 'sdkTools')}
    selected['profileSources'] = context['pins']['sdkProfile']['hashes']
    before = json.loads(json.dumps(inventory(workspace)))
    header = {'schema': 1, 'requestId': request_id, 'selected': selected, 'oldPins': old_pins, 'inventory': before}
    intent = parent / 'staging.json'
    if intent.exists():
        if json.loads(intent.read_text()) != header:
            raise ProjectFault('The original SDK staging input changed. Its source snapshot was preserved.', 409)
    else:
        save(intent, header)
    completed = parent / 'prepared.json'
    if completed.exists():
        value = json.loads(completed.read_text())
        if value['requestId'] != request_id or value['selected'] != selected:
            raise ProjectFault('The original SDK preparation identity changed.', 409)
        return {**value, 'workspace': parent / 'Workspace'}
    source = parent / 'Inputs' / request_id
    marker = source.with_name(request_id + '.json')
    partial = source.with_name(request_id + '.new')
    if marker.exists():
        receipt = json.loads(marker.read_text())
        candidate = source if source.exists() else partial
        for item in receipt['files']:
            path = candidate / item['path']
            if path.resolve(strict=True) != path.absolute() or sha(path) != item['sha256']:
                raise ProjectFault('The original SDK source snapshot changed.', 409)
        if not source.exists():
            partial.rename(source)
    else:
        # No published capture exists. Only this request's incomplete private
        # copy is disposable, and the original inventory above must still match.
        if partial.exists():
            folder(partial)
            shutil.rmtree(partial)
        receipt, source = freeze(workspace, parent, request_id, old_pins)
    target = parent / 'Workspace'
    if target.exists():
        folder(target)
        shutil.rmtree(target)
    shutil.copytree(source, target)
    executable = {item['path'] for item in receipt['files'] if item.get('executable')}
    for path in target.rglob('*'):
        if path.is_file():
            path.chmod(0o700 if str(path.relative_to(target)) in executable else 0o600)
    from sdk_execution import run
    native = []
    zon = target / 'build.zig.zon'
    if zon.exists():
        text = zon.read_text()
        matches = list(re.finditer(r'(?s)\.r4os_sdk\s*=\s*\.\{([^{}]*)\}', text))
        if len(matches) > 1:
            raise ProjectFault('The project has ambiguous SDK package dependencies.', 409)
        if matches:
            match = matches[0]
            urls = re.findall(r'\.url\s*=\s*"([^"\n]+)"', match[1])
            hashes = re.findall(r'\.hash\s*=\s*"([^"\n]+)"', match[1])
            if len(urls) != 1 or len(hashes) != 1:
                raise ProjectFault('A custom SDK dependency needs explicit source migration.', 409)
            old, new = old_pins['sdk'], context['pins']['sdk']
            if (urls[0], hashes[0]) not in ((old['url'], old['zigPackageHash']), (new['url'], new['zigPackageHash'])):
                raise ProjectFault('The Zig SDK dependency differs from the original project pins.', 409)
            body = match[0].replace('"' + urls[0] + '"', '"' + new['url'] + '"').replace('"' + hashes[0] + '"', '"' + new['zigPackageHash'] + '"')
            zon.write_text(text[:match.start()] + body + text[match.end():])
        native.append(run(context, target, parent / 'Native', ['/powershell/pwsh', '-NoLogo', '-NoProfile', '-File',
            '/sdk/Tools/Sync-ComponentPins.ps1', '-ProjectRoot', '/workspace', '-SdkRoot', '/sdk', '-IncludeLibraries', '-Write'], 'sync-zig'))
    if (target / 'Cargo.toml').exists():
        if not context.get('rust'):
            raise ProjectFault('The SDK Rust tools are required to synchronize this Cargo project.', 409)
        cargo = '/install/' + str(context['rust']['compiler'].relative_to('Install').with_name('cargo'))
        native.append(run(context, target, parent / 'Native', [cargo, 'generate-lockfile', '--offline', '--manifest-path', '/workspace/Cargo.toml',
            '--config', 'patch.crates-io.r4os-sdk.path="/sdk/Rust"',
            '--config', 'patch.crates-io.r4os-contract.path="/contract/Generated/SDK/Rust"'], 'sync-cargo'))
    changes = []
    for name in ('build.zig.zon', 'Cargo.lock'):
        old, new = source / name, target / name
        before = old.read_bytes() if old.exists() else None
        after = new.read_bytes() if new.exists() else None
        if before != after:
            if after is None or len(after) > 2 * 1024**2:
                raise ProjectFault('Invalid SDK-generated file change.', 409)
            changes.append({'path': name, 'before': base64.b64encode(before).decode() if before is not None else None,
                            'after': base64.b64encode(after).decode()})
    value = {'schema': 1, 'requestId': request_id, 'selected': selected, 'source': receipt, 'changes': changes, 'native': native}
    save(completed, value)
    return {**value, 'workspace': target}


def verify_live(workspace, source, changes):
    allowed = {'build.zig.zon', 'Cargo.lock'}
    if any(item.get('path') not in allowed for item in changes):
        raise ProjectFault('Invalid SDK-generated source change.', 503)
    ignored = {item['path'] for item in changes} | {'.r4os-studio/project.json'}
    current, directories = inventory(workspace)
    original = {item['path']: item for item in source['files']}
    if set(current) - ignored != set(original) - ignored:
        raise ProjectFault('Project sources changed after SDK preparation. The original migration was preserved.', 409)
    if set(directories) - {'.r4os-studio'} != set(source['directories']) - {'.r4os-studio'}:
        raise ProjectFault('Project directories changed after SDK preparation.', 409)
    for name in set(original) - ignored:
        item = original[name]
        if sha(workspace / name) != item['sha256'] or bool((workspace / name).stat().st_mode & 0o111) != item.get('executable', False):
            raise ProjectFault('Project source bytes or modes changed after SDK preparation.', 409)


def publish_files(workspace, base, changes):
    from project_pins import read
    from layout import sync
    for item in changes:
        if item.get('path') not in ('build.zig.zon', 'Cargo.lock'):
            raise ProjectFault('Invalid SDK-generated source change.', 503)
        target = workspace / item['path']
        old = base64.b64decode(item['before']) if item['before'] is not None else None
        new = base64.b64decode(item['after'])
        actual = read(target, 2 * 1024**2) if target.exists() or target.is_symlink() else None
        if actual not in (old, new):
            raise ProjectFault('An SDK-generated file changed during publication. Recover the original request.', 409)
        if actual == new:
            continue
        info = target.stat() if target.exists() else workspace.stat()
        temporary = base / (item['path'] + '.new')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), info.st_mode & 0o777 if target.exists() else 0o600)
            os.fchown(stream.fileno(), info.st_uid, info.st_gid)
            stream.write(new); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, target); sync(workspace); sync(base)
