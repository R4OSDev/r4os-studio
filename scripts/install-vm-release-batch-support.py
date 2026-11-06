#!/usr/bin/env python3
"""Explicit local setup for the private VM release-batch journal."""
import json
import os
from pathlib import Path
import pwd
import subprocess
import tempfile

CONFIG = Path('/etc/r4os-studio-updates/config.json')
DROPIN = Path('/etc/systemd/system/r4os-studio.service.d/64-vm-release-batches.conf')


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run this explicit local host setup as root.')
    if (CONFIG.resolve(strict=True) != CONFIG or not CONFIG.is_file()
            or CONFIG.stat().st_uid != 0 or CONFIG.stat().st_mode & 0o022):
        raise SystemExit('The fixed update configuration needs host maintenance.')
    data = Path(json.loads(CONFIG.read_text())['dataDirectory'])
    root = data / 'R4OS'
    if (not data.is_absolute() or root.resolve(strict=True) != root or not root.is_dir()
            or any(char in str(root) for char in '\r\n\0')):
        raise SystemExit('The configured R4OS directory must be real.')
    directory = root / 'ReleaseBatches'
    if directory.is_symlink() or directory.exists() and not directory.is_dir():
        raise SystemExit('Refusing linked or invalid VM release-batch storage.')
    quoted = str(directory).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    value = '[Service]\nReadWritePaths="' + quoted + '"\n'
    if DROPIN.parent.is_symlink() or DROPIN.is_symlink():
        raise SystemExit('Linked web service configuration is not supported.')
    DROPIN.parent.mkdir(mode=0o755, exist_ok=True)
    if (DROPIN.parent.resolve(strict=True) != DROPIN.parent
            or DROPIN.parent.stat().st_uid != 0 or DROPIN.parent.stat().st_mode & 0o022):
        raise SystemExit('The fixed web service configuration needs host maintenance.')
    if DROPIN.exists() and (not DROPIN.is_file() or DROPIN.stat().st_uid != 0
                            or DROPIN.stat().st_mode & 0o022 or DROPIN.read_text() != value):
        raise SystemExit('An existing VM release-batch override differs. Preserve and review it.')
    owner = pwd.getpwnam('r4os-studio')
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.resolve(strict=True) != directory:
        raise SystemExit('Refusing indirect VM release-batch storage.')
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fchown(descriptor, owner.pw_uid, owner.pw_gid)
        os.fchmod(descriptor, 0o700)
    finally:
        os.close(descriptor)
    if not DROPIN.exists():
        descriptor, staging = tempfile.mkstemp(prefix='.vm-release-batches-', dir=DROPIN.parent)
        try:
            with os.fdopen(descriptor, 'w') as output:
                output.write(value); output.flush(); os.fchmod(output.fileno(), 0o644); os.fsync(output.fileno())
            os.replace(staging, DROPIN)
            descriptor = os.open(DROPIN.parent, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(descriptor)
            finally: os.close(descriptor)
        finally:
            if Path(staging).exists(): Path(staging).unlink()
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    print('Private VM release-batch storage prepared. The next regular Studio start applies this one write path. No VMs were changed.')


if __name__ == '__main__': main()
