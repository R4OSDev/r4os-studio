#!/usr/bin/env python3
"""Explicit local broker setup/adoption; preserve bootstrap, data and VM units."""
import argparse
import json
import os
from pathlib import Path
import pwd
import subprocess
import tempfile
import importlib.util

CONFIG = Path('/etc/r4os-studio-remote/config.json')
DISPATCH = Path('/opt/r4os-studio/bin/remote-host.py')
UNIT = Path('/etc/systemd/system/r4os-studio-remote.service')


def install_file(path, content, mode):
    encoded = content.encode()
    if path.exists() or path.is_symlink():
        if path.resolve(strict=True) != path or not path.is_file() or path.stat().st_uid != 0 or path.stat().st_mode & 0o777 != mode or path.read_bytes() != encoded:
            raise SystemExit('Existing remote host support differs. Preserve it for explicit maintenance: ' + str(path))
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.remote-', delete=False) as file:
        temporary = Path(file.name); file.write(encoded); file.flush(); os.fsync(file.fileno())
    temporary.chmod(mode); os.chown(temporary, 0, 0); os.link(temporary, path); temporary.unlink()
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def control(*args): subprocess.run(['/usr/bin/systemctl', *args], check=True)


def setup():
    user = pwd.getpwnam('r4os-studio')
    old = json.loads(Path('/etc/r4os-studio-updates/config.json').read_text()); base = Path(old['dataDirectory'])
    if base.resolve(strict=True) != base: raise SystemExit('The configured Data directory must be real.')
    directory = base / 'RemoteHosts'
    if directory.is_symlink(): raise SystemExit('Refusing linked Remote Host storage.')
    directory.mkdir(mode=0o700, exist_ok=True); os.chown(directory, user.pw_uid, user.pw_gid); directory.chmod(0o700)
    CONFIG.parent.mkdir(mode=0o755, exist_ok=True)
    if CONFIG.parent.resolve(strict=True) != CONFIG.parent: raise SystemExit('Invalid remote configuration directory.')
    config = {'schema': 1, 'uid': user.pw_uid, 'directory': str(directory), 'runtime': '/run/r4os-studio-remote'}
    install_file(CONFIG, json.dumps(config, indent=2) + '\n', 0o644)
    install_file(DISPATCH, Path(__file__).with_name('dispatch.py').read_text(), 0o755)
    quoted = str(directory).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    service = '''[Unit]
Description=R4OS Studio private Remote Host broker
After=network.target

[Service]
Type=simple
User=r4os-studio
Group=r4os-studio
ExecStart=/opt/r4os-studio/bin/remote-host.py
RuntimeDirectory=r4os-studio-remote
RuntimeDirectoryMode=0700
UMask=0077
Restart=always
RestartSec=3
KillMode=control-group
TimeoutStopSec=20
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictNamespaces=yes
LockPersonality=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
MemoryMax=256M
TasksMax=64
LimitNOFILE=256
ReadWritePaths="''' + quoted + '''" /run/r4os-studio-remote

[Install]
WantedBy=multi-user.target
'''
    install_file(UNIT, service, 0o644); control('daemon-reload')
    spec = importlib.util.spec_from_file_location('remote_project_job_setup', Path(__file__).with_name('install-job-support.py'))
    job_setup = importlib.util.module_from_spec(spec); spec.loader.exec_module(job_setup); job_setup.main()
    print('Private unprivileged remote broker prepared. Install the compatible immutable release, then use --adopt.')


def adopt():
    release = Path('/opt/r4os-studio/current').resolve(strict=True)
    if not release.is_relative_to('/opt/r4os-studio/releases'): raise SystemExit('Invalid installed release.')
    protocol = json.loads((release / 'shared/remote-host.json').read_text())
    if protocol.get('hostProtocol') != 1 or protocol.get('catalogSchema') != 1: raise SystemExit('Install the compatible stable release first.')
    user = pwd.getpwnam('r4os-studio'); config = json.loads(CONFIG.read_text())
    if config['uid'] != user.pw_uid: raise SystemExit('Remote broker user changed; preserve its configuration.')
    control('enable', UNIT.name)
    state = subprocess.check_output(['/usr/bin/systemctl', 'show', UNIT.name, '--property=ActiveState', '--value'], text=True).strip()
    if state == 'active':
        # The original broker closes admissions before the fixed-unit restart.
        script = "import json,socket; s=socket.socket(socket.AF_UNIX); s.settimeout(5); s.connect('/run/r4os-studio-remote/host.sock'); s.sendall(b'{\"protocol\":1,\"operation\":\"prepare_adoption\"}\\n'); print(s.makefile().readline())"
        raw = subprocess.check_output(['/usr/sbin/runuser', '-u', 'r4os-studio', '--', '/usr/bin/python3', '-B', '-c', script], text=True, timeout=8)
        result = json.loads(raw)
        if not result.get('result', {}).get('ready'): raise SystemExit('The original remote broker is busy. Its work was preserved; adopt when idle.')
        control('restart', UNIT.name)
    elif state in ('inactive', 'failed'): control('start', UNIT.name)
    else: raise SystemExit('Wait for the original remote broker state to settle.')
    print('The compatible unprivileged remote broker started. Existing VM, agent and build services were not stopped.')


if __name__ == '__main__':
    if os.geteuid() != 0: raise SystemExit('Run this explicit local host setup as root.')
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--adopt', action='store_true'); args = parser.parse_args()
    adopt() if args.adopt else setup()
