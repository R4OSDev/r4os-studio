#!/usr/bin/env python3
"""Explicit, resumable transition of the existing Studio installation to Root."""
import argparse
import base64
from contextlib import closing
import json
import os
from pathlib import Path
import pwd
import shutil
import sqlite3
import subprocess
import time

from service_runtime import root_service

STATE = Path('/var/lib/r4os-studio-updates/root-runtime.json')
UNIT_DIRECTORY = Path('/etc/systemd/system')
ACCOUNTS = ('r4os-studio', 'r4os-studio-updater')


def run(*args, timeout=60):
    return subprocess.check_output(args, text=True, timeout=timeout).strip()


def save(value):
    temporary = STATE.with_suffix('.tmp')
    with temporary.open('w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, STATE)


def units():
    return [line.split()[0] for line in run('systemctl', 'list-units', '--type=service',
        '--state=active', '--no-legend', '--no-pager', '--plain', 'r4os-studio*').splitlines() if line]


def idle(data):
    # Read-only admission check: never stop a live user run to migrate accounts.
    for root in (data / 'Projects', data / 'Skills'):
        for database in root.glob('*/Sessions/Sessions.sqlite'):
            with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
                if db.execute('SELECT count(*) FROM runs WHERE busy != 0').fetchone()[0]:
                    raise RuntimeError('A Studio run is active. Finish or stop it before migrating services.')


def prepare_updater():
    """Allow the regular updater to build the first Root-compatible release."""
    if os.geteuid() != 0:
        raise RuntimeError('Run explicit updater preparation as Root.')
    source = Path(__file__).resolve().parent
    target = Path('/opt/r4os-studio/bin/update-host.py')
    backup = STATE.with_name('update-host-before-root.py')
    if not backup.exists():
        with backup.open('xb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(target.read_bytes())
    shutil.copyfile(source / 'updates/host.py', target)
    target.chmod(0o755)
    unit = UNIT_DIRECTORY / 'r4os-studio-update-build.service'
    unit.write_text((source / 'updates/systemd/r4os-studio-update-build.service').read_text())
    run('systemctl', 'daemon-reload')
    run('systemctl', 'restart', 'r4os-studio-updates.service')
    print(json.dumps({'updaterPrepared': True, 'backup': str(backup)}))


def ownership(root, old_ids):
    count = 0
    if not root.exists():
        return count
    # Only the retired Studio identities are changed, and symlinks are not followed.
    for directory, names, files in os.walk(root, followlinks=False):
        for path in [Path(directory), *(Path(directory) / name for name in names + files)]:
            info = path.lstat()
            if info.st_uid in old_ids or info.st_gid in old_ids:
                os.chown(path, 0, 0, follow_symlinks=False)
                count += 1
    return count


def migrate():
    if os.geteuid() != 0:
        raise RuntimeError('Run explicit Root service maintenance as Root.')
    update = json.loads(Path('/etc/r4os-studio-updates/config.json').read_text())
    data = Path(update['dataDirectory']).resolve(strict=True)
    release = Path('/opt/r4os-studio/current').resolve(strict=True)
    if json.loads((release / 'shared/update-host.json').read_text()).get('rootServices') != 1:
        raise RuntimeError('Install the Root-compatible Studio release before migrating services.')
    state = json.loads(STATE.read_text()) if STATE.exists() else None
    if state and state.get('phase') == 'complete':
        print(json.dumps({'phase': 'complete', 'changed': False}))
        return
    idle(data)
    if state is None:
        paths = [*UNIT_DIRECTORY.glob('r4os-studio*.service'),
                 *UNIT_DIRECTORY.glob('r4os-studio*.service.d/*.conf'),
                 *Path('/etc').glob('r4os-studio*/config.json'),
                 *Path('/etc/polkit-1/rules.d').glob('*r4os-studio*.rules')]
        for candidate in (Path('/etc/tmpfiles.d/r4os-studio-vms.conf'), Path('/etc/dbus-1/system.d/r4os-studio-skill-mcp.conf')):
            if candidate.exists(): paths.append(candidate)
        old_ids = []
        for name in ACCOUNTS:
            try:
                user = pwd.getpwnam(name)
                old_ids.extend((user.pw_uid, user.pw_gid))
            except KeyError:
                pass
        state = {'schema': 1, 'rootServices': 1, 'phase': 'prepared', 'active': units(),
            'oldIds': sorted(set(old_ids)), 'data': str(data), 'release': str(release),
            'originals': {str(path): base64.b64encode(path.read_bytes()).decode() for path in paths},
            'started': [], 'ownershipChanges': 0}
        save(state)
    if state['phase'] == 'prepared':
        if 'r4os-studio.service' in state['active']:
            run('systemctl', 'stop', 'r4os-studio.service')
            try:
                idle(data)
            except Exception:
                run('systemctl', 'start', 'r4os-studio.service')
                raise
        for unit in state['active']:
            if unit in ('r4os-studio-updates.service', 'r4os-studio.service'): continue
            run('systemctl', 'thaw', unit)
            run('systemctl', 'stop', unit, timeout=1200)
        run('systemctl', 'stop', 'r4os-studio-updates.service')
        state['phase'] = 'stopped'; save(state)
    if state['phase'] == 'stopped':
        for path in [*UNIT_DIRECTORY.glob('r4os-studio*.service'), *UNIT_DIRECTORY.glob('r4os-studio*.service.d/*.conf')]:
            text = path.read_text()
            path.write_text(root_service(text, identity=path.suffix == '.service'))
        for path in Path('/etc').glob('r4os-studio*/config.json'):
            value = json.loads(path.read_text())
            if 'uid' in value:
                value['uid'] = 0
                path.write_text(json.dumps(value, indent=2) + '\n')
        tmpfiles = Path('/etc/tmpfiles.d/r4os-studio-vms.conf')
        if tmpfiles.exists():
            tmpfiles.write_text(tmpfiles.read_text().replace('r4os-studio r4os-studio', 'root root'))
        for path in Path('/etc/polkit-1/rules.d').glob('*r4os-studio*.rules'):
            path.unlink()
        Path('/etc/dbus-1/system.d/r4os-studio-skill-mcp.conf').unlink(missing_ok=True)
        for source, destination in (
            ('updates/host.py', 'update-host.py'), ('agent-sessions/launch.py', 'agent-launch.py'),
            ('project-development/launch.py', 'development-launch.py'), ('project-git/launch.py', 'git-launch.py'),
            ('components/launch.py', 'components-launch.py'), ('remote-hosts/dispatch.py', 'remote-host.py'),
            ('skills/mcp_launch.py', 'skill-mcp-launch.py'),
            ('skills/source_launch.py', 'skill-source-launch.py')):
            target = Path('/opt/r4os-studio/bin') / destination
            shutil.copyfile(release / 'scripts' / source, target)
            target.chmod(0o755)
        for directory in (data, Path('/var/cache/r4os-studio-updates')):
            state['ownershipChanges'] += ownership(directory, state['oldIds'])
        for directory in Path('/run').glob('r4os-studio*'):
            if directory.is_dir(): state['ownershipChanges'] += ownership(directory, state['oldIds'])
        run('systemctl', 'daemon-reload')
        run('systemd-tmpfiles', '--create', '/etc/tmpfiles.d/r4os-studio-vms.conf')
        run('busctl', 'call', 'org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'ReloadConfig')
        state['phase'] = 'configured'; save(state)
    if state['phase'] == 'configured':
        for unit in state['active']:
            if unit in state['started']: continue
            run('systemctl', 'start', unit, timeout=1200)
            state['started'].append(unit); save(state)
        state['phase'] = 'started'; save(state)
    if state['phase'] == 'started':
        for unit in state['active']:
            pid = int(run('systemctl', 'show', unit, '--property=MainPID', '--value'))
            if not pid or Path('/proc', str(pid)).stat().st_uid != 0:
                raise RuntimeError('The migrated service did not confirm Root operation: ' + unit)
        for name in ACCOUNTS:
            try: user = pwd.getpwnam(name)
            except KeyError: user = None
            if user is not None:
                for process in Path('/proc').iterdir():
                    if process.name.isdigit():
                        try: owner = process.stat().st_uid
                        except FileNotFoundError: continue
                        if owner == user.pw_uid:
                            raise RuntimeError('A retired account still owns a process: ' + name)
                run('/usr/sbin/userdel', name)
            # userdel may have already removed its matching private group.
            import grp
            try: grp.getgrnam(name)
            except KeyError: continue
            run('/usr/sbin/groupdel', name)
        state['phase'] = 'complete'; save(state)
    print(json.dumps({key: state[key] for key in ('phase', 'ownershipChanges', 'started')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--prepare-updater', action='store_true')
    args = parser.parse_args()
    if args.prepare_updater:
        prepare_updater()
    elif args.apply:
        migrate()
    else:
        print(json.dumps({'activeServices': units(), 'migration': str(STATE), 'apply': False}))
