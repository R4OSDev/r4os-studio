#!/usr/bin/env python3
"""Explicit additive skill-session host support; never reinitialize bootstrap."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess

UPDATER_SHA = '235fcbf230158abf8747b0b55a529dc663dfdc04dffec6b2c75b6ebe469e6c43'
LAUNCHER_SHA = '674b7f5d61d77f3e7010bf68f22f741dba657a93ed6928ffbdfc499d8b8f29a1'
BUSY = {'checking', 'downloading', 'building', 'activating', 'recovering'}


def control(*args): return subprocess.check_output(['/usr/bin/systemctl', *args], text=True, timeout=45).strip()


def checked(path, source, expected, label):
    if path.resolve(strict=True) != path or not stat.S_ISREG(path.stat().st_mode) or path.stat().st_uid != 0:
        raise SystemExit('Review the existing root-owned ' + label + ' before maintenance.')
    original, replacement = path.read_bytes(), source.read_bytes()
    compile(replacement, str(source), 'exec')
    if original != replacement and hashlib.sha256(original).hexdigest() != expected:
        raise SystemExit('The existing ' + label + ' differs. Preserve and review it before maintenance.')
    return original, replacement


def replace(path, data, original, stamp='skill-sessions'):
    if data == original: return
    backup = path.with_name(path.name + '.pre-' + stamp)
    if not backup.exists():
        with backup.open('xb') as stream:
            os.fchmod(stream.fileno(), 0o700); stream.write(original); stream.flush(); os.fsync(stream.fileno())
    temporary = path.with_name(path.name + '.' + stamp + '.tmp')
    with temporary.open('xb') as stream:
        os.fchmod(stream.fileno(), 0o755); stream.write(data); stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def idle_updater():
    for file in ('status.json', 'state.json'):
        path = Path('/var/lib/r4os-studio-updates') / file
        if path.exists() and json.loads(path.read_text()).get('phase') in BUSY:
            raise SystemExit('Wait for the current update operation to finish.')
    if control('show', 'r4os-studio-update-build.service', '--property=ActiveState', '--value') not in ('inactive', 'failed'):
        raise SystemExit('Wait for the update build service to finish.')


def install():
    scripts = Path(__file__).resolve().parents[1]
    updater = Path('/opt/r4os-studio/bin/update-host.py'); launcher = updater.with_name('agent-launch.py')
    old_updater, new_updater = checked(updater, scripts / 'updates/host.py', UPDATER_SHA, 'updater')
    old_launcher, new_launcher = checked(launcher, scripts / 'agent-sessions/launch.py', LAUNCHER_SHA, 'agent dispatcher')
    config = json.loads(Path('/etc/r4os-studio-agents/config.json').read_text())
    projects = Path(config['projects']); skills = projects.parent / 'Skills'
    if skills.resolve(strict=True) != skills or not skills.is_dir() or skills.stat().st_uid != config['uid']:
        raise SystemExit('Prepare the existing private Skills storage first.')
    quoted = str(skills).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    wanted = '[Service]\nReadWritePaths="' + quoted + '"\n'
    dropins = [Path('/etc/systemd/system') / (unit + '.d') / '64-skills.conf'
               for unit in ('r4os-studio-agents.service', 'r4os-studio-agent@.service')]
    for path in dropins:
        if path.is_symlink() or (path.exists() and path.read_text() != wanted):
            raise SystemExit('Review existing skill session service support before maintenance.')
    idle_updater()
    control('stop', 'r4os-studio-updates.service')
    try:
        idle_updater()
        replace(updater, new_updater, old_updater); replace(launcher, new_launcher, old_launcher)
        for path in dropins:
            path.parent.mkdir(exist_ok=True)
            path.write_text(wanted)
        control('daemon-reload')
    finally: control('start', 'r4os-studio-updates.service')
    print('Skill session compatibility installed. Existing configuration, live workers and VMs were preserved.')


def adopt():
    release = Path('/opt/r4os-studio/current').resolve(strict=True)
    script = release / 'scripts/agent-sessions/host.py'
    profiles = json.loads((release / 'shared/update-host.json').read_text()).get('agentToolProfiles', [])
    if (not release.is_relative_to('/opt/r4os-studio/releases') or 'studio-skill-tools-v1' not in profiles
            or script.stat().st_uid != 0 or script.stat().st_mode & 0o022):
        raise SystemExit('Install the immutable skill-capable release before adopting it.')
    if control('list-units', '--all', '--state=active,activating,deactivating,reloading', '--plain', '--no-legend', '--no-pager', 'r4os-studio-agent@*.service'):
        raise SystemExit('Wait for active agent workers to finish. None were stopped.')
    config = json.loads(Path('/etc/r4os-studio-agents/config.json').read_text()); projects = Path(config['projects'])
    for root in (projects, projects.parent / 'Skills'):
        for path in root.glob('*/Sessions/Sessions.sqlite'):
            if path.resolve(strict=True) != path: raise SystemExit('Review unexpected session storage before adoption.')
            db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
            try:
                if db.execute('SELECT 1 FROM runs WHERE busy=1 LIMIT 1').fetchone():
                    raise SystemExit('Wait for admitted runs to finish. None were stopped.')
            finally: db.close()
    control('restart', 'r4os-studio-agents.service')
    print('Idle agent coordinator adopted skill support; histories, credentials and all worker/VM units preserved.')


if __name__ == '__main__':
    if os.geteuid() != 0: raise SystemExit('Run explicit skill-session host maintenance as root.')
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--adopt', action='store_true')
    args = parser.parse_args(); adopt() if args.adopt else install()
