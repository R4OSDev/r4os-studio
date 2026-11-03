#!/usr/bin/env python3
"""Delete inventoried obsolete Studio SDK sources after confirmed migration."""
import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

from layout import folder, save, sync
from project_use import acquire, project_id
from project_maintenance import require_idle
from store import ProjectFault
import sdk_migration_guard as guard

sys.path[:0] = [str(Path(__file__).parents[1] / 'components')]
import sdk_provision


def describe(path):
    path = Path(path).absolute()
    if path.resolve(strict=True) != path or path.is_symlink():
        raise ProjectFault('An SDK retirement path is indirect.', 409)
    info = path.stat(); count = size = 0
    if path.is_dir():
        for base, directories, files in os.walk(path, followlinks=False):
            for name in directories + files:
                target = Path(base) / name; item = target.lstat()
                if stat.S_ISREG(item.st_mode): count += 1; size += item.st_size
                elif not (stat.S_ISDIR(item.st_mode) or stat.S_ISLNK(item.st_mode)):
                    raise ProjectFault('An SDK retirement candidate contains a special file.', 409)
    elif path.is_file(): count = 1; size = info.st_size
    else: raise ProjectFault('Invalid SDK retirement candidate.', 409)
    return {'path': str(path), 'identity': [info.st_dev, info.st_ino, info.st_uid, info.st_gid],
            'files': count, 'bytes': size, 'directory': path.is_dir()}


def no_live_access(candidates):
    prefixes = tuple(value['path'] for value in candidates)
    own = os.getpid()
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit() or int(directory.name) == own:
            continue
        references = []
        try:
            for name in ('cwd', 'exe'):
                try: references.append(os.readlink(directory / name).removesuffix(' (deleted)'))
                except FileNotFoundError: pass
            for fd in (directory / 'fd').iterdir():
                try: references.append(os.readlink(fd).removesuffix(' (deleted)'))
                except FileNotFoundError: pass
            try:
                for line in (directory / 'maps').read_text().splitlines():
                    parts = line.split(None, 5)
                    if len(parts) == 6: references.append(parts[5].removesuffix(' (deleted)'))
            except FileNotFoundError: pass
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            raise ProjectFault('Live SDK file access could not be audited. Run retirement as the host administrator.', 403) from None
        if any(value == prefix or value.startswith(prefix + '/') for value in references for prefix in prefixes):
            raise ProjectFault('A live process still uses an obsolete SDK path: PID ' + directory.name, 409)


def owned_gate(path, request_id):
    value = {'schema': 1, 'operation': 'sdk-profile-migration', 'requestId': request_id}
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True); folder(path.parent)
    if path.exists() or path.is_symlink():
        if path.resolve(strict=True) != path or json.loads(path.read_text()) != value:
            raise ProjectFault('Another original SDK maintenance request owns admission.', 409)
    else:
        save(path, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'projects', 'workspace-root', 'migration-id', 'request-id', 'plan'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(); os.umask(0o077)
    root, projects, workspace = (Path(value).resolve(strict=True) for value in (args.root, args.projects, args.workspace_root))
    request_id, migration_id = project_id(args.request_id), project_id(args.migration_id)
    migration = json.loads((projects / '.studio/sdk-migrations' / (migration_id + '.json')).read_text())
    if migration.get('phase') != 'complete':
        raise ProjectFault('Confirm the original whole-project SDK migration before retirement.', 409)
    active = migration['input']['sdk']; defaults = json.loads((root / 'Profiles/versions.json').read_text())
    if defaults['defaults']['sdk']['revision'] != active:
        raise ProjectFault('The SDK standard changed after migration.', 409)
    context = sdk_provision.verify(root, active, sources=True)
    plan_file = Path(args.plan).resolve(strict=True)
    plan = json.loads(plan_file.read_text())
    if plan.get('schema') != 1 or plan.get('sdk') != active or plan.get('requestId') != request_id:
        raise ProjectFault('The SDK retirement plan belongs to different inputs.', 409)
    candidates = plan['candidates']
    allowed = (root / 'SDK', root / 'Toolchains/Rust', root / 'Toolchains/R4UPack', root / 'Profiles', projects, workspace / 'Temp')
    for item in candidates:
        path = Path(item['path'])
        if not path.is_absolute() or not any(path.is_relative_to(base) and path != base for base in allowed):
            raise ProjectFault('An SDK retirement path is outside its managed roots.', 409)
        if path.is_relative_to(context['base']) or path == context['paths']['sdk']:
            raise ProjectFault('The active SDK package cannot be retired.', 409)
        if path.is_relative_to(projects):
            parts = path.relative_to(projects).parts
            compiler_cache = len(parts) >= 3 and parts[1] == 'Development' and parts[2] in ('Work','Cache')
            session_tools = (len(parts) >= 6 and parts[1] == 'Sessions' and parts[3] == 'Tools'
                             and parts[5] in ('tools','zig') and re.fullmatch('[a-f0-9-]{36}', parts[2])
                             and re.fullmatch('[a-f0-9-]{36}', parts[4]))
            if parts[0] != '.studio' and not compiler_cache and not session_tools:
                raise ProjectFault('User workspace, original evidence and artifact paths cannot be retired.', 409)
        if not isinstance(item.get('reason'), str) or not item['reason']:
            raise ProjectFault('Every SDK deletion needs its original ownership reason.', 409)
    journal = root / 'Profiles/SDK-Retirements' / (request_id + '.json')
    journal.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    state = json.loads(journal.read_text()) if journal.exists() else {'schema': 1, 'requestId': request_id,
        'migrationId': migration_id, 'sdk': active, 'planSha256': hashlib.sha256(plan_file.read_bytes()).hexdigest(),
        'phase': 'prepared', 'deleted': []}
    if state['planSha256'] != hashlib.sha256(plan_file.read_bytes()).hexdigest():
        raise ProjectFault('The original SDK retirement plan changed.', 409)
    if not args.apply:
        for item in candidates:
            current = describe(item['path'])
            if any(current[key] != item[key] for key in ('identity','files','bytes','directory')):
                raise ProjectFault('An SDK retirement candidate changed since inventory.', 409)
        no_live_access(candidates)
        print(json.dumps({'requestId': request_id, 'candidates': len(candidates), 'files': sum(p['files'] for p in candidates),
                          'bytes': sum(p['bytes'] for p in candidates), 'ready': True}), flush=True)
        return
    if json.loads((Path('/opt/r4os-studio/current') / 'shared/update-host.json').read_text()).get('sdkProfilesOnly') != 1:
        raise ProjectFault('Install the SDK-only Studio release before removing old sources.', 409)
    host_source = Path('/opt/r4os-studio/bin/update-host.py').read_text()
    if 'def sdk_compatible_release(' not in host_source:
        raise ProjectFault('Install the narrow updater retirement guard first.', 409)
    with ExitStack() as stack:
        mutex = stack.enter_context((journal.parent / 'retirement.lock').open('a'))
        fcntl.flock(mutex, fcntl.LOCK_EX | fcntl.LOCK_NB)
        owned_gate(guard.path(projects), request_id)
        owned_gate(root / 'Profiles/sdk-host-maintenance.json', request_id)
        stack.enter_context(guard.own(projects, request_id))
        for project in migration['after']:
            stack.enter_context(acquire(projects, project['id'], exclusive=True, pins_recovery=True))
            require_idle(projects, project['id'])
            from project_maintenance import project as current_project
            if current_project(projects, project['id'])['pins'] != project['pins']:
                raise ProjectFault('A project SDK changed before retirement.', 409)
        from migrate_sdk_support import require_idle_hosts
        require_idle_hosts(projects, root, migration['after'])
        pending = [item for item in candidates if item['path'] not in {row['path'] for row in state['deleted']}]
        no_live_access([item for item in pending if Path(item['path']).exists()])
        marker = root / 'Profiles/sdk-retirement.json'
        save(marker, {'schema': 1, 'sdkProfilesOnly': 1, 'requestId': request_id, 'sdk': active,
                      'manifestSha256': context['record']['manifestSha256'], 'profileSources': context['record']['profileSources']})
        save(journal, state)
        for item in pending:
            path = Path(item['path'])
            if path.exists() or path.is_symlink():
                current = describe(path)
                if current['identity'] != item['identity']:
                    raise ProjectFault('An SDK deletion target changed identity.', 409)
                if item['directory']: shutil.rmtree(path)
                else: path.unlink()
                sync(path.parent)
            state['deleted'].append(item); save(journal, state)
        sdk_provision.verify(root, active, sources=True)
        state['phase'] = 'complete'; save(journal, state)
        for path in (guard.path(projects), root / 'Profiles/sdk-host-maintenance.json'):
            if path.exists() and json.loads(path.read_text()).get('requestId') == request_id:
                path.unlink(); sync(path.parent)
        print(json.dumps({'requestId': request_id, 'phase': 'complete', 'deleted': len(state['deleted']),
                          'bytes': sum(item['bytes'] for item in state['deleted'])}), flush=True)


if __name__ == '__main__': main()
