#!/usr/bin/env python3
"""Explicit host setup for private GitHub connections; preserve the bootstrap."""
import json
import os
import pwd
from pathlib import Path
import subprocess


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run this explicit host setup as root.')
    config = json.loads(Path('/etc/r4os-studio-updates/config.json').read_text())
    directory = Path(config['dataDirectory']) / 'GitHub'
    if directory.is_symlink():
        raise SystemExit('Refusing a symbolic GitHub storage directory.')
    directory.mkdir(mode=0o700, exist_ok=True)
    user = pwd.getpwnam('r4os-studio')
    os.chown(directory, user.pw_uid, user.pw_gid)
    directory.chmod(0o700)
    dropin = Path('/etc/systemd/system/r4os-studio.service.d/61-github.conf')
    dropin.parent.mkdir(exist_ok=True)
    quoted = str(directory).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    dropin.write_text('[Service]\nReadWritePaths="' + quoted + '"\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    print('GitHub storage prepared. The next regular Studio update applies the service write path.')


if __name__ == '__main__':
    main()
