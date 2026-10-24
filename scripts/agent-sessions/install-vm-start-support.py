#!/usr/bin/env python3
"""Explicit v3 compatibility maintenance; preserve bootstrap, data and VMs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess

PREVIOUS_UPDATER_SHA = '99d59cdba45b939a1bc90f7b3680302b6a37421a51d219b6f7c73ee667b3f47a'
BUSY = {'checking', 'downloading', 'building', 'activating', 'recovering'}


def control(*args):
    return subprocess.check_output(['/usr/bin/systemctl', *args], text=True, timeout=45).strip()


def updater_idle():
    path = Path('/var/lib/r4os-studio-updates/status.json')
    if path.exists() and json.loads(path.read_text()).get('phase') in BUSY:
        raise SystemExit('Wait for the current update operation to finish.')
    if control('show', 'r4os-studio-update-build.service', '--property=ActiveState', '--value') not in ('inactive', 'failed'):
        raise SystemExit('Wait for the update build service to finish.')


def install():
    target = Path('/opt/r4os-studio/bin/update-host.py')
    if target.resolve(strict=True) != target or not stat.S_ISREG(target.stat().st_mode) or target.stat().st_uid != 0:
        raise SystemExit('The existing updater is not the expected root-owned regular file.')
    source = Path(__file__).resolve().parents[1] / 'updates/host.py'
    original, replacement = target.read_bytes(), source.read_bytes()
    compile(replacement, str(source), 'exec')
    if original == replacement:
        print('VM start update compatibility is already installed.'); return
    if hashlib.sha256(original).hexdigest() != PREVIOUS_UPDATER_SHA:
        raise SystemExit('The existing updater differs. Preserve and review it before maintenance.')
    updater_idle()
    control('stop', 'r4os-studio-updates.service')
    try:
        updater_idle()
        backup = target.with_name('update-host.pre-tools-v3.py')
        if not backup.exists():
            with backup.open('xb') as stream:
                os.fchmod(stream.fileno(), 0o700); stream.write(original); stream.flush(); os.fsync(stream.fileno())
        temporary = target.with_name('update-host.tools-v3.tmp')
        with temporary.open('xb') as stream:
            os.fchmod(stream.fileno(), 0o755); stream.write(replacement); stream.flush(); os.fsync(stream.fileno())
        temporary.replace(target)
        fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally: control('start', 'r4os-studio-updates.service')
    print('Tool profile v3 compatibility installed; configuration, release selection, data and VMs preserved.')


def adopt():
    release = Path('/opt/r4os-studio/current').resolve(strict=True)
    script = release / 'scripts/agent-sessions/host.py'
    profiles = json.loads((release / 'shared/update-host.json').read_text()).get('agentToolProfiles', [])
    if (not release.is_relative_to('/opt/r4os-studio/releases') or 'studio-tools-v3' not in profiles
            or script.stat().st_uid != 0 or script.stat().st_mode & 0o022):
        raise SystemExit('Install the immutable v3-capable Studio release before adopting it.')
    units = control('list-units', '--all', '--state=active,activating,deactivating,reloading', '--plain', '--no-legend', '--no-pager',
                    'r4os-studio-agent@*.service')
    if units: raise SystemExit('Wait for existing agent worker units to finish; none were stopped.')
    projects = Path(json.loads(Path('/etc/r4os-studio-agents/config.json').read_text())['projects'])
    for database in projects.glob('*/Sessions/Sessions.sqlite'):
        if database.resolve(strict=True) != database: raise SystemExit('Review unexpected session storage before coordinator adoption.')
        db = sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True)
        try:
            if db.execute('SELECT id FROM runs WHERE busy=1 LIMIT 1').fetchone():
                raise SystemExit('Wait for existing agent runs to finish; none were stopped.')
        finally: db.close()
    control('restart', 'r4os-studio-agents.service')
    print('Agent coordinator adopted the installed release. Worker units, VMs, credentials and histories preserved.')


def main():
    if os.geteuid() != 0: raise SystemExit('Run this targeted VM start compatibility maintenance as root.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adopt', action='store_true', help='After release installation, adopt it with an idle agent coordinator.')
    args = parser.parse_args()
    adopt() if args.adopt else install()


if __name__ == '__main__': main()
