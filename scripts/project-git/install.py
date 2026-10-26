#!/usr/bin/env python3
"""Explicit additive host installation for the fixed unprivileged Git adapter."""
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess


def main():
    if os.geteuid() != 0: raise SystemExit('Run the Git host installer as root.')
    for tool in ('/usr/bin/git', '/usr/bin/bwrap', '/usr/bin/python3'):
        if not Path(tool).is_file(): raise SystemExit('Missing Git host prerequisite: ' + tool)
    update = json.loads(Path('/etc/r4os-studio-updates/config.json').read_text())
    data = Path(update['dataDirectory']).resolve(strict=True); user = pwd.getpwnam('r4os-studio')
    config = {'schema': 1, 'uid': user.pw_uid, 'projects': str(data / 'Projects'), 'github': str(data / 'GitHub')}
    directory = Path('/etc/r4os-studio-git'); directory.mkdir(exist_ok=True)
    path = directory / 'config.json'
    if path.exists() and json.loads(path.read_text()) != config: raise SystemExit('Preserve and review the different existing Git host configuration.')
    path.write_text(json.dumps(config, indent=2) + '\n'); path.chmod(0o644)
    target = Path('/opt/r4os-studio/bin/git-launch.py')
    source = Path(__file__).with_name('launch.py')
    if target.exists() and target.read_bytes() != source.read_bytes(): raise SystemExit('Existing Git dispatcher differs; explicit qualified maintenance is required.')
    shutil.copyfile(source, target); target.chmod(0o755)
    private = data / 'Projects/.studio/github'
    private.mkdir(mode=0o700, exist_ok=True); os.chown(private, user.pw_uid, user.pw_gid)
    def quote(value): return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
    unit = '''[Unit]
Description=R4OS Studio Git coordinator
After=network-online.target

[Service]
User=r4os-studio
Group=r4os-studio
UMask=0077
ExecStart=/usr/bin/python3 -B /opt/r4os-studio/bin/git-launch.py
RuntimeDirectory=r4os-studio-git
RuntimeDirectoryMode=0700
RuntimeDirectoryPreserve=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
NoNewPrivileges=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK
CapabilityBoundingSet=
MemoryMax=1G
TasksMax=64
CPUQuota=200%
LimitFSIZE=268435456
KillMode=mixed
TimeoutStopSec=15
Restart=on-failure
'''
    unit += 'ReadWritePaths=' + quote(data / 'Projects') + '\n'
    for item in ('LLMProvider', 'Skills', 'R4OS'):
        unit += 'InaccessiblePaths=-' + quote(data / item) + '\n'
    unit += 'InaccessiblePaths=-/run/r4os-studio-vms\nInaccessiblePaths=-/run/r4os-studio-agents\nInaccessiblePaths=-/run/r4os-studio-development\n\n[Install]\nWantedBy=multi-user.target\n'
    target_unit = Path('/etc/systemd/system/r4os-studio-git.service')
    if target_unit.exists() and target_unit.read_text() != unit: raise SystemExit('Existing Git service differs; preserve it for review.')
    target_unit.write_text(unit)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', 'r4os-studio-git.service'], check=True)
    if Path('/opt/r4os-studio/current/scripts/project-git/host.py').is_file():
        subprocess.run(['systemctl', 'start', 'r4os-studio-git.service'], check=True)
    print('Git support installed. Existing bootstrap, workers, VMs and credentials preserved.')


if __name__ == '__main__': main()
