"""Register a checked Git import through the existing recoverable project journal."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from store import connect, public, ProjectFault, check_vm
from project_use import acquire, project_id
from create import publish, finish, sync_tree
from templates import hashes
from sdk import profile, TYPES
from remote_binding import hold, set_binding

# Load source inspection by an explicit private module name: the SDK has its
# own unrelated components/common.py, which must keep its normal import name.
spec = importlib.util.spec_from_file_location('studio_git_files', Path(__file__).parents[1] / 'project-git/common.py')
files = importlib.util.module_from_spec(spec); spec.loader.exec_module(files)


def checked_profile(root, projects, metadata, fallback):
    if metadata:
        language, template, pinned = metadata.get('language'), metadata.get('template'), metadata.get('pins')
        if not isinstance(pinned, dict) or set(pinned) - {'sdk', 'contract', 'zig', 'rust', 'sdkTools'}:
            raise ProjectFault('Portable component pins are invalid.', 409)
        if language == 'Rust' and not pinned.get('rust'): raise ProjectFault('Portable Rust projects require their original Rust pins.', 409)
    else:
        if not isinstance(fallback, dict) or set(fallback) != {'language', 'template', 'optionsRevision'}:
            raise ProjectFault('This repository has no portable pins. Explicitly select its local SDK profile, language and module type.', 409)
        language, template, pinned = fallback['language'], fallback['template'], None
    if language not in ('Zig', 'C', 'Rust') or template not in [v[0] for v in TYPES]:
        raise ProjectFault('Unsupported imported project language or module type.', 409)
    # Import never downloads missing SDK tools. The user installs components in
    # Updates before retrying; an absent pin is never replaced by a default.
    selected = pinned or json.loads((root / 'Profiles/versions.json').read_text())['defaults']
    primary = {k: v for k, v in selected.items() if k in ('sdk', 'contract', 'zig')}
    if not pinned:
        primary = {}
        try:
            paths = {'sdk': root / 'SDK' / selected['sdk']['revision'], 'contract': root / 'Contract' / selected['contract']['revision'], 'zig': root / 'Toolchains/Zig' / selected['zig']['version']}
            for kind, path in paths.items():
                record = files.document(path / '.studio-component.json')
                primary[kind] = {k: record[k] for k in ('version', 'revision', 'sha256', 'url') if k in record}
                primary[kind]['url'] = record.get('url') or record['archiveUrl']
                if kind == 'zig': primary[kind]['binarySha256'] = record.get('binarySha256') or hashlib.sha256((path / 'zig').read_bytes()).hexdigest()
                else: primary[kind]['zigPackageHash'] = record.get('zigPackageHash') or record.get('packageHash')
        except (KeyError, OSError): raise ProjectFault('The selected local SDK profile is unavailable.', 409) from None
    cache = projects / '.studio/tools' / hashlib.sha256(json.dumps(primary, sort_keys=True).encode()).hexdigest()
    if (not pinned or pinned.get('sdkTools')) and not all((cache / v).exists() for v in ('sdk-tools', 'SDK-Release.json', 'sdk-capabilities.json')):
        raise ProjectFault('The exact SDK tools are not installed locally. Prepare this SDK in Updates before importing.', 409)
    try: context = profile(root, projects, pinned, resolve_rust=language == 'Rust')
    except (OSError, ValueError, KeyError): raise ProjectFault('The imported SDK, Contract or compiler pins are unavailable or changed. Install the exact components before retrying.', 409) from None
    if metadata and context['pins'] != pinned: raise ProjectFault('The imported component pins changed.', 409)
    if not metadata:
        if context['revision'] != fallback['optionsRevision']: raise ProjectFault('Local project options changed. Select the profile again.', 409)
        if language == 'Rust':
            if not context.get('rust'): raise ProjectFault('The selected Rust profile is unavailable.', 409)
            context['pins']['rust'] = context['rust']['pin']
    return context, language, template


def manifest(context, source, language, template, expected_name):
    tool = context['rust']['catalog'] if language == 'Rust' else context['tool']
    command = ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-all',
               '--ro-bind', '/usr', '/usr', '--dev', '/dev', '--dir', '/proc', '--tmpfs', '/tmp',
               '--ro-bind', str(source), '/workspace', '--ro-bind', str(tool), '/catalog']
    for path in ('/lib', '/lib64'):
        if Path(path).exists(): command += ['--ro-bind', path, path]
    command += ['--chdir', '/tmp', '--clearenv', '--setenv', 'HOME', '/tmp', '--setenv', 'LANG', 'C.UTF-8', '--', '/catalog']
    def run(*args):
        result = subprocess.run(command + list(args), capture_output=True, timeout=30)
        if result.returncode or len(result.stdout) > 2 * 1024**2:
            raise ProjectFault('The pinned SDK rejected this repository manifest or its source paths.', 409)
        return result.stdout
    run('validate', '--manifest', '/workspace/module.R4MF')
    declared = json.loads(run('catalog', '--root', '/workspace'))
    if len(declared.get('entries', [])) != 1: raise ProjectFault('Import supports exactly one R4OS app manifest at the repository root.', 409)
    entry = declared['entries'][0]; module = entry.get('name')
    if not isinstance(module, str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', module): raise ProjectFault('Unsupported imported module identity.', 409)
    expected_kind = {'library': 'R4L', 'driver': 'R4D', 'protocol': 'R4P'}.get(template, 'R4X')
    if entry.get('language') != language or entry.get('kind') != expected_kind or (expected_name is not None and module != expected_name):
        raise ProjectFault('The manifest differs from the selected project metadata.', 409)
    if expected_kind == 'R4X':
        plan = json.loads(run('plan', '--manifest', '/workspace/module.R4MF')).get('plan', {})
        if plan.get('app_class') != {'terminal': 'console', 'desktop': 'gui', 'service': 'service', 'subsystem': 'gui'}[template] or (template == 'subsystem') != (plan.get('module_role') == 'subsystem'):
            raise ProjectFault('The manifest application class differs from the selected module type.', 409)
        run('contract-plan', '--manifest', '/workspace/module.R4MF')
    return module


def register(db, projects, root, identity, data):
    if set(data) - {'name', 'description', 'snapshot', 'fallback', 'remoteHostId', 'vmId'} or not all(isinstance(data.get(k), str) for k in ('name', 'description', 'snapshot')):
        raise ProjectFault('Invalid import completion.', 400)
    name = data['name'].strip()
    if not name or len(name) > 120 or len(data['description']) > 4000: raise ProjectFault('Enter a project name and a bounded description.', 400)
    fingerprint = files.digest(data)
    retired = db.execute('SELECT 1 FROM retired_project_requests WHERE request_key=?', (identity,)).fetchone()
    if retired: raise ProjectFault('This imported project was deleted. Start a new import.', 410)
    previous = db.execute('SELECT * FROM requests WHERE request_key=?', (identity,)).fetchone()
    if previous:
        if previous['request_hash'] != fingerprint: raise ProjectFault('This import ID belongs to a different completion.', 409)
        return finish(db, projects, root, previous)
    check_vm(root, data.get('vmId'))
    job = files.document(projects / '.studio/github/Jobs' / identity / 'job.json')
    if job['kind'] != 'import' or job['projectId'] != identity or job['state'] != 'completed': raise ProjectFault('Wait for the original import to finish.', 409)
    original = projects / '.studio/github/Imports' / identity
    stage = projects / '.studio/staging' / identity
    source_stage = stage if stage.exists() else original
    files.folder(source_stage)
    receipt = files.document(source_stage / 'import.json')
    if receipt['projectId'] != identity or receipt['requestId'] != identity or receipt['snapshot'] != data['snapshot'] or files.digest(files.inventory(source_stage / 'Workspace')) != data['snapshot']:
        raise ProjectFault('The imported source changed. Original staging was preserved.', 409)
    metadata = receipt['metadata']
    context, language, template = checked_profile(root, projects, metadata, data.get('fallback'))
    module = manifest(context, source_stage / 'Workspace', language, template, metadata.get('moduleName') if metadata else None)
    if files.digest(files.inventory(source_stage / 'Workspace')) != data['snapshot']: raise ProjectFault('The imported source changed during validation.', 409)
    if (projects / identity).exists(): raise ProjectFault('The project destination already exists. Existing files were preserved.', 409)
    sync_tree(source_stage)
    if source_stage != stage: publish(source_stage, stage)
    now = files.now()
    with hold(projects, data.get('remoteHostId')), db:
        db.execute("INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?,?,1,'pending')", (identity, name, data['description'], language, template, 'IMPORT_' + identity.replace('-', ''), data.get('vmId'), json.dumps(context['pins']), now, now))
        set_binding(db, identity, data.get('remoteHostId'))
        db.execute('INSERT INTO project_imports VALUES (?,?,?)', (identity, module, fingerprint))
        db.execute("INSERT INTO requests VALUES (?,?,?,'prepared',?,NULL)", (identity, fingerprint, identity, json.dumps({'layout': 2, 'input': data, 'files': hashes(stage)})))
    return finish(db, projects, root, db.execute('SELECT * FROM requests WHERE request_key=?', (identity,)).fetchone())


def main():
    os.umask(0o077)
    raw = sys.stdin.buffer.read(131073)
    if len(raw) > 131072: raise ProjectFault('Import completion is too large.', 400)
    request = json.loads(raw)
    if set(request) != {'operation', 'id', 'input'} or request['operation'] != 'finish': raise ProjectFault('Unsupported import operation.', 400)
    projects, root, identity = Path(sys.argv[1]).absolute(), Path(sys.argv[2]).resolve(), project_id(request['id'])
    staging = projects / '.studio/staging'; staging.mkdir(mode=0o700, parents=True, exist_ok=True); files.folder(staging)
    with (projects / '.studio/create.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with acquire(projects, identity, exclusive=True), connect(projects) as db:
            result = register(db, projects, root, identity, request['input'])
    print(json.dumps({'result': result}))


if __name__ == '__main__':
    try: main()
    except ProjectFault as error:
        print(json.dumps({'error': str(error), 'code': error.code})); sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'Import could not be confirmed. Retry the original completion; staged files were preserved.', 'code': 503})); sys.exit(1)
