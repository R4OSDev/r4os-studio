#!/usr/bin/env python3
"""Explicit local metadata storage setup; no broker/network/bootstrap changes."""
import json
import os
from pathlib import Path
import pwd
import subprocess


def main():
    if os.geteuid() != 0: raise SystemExit('Run this explicit local host setup as root.')
    config = json.loads(Path('/etc/r4os-studio-updates/config.json').read_text())
    base = Path(config['dataDirectory'])
    if base.resolve(strict=True) != base: raise SystemExit('The configured Data directory must be real.')
    directory = base / 'RemoteHosts'
    if directory.is_symlink(): raise SystemExit('Refusing linked Remote Host storage.')
    directory.mkdir(mode=0o700, exist_ok=True)
    if not directory.is_dir(): raise SystemExit('Remote Host storage is not a directory.')
    user = pwd.getpwnam('r4os-studio'); os.chown(directory, user.pw_uid, user.pw_gid); directory.chmod(0o700)
    dropin = Path('/etc/systemd/system/r4os-studio.service.d/63-remote-hosts.conf'); dropin.parent.mkdir(exist_ok=True)
    quoted = str(directory).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    dropin.write_text('[Service]\nReadWritePaths="' + quoted + '"\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    print('Private Remote Host storage prepared. The next regular Studio update applies this one write path.')


if __name__ == '__main__': main()
