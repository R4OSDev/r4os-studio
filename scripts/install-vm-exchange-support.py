#!/usr/bin/env python3
"""Explicit, targeted host maintenance for the larger offline Exchange export."""
import json
import os
from pathlib import Path
import subprocess

if os.geteuid() != 0:
    raise SystemExit('Run this host maintenance script as root.')
unit = Path('/etc/systemd/system/r4os-studio-vm@.service')
if unit.is_symlink() or not unit.is_file() or unit.stat().st_uid != 0:
    raise SystemExit('Install the fixed VM host template first.')
text = unit.read_text()
if 'User=r4os-studio' not in text or ('vm-dispatch.py %i' not in text and 'virtual-machines/runner.js" %i' not in text):
    raise SystemExit('The installed VM template is not supported.')
policy = json.loads((Path(__file__).resolve().parents[1] / 'shared/exchange-host.json').read_text())
dropin = unit.parent / (unit.name + '.d')
if dropin.is_symlink():
    raise SystemExit('Linked VM configuration is not supported.')
dropin.mkdir(mode=0o755, exist_ok=True)
path = dropin / '40-exchange.conf'
value = '[Service]\nTimeoutStopSec=' + str(policy['stopSeconds']) + 's\n'
if path.is_symlink() or path.exists() and (path.stat().st_uid != 0 or path.read_text() != value):
    raise SystemExit('An existing Exchange timeout override differs. Preserve it and review host configuration.')
staging = path.with_suffix('.tmp')
with staging.open('x') as output:
    output.write(value); output.flush(); os.fsync(output.fileno())
staging.chmod(0o644); staging.replace(path)
descriptor = os.open(dropin, os.O_RDONLY | os.O_DIRECTORY)
try: os.fsync(descriptor)
finally: os.close(descriptor)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
print('Exchange stop/export timeout configured. Running VMs and their pinned workers were preserved.')
