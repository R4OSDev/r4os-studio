#!/usr/bin/env python3
"""Narrow maintenance for existing component hosts; never reset their setup."""
import json
import os
from pathlib import Path
import pwd
import socket
import subprocess
import uuid


def main():
    if os.geteuid() != 0:
        raise SystemExit('SDK profile host maintenance requires root.')
    config = json.loads(Path('/etc/r4os-studio-components/config.json').read_text())
    root = Path(config['root'])
    if root.resolve(strict=True) != root or not (root / 'Profiles/versions.json').is_file():
        raise SystemExit('The existing component root is invalid.')
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(10)
        client.connect('/run/r4os-studio-components/control.sock')
        client.sendall(b'{"command":"status"}\n')
        raw = b''
        while b'\n' not in raw:
            chunk = client.recv(65536)
            if not chunk:
                raise SystemExit('Component status disconnected.')
            raw += chunk
            if len(raw) > 2 * 1024**2:
                raise SystemExit('Invalid component status.')
    status = json.loads(raw.split(b'\n')[0])['status']
    if status.get('features', {}).get('sdkProfiles') != 1:
        raise SystemExit('Wait for the component coordinator to adopt the SDK profile release.')
    gate = root / 'Profiles/sdk-host-maintenance.json'
    identity = str(uuid.uuid4())
    with gate.open('x') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump({'schema': 1, 'operation': 'sdk-host-maintenance', 'requestId': identity}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(10)
            client.connect('/run/r4os-studio-components/control.sock')
            client.sendall(b'{"command":"status"}\n')
            raw = b''
            while b'\n' not in raw:
                chunk = client.recv(65536)
                if not chunk:
                    raise SystemExit('Component status disconnected.')
                raw += chunk
                if len(raw) > 2 * 1024**2:
                    raise SystemExit('Invalid component status.')
        status = json.loads(raw.split(b'\n')[0])['status']
        if (status.get('job') or {}).get('phase') == 'working':
            raise SystemExit('Wait for the original component operation to finish.')
        account = pwd.getpwnam('root')
        for suffix in ('Packages', 'Toolchains/PowerShell'):
            path = root / suffix
            if path.is_symlink() or path.resolve() != path:
                raise SystemExit('Invalid SDK host storage.')
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chown(path, account.pw_uid, account.pw_gid)
        subprocess.run(['systemctl', 'restart', 'r4os-studio-components.service'], check=True)
        print('SDK package storage enabled; only the idle component coordinator was restarted.')
    finally:
        if gate.exists() and json.loads(gate.read_text()).get('requestId') == identity:
            gate.unlink()


if __name__ == '__main__':
    main()
