#!/usr/bin/env python3
"""Add only the free-SSH worker unit; preserve bootstrap and all running work."""
import os
from pathlib import Path
import re
import subprocess


def main():
    if os.geteuid() != 0: raise SystemExit('Run SSH worker host maintenance as root.')
    source = Path('/etc/systemd/system/r4os-studio-development-vm@.service')
    if source.stat().st_uid != 0 or source.stat().st_mode & 0o022: raise SystemExit('Invalid existing VM worker unit.')
    text = source.read_text()
    if 'ExecStart=/usr/bin/python3 -B /opt/r4os-studio/bin/development-launch.py %i' not in text:
        raise SystemExit('Existing development dispatcher differs; preserve and review it.')
    text = re.sub(r'^RuntimeMaxSec=.*\n', '', text, flags=re.M)
    text += 'RuntimeMaxSec=infinity\n'
    text = text.replace('Description=R4OS Studio VM development job %i', 'Description=R4OS Studio project VM SSH job %i')
    destination = source.with_name('r4os-studio-development-ssh@.service')
    if destination.exists() and destination.read_text() != text: raise SystemExit('Existing SSH unit differs; preserve and review it.')
    destination.write_text(text); destination.chmod(0o644)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    print('Project SSH worker support installed. No service or VM started/stopped.')


if __name__ == '__main__': main()
