#!/usr/bin/env python3
"""Explicit host maintenance: install the bounded, unprivileged component service."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run the component host installer as root.')
    config_file = Path('/etc/r4os-studio-updates/config.json')
    if not config_file.is_file():
        raise SystemExit('Set up managed Studio updates first.')
    config = json.loads(config_file.read_text())
    root = Path(config['dataDirectory']) / 'R4OS'
    user = pwd.getpwnam('r4os-studio')
    for suffix in ('Profiles', 'SDK', 'Contract', 'Libraries', 'Images', 'Toolchains/Zig', 'Toolchains/Rust', 'Toolchains/QEMU', 'Toolchains/Codex'):
        path = root / suffix
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, user.pw_uid, user.pw_gid)
        path.chmod(0o700)
    external = {}
    for kind, binary in (('qemu', '/usr/bin/qemu-system-x86_64'), ('codex', '/opt/r4os-studio/bin/codex')):
        path = Path(binary)
        result = subprocess.check_output([binary, '--version'], text=True)
        match = re.search(r'(\d+\.\d+\.\d+)', result)
        if not match:
            raise SystemExit(f'Could not verify the installed {kind}.')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        info = path.stat()
        record = {'id': 'system-' + match[1], 'version': match[1], 'binary': binary,
                  'sha256': digest, 'binarySize': info.st_size, 'binaryMtimeNs': info.st_mtime_ns, 'external': True}
        if kind == 'qemu':
            record['imageBinary'] = '/usr/bin/qemu-img'
        external[kind] = record
    directory = Path('/etc/r4os-studio-components')
    directory.mkdir(exist_ok=True)
    path = directory / 'config.json'
    if not path.exists():
        path.write_text(json.dumps({'schema': 1, 'root': str(root), 'uid': user.pw_uid, 'external': external}, indent=2) + '\n')
        path.chmod(0o644)
    elif json.loads(path.read_text()).get('root') != str(root):
        raise SystemExit('Existing component configuration has a different data path.')
    scripts = Path(__file__).resolve().parent
    shutil.copyfile(scripts / 'launch.py', '/opt/r4os-studio/bin/components-launch.py')
    Path('/opt/r4os-studio/bin/components-launch.py').chmod(0o755)
    # The code follows the current release on the next service start, never as root.
    escaped = lambda value: '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
    unit = '[Unit]\nDescription=R4OS Studio component downloads\nAfter=network-online.target\n\n[Service]\nUser=r4os-studio\nGroup=r4os-studio\nExecStart=/usr/bin/python3 -B /opt/r4os-studio/bin/components-launch.py\nRuntimeDirectory=r4os-studio-components\nRuntimeDirectoryMode=0700\nProtectSystem=strict\nProtectHome=yes\nPrivateTmp=yes\nNoNewPrivileges=yes\nProtectKernelTunables=yes\nProtectKernelModules=yes\nProtectControlGroups=yes\nRestrictSUIDSGID=yes\nRestrictAddressFamilies=AF_UNIX AF_INET AF_INET6\nCapabilityBoundingSet=\nUMask=0077\nRestart=on-failure\nTimeoutStopSec=15\n'
    unit += 'CPUQuota=800%\nMemoryMax=8G\nTasksMax=512\n'
    for suffix in ('Profiles', 'SDK', 'Contract', 'Libraries', 'Images', 'Toolchains'):
        unit += 'ReadWritePaths=' + escaped(root / suffix) + '\n'
    for suffix in ('LLMProvider', 'Projects', 'R4OS/Instances'):
        unit += 'InaccessiblePaths=-' + escaped(Path(config['dataDirectory']) / suffix) + '\n'
    unit += '\n[Install]\nWantedBy=multi-user.target\n'
    Path('/etc/systemd/system/r4os-studio-components.service').write_text(unit)
    dropin = Path('/etc/systemd/system/r4os-studio.service.d/30-components.conf')
    dropin.write_text('[Service]\nReadWritePaths=-/run/r4os-studio-components\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'r4os-studio-components.service'], check=True)
    print('Component support installed. The active Studio release must contain scripts/components/service.py. No VMs were stopped.')


if __name__ == '__main__':
    main()
