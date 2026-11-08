#!/usr/bin/env python3
"""Install only the independent private session-analysis unit and narrow policy."""
import json
import os
from pathlib import Path
import subprocess
import uuid


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from service_runtime import root_service

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
User=root
Group=root
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
    targets={Path('/etc/systemd/system/r4os-studio-skill-mcp@.service'): root_service(unit).encode(), Path('/opt/r4os-studio/bin/skill-mcp-launch.py'): Path(__file__).with_name('mcp_launch.py').read_bytes()}
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
