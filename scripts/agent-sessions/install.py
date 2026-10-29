#!/usr/bin/env python3
"""Explicit host maintenance; installs only fixed unprivileged agent services."""
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
from run_limits import DEFAULT_MAX_ACTIVE_RUNS, max_active_runs


def main():
    if os.geteuid() != 0: raise SystemExit('Run the agent host installer as root.')
    for path in ('/usr/bin/bwrap', '/usr/bin/python3', '/usr/bin/systemctl'):
        if not Path(path).is_file(): raise SystemExit('Missing required agent host tool: ' + path)
    update = json.loads(Path('/etc/r4os-studio-updates/config.json').read_text())
    user = pwd.getpwnam('r4os-studio'); data = Path(update['dataDirectory']).resolve(strict=True)
    projects, providers, r4os = data / 'Projects', data / 'LLMProvider', data / 'R4OS'
    cfg = {'schema': 1, 'uid': user.pw_uid, 'projects': str(projects), 'providers': str(providers), 'r4os': str(r4os), 'maxActiveRuns': DEFAULT_MAX_ACTIVE_RUNS}
    config_dir = Path('/etc/r4os-studio-agents'); config_dir.mkdir(exist_ok=True)
    file = config_dir / 'config.json'
    if file.exists():
        existing = json.loads(file.read_text())
        if {k: v for k, v in existing.items() if k != 'maxActiveRuns'} != {k: v for k, v in cfg.items() if k != 'maxActiveRuns'}:
            raise SystemExit('Existing agent host configuration differs; preserve and review it.')
        max_active_runs(existing)
        cfg = existing
    file.write_text(json.dumps(cfg, indent=2) + '\n'); file.chmod(0o644)
    target = Path('/opt/r4os-studio/bin/agent-launch.py')
    shutil.copyfile(Path(__file__).parent / 'launch.py', target); target.chmod(0o755)
    def quote(path): return '"' + str(path).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
    # These two systemd filters break rootless Bubblewrap on this host:
    # ProtectKernelTunables denies its private proc mount; RestrictSUIDSGID
    # returns ENOSYS for open_tree. The inner namespace remains authoritative.
    common = '[Service]\nUser=r4os-studio\nGroup=r4os-studio\nUMask=0077\nProtectSystem=strict\nProtectHome=yes\nPrivateTmp=yes\nNoNewPrivileges=yes\nProtectKernelModules=yes\nProtectControlGroups=yes\nRestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK\nCapabilityBoundingSet=\n'
    common += 'ReadWritePaths=' + quote(projects) + '\nReadWritePaths=' + quote(providers) + '\n'
    common += 'InaccessiblePaths=-' + quote(r4os / 'Instances') + '\nInaccessiblePaths=-/run/r4os-studio-vms\n'
    coordinator = '[Unit]\nDescription=R4OS Studio agent coordinator\nAfter=network-online.target\n\n' + common
    coordinator += 'ExecStart=/usr/bin/python3 -B /opt/r4os-studio/bin/agent-launch.py\nRuntimeDirectory=r4os-studio-agents\nRuntimeDirectoryMode=0700\nRuntimeDirectoryPreserve=yes\nRestart=on-failure\nMemoryMax=512M\nTasksMax=64\nTimeoutStopSec=25\n\n[Install]\nWantedBy=multi-user.target\n'
    worker = '[Unit]\nDescription=R4OS Studio agent run %i\nAfter=network-online.target\n\n' + common
    worker += 'ExecStart=/usr/bin/python3 -B /opt/r4os-studio/bin/agent-launch.py %i\nExecStopPost=/usr/bin/python3 -B /opt/r4os-studio/bin/agent-launch.py %i --finalize\nKillMode=mixed\nTimeoutStopSec=15\nMemoryMax=2G\nTasksMax=256\nCPUQuota=200%\nLimitFSIZE=268435456:infinity\nRestart=no\n'
    Path('/etc/systemd/system/r4os-studio-agents.service').write_text(coordinator)
    Path('/etc/systemd/system/r4os-studio-agent@.service').write_text(worker)
    polkit = '''polkit.addRule(function(action, subject) {
  if (action.id !== "org.freedesktop.systemd1.manage-units" || subject.user !== "r4os-studio") return;
  var unit = action.lookup("unit"), verb = action.lookup("verb");
  if ((verb === "start" || verb === "stop") && /^r4os-studio-agent@[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\\.service$/.test(unit)) return polkit.Result.YES;
});
'''
    Path('/etc/polkit-1/rules.d/52-r4os-studio-agents.rules').write_text(polkit)
    dropin = Path('/etc/systemd/system/r4os-studio.service.d/50-agents.conf')
    dropin.write_text('[Service]\nReadWritePaths=-/run/r4os-studio-agents\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    # Never restart a pre-existing coordinator or any worker/VM here.
    subprocess.run(['systemctl', 'enable', '--now', 'r4os-studio-agents.service'], check=True)
    print('Agent host support installed. Existing Studio/bootstrap/VM configuration was preserved.')


if __name__ == '__main__': main()
