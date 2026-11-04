#!/usr/bin/env python3
"""Add only the private skill-source job unit and its narrow start/stop right."""
import json
import os
from pathlib import Path
import subprocess
import uuid


def install():
    if os.geteuid() != 0:
        raise SystemExit('Install the explicit source job host support as root.')
    config = json.loads(Path('/etc/r4os-studio-agents/config.json').read_text())
    root = Path(config['projects']).parent / 'Skills'
    if root.resolve(strict=True) != root or root.stat().st_uid != config['uid']:
        raise SystemExit('Use the existing owned private Skills data directory.')
    quoted = str(root).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    unit = '''[Unit]
Description=R4OS Studio private skill source job %i
After=network.target

[Service]
Type=exec
User=r4os-studio
Group=r4os-studio
UMask=0077
ExecStart=/usr/bin/python3 -B /opt/r4os-studio/bin/skill-source-launch.py %i
KillMode=control-group
TimeoutStopSec=10
SendSIGKILL=yes
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=no
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK
ReadWritePaths="''' + quoted + '''"
MemoryMax=6G
TasksMax=512
'''
    rule = '''// R4OS Studio: only one validated private source-job UUID instance.
polkit.addRule(function(action, subject) {
  if (subject.user !== "r4os-studio" || action.id !== "org.freedesktop.systemd1.manage-units") return;
  var unit = action.lookup("unit");
  var verb = action.lookup("verb");
  if (unit && /^r4os-studio-skill-source@[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}[.]service$/.test(unit)
      && (verb === "start" || verb === "stop")) return polkit.Result.YES;
});
'''
    targets = {
        Path('/etc/systemd/system/r4os-studio-skill-source@.service'): unit.encode(),
        Path('/etc/polkit-1/rules.d/66-r4os-studio-skill-sources.rules'): rule.encode(),
        Path('/opt/r4os-studio/bin/skill-source-launch.py'): Path(__file__).with_name('source_launch.py').read_bytes(),
    }
    originals = {}
    for path, data in targets.items():
        if path.is_symlink() or path.exists() and not path.is_file():
            raise SystemExit('Refusing linked source job host support.')
        previous = path.read_bytes() if path.exists() else None
        originals[path] = previous
        # Only our exact generated earlier units are migrated: the proc fix and
        # the bounded extra memory required by the real managed REA build.
        known_previous = {data}
        if path.suffix == '.service':
            known_previous |= {data.replace(b'MemoryMax=6G\n', b'MemoryMax=2G\n')}
            known_previous |= {value.replace(b'ProtectKernelTunables=no\n', b'ProtectKernelTunables=yes\n') for value in list(known_previous)}
        if previous is not None and previous not in known_previous:
            raise SystemExit('Existing source job support differs; preserve it for explicit maintenance.')
    for path, data in targets.items():
        if originals[path] != data:
            if (path.read_bytes() if path.exists() else None) != originals[path]:
                raise SystemExit('Source job host support changed during maintenance.')
            temporary = path.with_name('.' + path.name + '.' + str(uuid.uuid4()) + '.tmp')
            with temporary.open('xb') as stream:
                os.fchmod(stream.fileno(), 0o644)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    companion=Path(__file__).with_name('install-mcp-support.py')
    if companion.is_file():subprocess.run(['/usr/bin/python3','-B',str(companion)],check=True)
    print('Private source-job unit and narrow start/stop support installed; existing services and VMs preserved.')


if __name__ == '__main__':
    install()
