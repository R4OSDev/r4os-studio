#!/usr/bin/env python3
"""Explicit host maintenance enabling QEMU's unprivileged outbound user network."""
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
dropin = unit.parent / (unit.name + '.d')
dropin.mkdir(mode=0o755, exist_ok=True)
path = dropin / '30-network.conf'
value = '[Service]\nRestrictAddressFamilies=\nRestrictAddressFamilies=AF_UNIX AF_INET AF_INET6\n'
staging = path.with_suffix('.tmp')
staging.write_text(value); staging.chmod(0o644); staging.replace(path)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
capability = Path('/etc/r4os-studio-vms/network.json')
capability.parent.mkdir(mode=0o755, exist_ok=True)
staging = capability.with_suffix('.tmp')
staging.write_text(json.dumps({'schema': 1, 'mode': 'user', 'device': 'rtl8139'}) + '\n')
staging.chmod(0o644); staging.replace(capability)
print('Outbound user networking is available for the next VM start. Running VMs were not restarted.')
