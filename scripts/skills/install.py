#!/usr/bin/env python3
"""Add only the private Skills storage path to the existing Studio service."""
import json
import os
from pathlib import Path
import pwd
import subprocess


def main():
    if os.geteuid() != 0: raise SystemExit('Run the explicit skill host installer as root.')
    config = json.loads(Path('/etc/r4os-studio-updates/config.json').read_text())
    root = Path(config['dataDirectory']) / 'Skills'
    if root.is_symlink(): raise SystemExit('Refusing linked Skills storage.')
    root.mkdir(mode=0o700, exist_ok=True)
    user = pwd.getpwnam('r4os-studio'); os.chown(root, user.pw_uid, user.pw_gid); root.chmod(0o700)
    quoted = str(root).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    target = Path('/etc/systemd/system/r4os-studio.service.d/62-skills.conf')
    target.parent.mkdir(exist_ok=True)
    target.write_text('[Service]\nReadWritePaths="' + quoted + '"\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    print('Skills storage prepared. The next regular Studio update applies its write path. Bootstrap and running workers were preserved.')


if __name__ == '__main__': main()
