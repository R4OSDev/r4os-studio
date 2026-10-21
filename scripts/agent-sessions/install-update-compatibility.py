#!/usr/bin/env python3
"""Explicit additive host maintenance, no bootstrap/configuration/VM changes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

OLD_SHA = '7b159246dc86c0164b0498b2edce1c86c47cf60dbad0846eeb57ab6c1b2fd38f'


def main():
    if os.getuid() != 0: raise SystemExit('Run this targeted update compatibility maintenance as root.')
    target = Path('/opt/r4os-studio/bin/update-host.py')
    source = Path(__file__).resolve().parents[1] / 'updates/host.py'
    original = target.read_bytes(); replacement = source.read_bytes()
    if original == replacement:
        print('Agent update compatibility is already installed.'); return
    if hashlib.sha256(original).hexdigest() != OLD_SHA:
        raise SystemExit('The existing host updater differs. Preserve and review it before maintenance.')
    status = Path('/var/lib/r4os-studio-updates/status.json')
    # Check via the fixed local control/status store; never interrupt an update.
    for file in (status, status.with_name('state.json')):
        if file.exists() and json.loads(file.read_text()).get('phase') in ('checking', 'downloading', 'building', 'activating', 'recovering'):
            raise SystemExit('Wait for the current update operation to finish.')
    subprocess.run(['systemctl', 'stop', 'r4os-studio-updates.service'], check=True)
    backup = target.with_name('update-host.pre-agents-v1.py')
    if not backup.exists(): shutil.copyfile(target, backup); backup.chmod(0o700)
    temporary = target.with_name('update-host.agents-v1.tmp')
    with temporary.open('wb') as f: f.write(replacement); f.flush(); os.fsync(f.fileno())
    temporary.chmod(0o755); temporary.replace(target)
    fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY); os.fsync(fd); os.close(fd)
    subprocess.run(['systemctl', 'start', 'r4os-studio-updates.service'], check=True)
    print('Agent protocol 1 compatibility installed; existing configuration, Studio and workers preserved.')


if __name__ == '__main__': main()
