#!/usr/bin/env python3
"""Install only the independent private session-analysis unit and narrow policy."""
import json
import os
from pathlib import Path
import subprocess
import uuid


def install():
    if os.geteuid()!=0:raise SystemExit('Install explicit session MCP host support as root.')
    config=json.loads(Path('/etc/r4os-studio-agents/config.json').read_bytes())
    roots=[Path(config['projects']),Path(config['projects']).parent/'Skills']
    if any(path.resolve(strict=True)!=path or path.stat().st_uid!=config['uid'] for path in roots):
        raise SystemExit('Use the existing owned private project and skill data directories.')
    def quote(path):return '"'+str(path).replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'
    unit='''[Unit]
Description=R4OS Studio private session analysis %i
After=network.target

[Service]
Type=exec
User=r4os-studio
Group=r4os-studio
UMask=0077
ExecStart=/usr/bin/python3 -B /opt/r4os-studio/bin/skill-mcp-launch.py %i
RuntimeDirectory=r4os-studio-skill-mcp/%i
RuntimeDirectoryMode=0700
KillMode=control-group
TimeoutStopSec=25
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
ReadWritePaths='''+' '.join(quote(path) for path in roots)+'''
MemoryMax=6G
TasksMax=512
'''
    rule='''// R4OS Studio: validated private per-session analysis instances only.
polkit.addRule(function(action, subject) {
  if (subject.user !== "r4os-studio" || action.id !== "org.freedesktop.systemd1.manage-units") return;
  var unit = action.lookup("unit");
  var verb = action.lookup("verb");
  if (unit && /^r4os-studio-skill-mcp@[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}[.]service$/.test(unit)
      && (verb === "start" || verb === "stop" || verb === "freeze" || verb === "thaw" || verb === "ref" || verb === "unref")) return polkit.Result.YES;
});
'''
    # Debian's system bus policy omits Manager.FreezeUnit/ThawUnit. Authorisation still
    # passes through systemd's per-unit start/stop polkit checks above.
    bus_policy='''<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <policy user="r4os-studio">
    <allow send_destination="org.freedesktop.systemd1" send_interface="org.freedesktop.systemd1.Manager" send_member="FreezeUnit"/>
    <allow send_destination="org.freedesktop.systemd1" send_interface="org.freedesktop.systemd1.Manager" send_member="ThawUnit"/>
  </policy>
</busconfig>
'''
    targets={Path('/etc/dbus-1/system.d/r4os-studio-skill-mcp.conf'):bus_policy.encode(),
        Path('/etc/systemd/system/r4os-studio-skill-mcp@.service'):unit.encode(),
        Path('/etc/polkit-1/rules.d/67-r4os-studio-skill-mcp.rules'):rule.encode(),
        Path('/opt/r4os-studio/bin/skill-mcp-launch.py'):Path(__file__).with_name('mcp_launch.py').read_bytes()}
    previous={}
    for path,value in targets.items():
        if path.is_symlink() or path.exists() and not path.is_file():raise SystemExit('Refusing linked analysis host support.')
        previous[path]=path.read_bytes() if path.exists() else None
        known={value}
        if path.suffix=='.conf':known.add(value.replace(b'org.freedesktop.systemd1.Manager',b'org.freedesktop.systemd1.Unit').replace(b'FreezeUnit',b'Freeze').replace(b'ThawUnit',b'Thaw'))
        if path.suffix=='.rules':known.add(value.replace(b' || verb === "ref" || verb === "unref"',b''))
        if previous[path] is not None and previous[path] not in known:raise SystemExit('Existing analysis host support differs; preserve it for explicit maintenance.')
    for path,value in targets.items():
        if previous[path]==value:continue
        if (path.read_bytes() if path.exists() else None)!=previous[path]:raise SystemExit('Analysis support changed during maintenance.')
        temporary=path.with_name('.'+path.name+'.'+str(uuid.uuid4())+'.tmp')
        with temporary.open('xb') as output:
            os.fchmod(output.fileno(),0o644);output.write(value);output.flush();os.fsync(output.fileno())
        os.replace(temporary,path)
        fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    subprocess.run(['/usr/bin/systemctl','daemon-reload'],check=True)
    subprocess.run(['/usr/bin/busctl','call','org.freedesktop.DBus','/org/freedesktop/DBus',
        'org.freedesktop.DBus','ReloadConfig'],check=True)
    print('Independent session MCP unit and narrow policy installed; existing user resources preserved.')


if __name__=='__main__':install()
