#!/usr/bin/env python3
"""Explicit, additive host maintenance for the persistent project catalog."""
import json
import os
from pathlib import Path
import pwd
import sqlite3
import subprocess


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run the project host installer as root.')
    config = json.loads(Path('/etc/r4os-studio-updates/config.json').read_text())
    root = Path(config['dataDirectory']) / 'Projects'
    if not root.is_absolute() or root.is_symlink():
        raise SystemExit('Invalid persistent project directory.')
    user = pwd.getpwnam('r4os-studio')
    root.mkdir(mode=0o700, parents=False, exist_ok=True)
    os.chown(root, user.pw_uid, user.pw_gid)
    root.chmod(0o700)
    escaped = str(root).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    dropin = Path('/etc/systemd/system/r4os-studio.service.d/40-projects.conf')
    dropin.parent.mkdir(exist_ok=True)
    dropin.write_text('[Service]\nReadWritePaths="' + escaped + '"\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    print(f'Projects support ready (SQLite {sqlite3.sqlite_version}). Applies on the next Studio start. No VMs were stopped.')


if __name__ == '__main__':
    main()
