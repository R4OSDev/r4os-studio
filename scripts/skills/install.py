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
    user = pwd.getpwnam('root'); os.chown(root, user.pw_uid, user.pw_gid); root.chmod(0o700)
    print('Skills storage prepared. Root services use this data directory. Bootstrap and running workers were preserved.')


if __name__ == '__main__': main()
