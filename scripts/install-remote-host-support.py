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
    user = pwd.getpwnam('root'); os.chown(directory, user.pw_uid, user.pw_gid); directory.chmod(0o700)
    print('Private Remote Host storage prepared. Root services use this data directory.')


if __name__ == '__main__': main()
