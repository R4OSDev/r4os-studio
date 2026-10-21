#!/usr/bin/env python3
"""Explicit narrow host maintenance, preserving bootstrap and existing workers."""
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess


def main():
    if os.geteuid() != 0: raise SystemExit('Run the development host installer as root.')
    for path in ('/usr/bin/bwrap', '/usr/bin/python3', '/usr/bin/systemctl'):
        if not Path(path).is_file(): raise SystemExit('Missing required development host tool: ' + path)
    update = json.loads(Path('/etc/r4os-studio-updates/config.json').read_text())
    user = pwd.getpwnam('r4os-studio'); data = Path(update['dataDirectory']).resolve(strict=True)
    projects, r4os = data / 'Projects', data / 'R4OS'
    cfg = {'schema': 1, 'uid': user.pw_uid, 'projects': str(projects), 'r4os': str(r4os)}
    parent = Path('/etc/r4os-studio-development'); parent.mkdir(exist_ok=True)
    path = parent / 'config.json'
    if path.exists() and json.loads(path.read_text()) != cfg: raise SystemExit('Existing development host configuration differs. Preserve and review it.')
    path.write_text(json.dumps(cfg, indent=2) + '\n'); path.chmod(0o644)
    target = Path('/opt/r4os-studio/bin/development-launch.py')
    shutil.copyfile(Path(__file__).parent / 'launch.py', target); target.chmod(0o755)
    def quote(p): return '"' + str(p).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
    common = '[Service]\nUser=r4os-studio\nGroup=r4os-studio\nUMask=0077\nProtectSystem=strict\nProtectHome=yes\nPrivateTmp=yes\nNoNewPrivileges=yes\nProtectKernelModules=yes\nProtectControlGroups=yes\nRestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK\nCapabilityBoundingSet=\n'
    common += 'ReadWritePaths=' + quote(projects) + '\nInaccessiblePaths=-' + quote(data / 'LLMProvider') + '\n'
    common += 'InaccessiblePaths=-' + quote(r4os / 'Instances') + '\nInaccessiblePaths=-/run/r4os-studio-vms\n'
    coordinator = '[Unit]\nDescription=R4OS Studio development coordinator\nAfter=network-online.target\n\n' + common
    coordinator += 'ExecStart=/usr/bin/python3 -B /opt/r4os-studio/bin/development-launch.py\nRuntimeDirectory=r4os-studio-development\nRuntimeDirectoryMode=0700\nRestart=on-failure\nMemoryMax=512M\nTasksMax=64\nTimeoutStopSec=25\n\n[Install]\nWantedBy=multi-user.target\n'
    worker = '[Unit]\nDescription=R4OS Studio development job %i\n\n' + common
    worker += 'ExecStart=/usr/bin/python3 -B /opt/r4os-studio/bin/development-launch.py %i\nExecStopPost=/usr/bin/python3 -B /opt/r4os-studio/bin/development-launch.py %i --finalize\nKillMode=mixed\nTimeoutStopSec=15\nMemoryMax=3G\nTasksMax=256\nCPUQuota=200%\nLimitFSIZE=268435456\nRuntimeMaxSec=660\nRestart=no\n'
    Path('/etc/systemd/system/r4os-studio-development.service').write_text(coordinator)
    Path('/etc/systemd/system/r4os-studio-development@.service').write_text(worker)
    agent_dropin = Path('/etc/systemd/system/r4os-studio-agent@.service.d')
    agent_dropin.mkdir(exist_ok=True)
    (agent_dropin / '51-development.conf').write_text('[Service]\nReadWritePaths=-/run/r4os-studio-agents\n')
    Path('/etc/polkit-1/rules.d/53-r4os-studio-development.rules').write_text('''polkit.addRule(function(action, subject) {
  if (action.id !== "org.freedesktop.systemd1.manage-units" || subject.user !== "r4os-studio") return;
  var unit = action.lookup("unit"), verb = action.lookup("verb");
  if ((verb === "start" || verb === "stop") && /^r4os-studio-development@[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\\.service$/.test(unit)) return polkit.Result.YES;
});
''')
    dropin = Path('/etc/systemd/system/r4os-studio.service.d/51-development.conf')
    dropin.write_text('[Service]\nReadWritePaths=-/run/r4os-studio-development\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    # Enable now only when the currently installed release implements this service.
    # Existing coordinators/workers/VMs are never restarted by this installer.
    current = Path('/opt/r4os-studio/current/scripts/project-development/host.py')
    if current.is_file(): subprocess.run(['systemctl', 'enable', '--now', 'r4os-studio-development.service'], check=True)
    else: subprocess.run(['systemctl', 'enable', 'r4os-studio-development.service'], check=True)
    print('Development host support installed; existing Studio, agent and VM state preserved.')


if __name__ == '__main__': main()
