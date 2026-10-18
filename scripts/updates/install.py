#!/usr/bin/env python3
"""One-time privileged bootstrap; updates never execute downloaded installers."""
import argparse
import datetime
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
from urllib.parse import urlparse

from host import BASE, CACHE, STATE, Updater, atomic_json, copy_release, run, switch


def quoted(value):
    if any(char in str(value) for char in '\n\r\0'):
        raise ValueError('Unsupported path.')
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def account(name):
    try:
        return pwd.getpwnam(name)
    except KeyError:
        subprocess.run(['/usr/sbin/useradd', '--system', '--user-group', '--no-create-home',
                        '--home-dir', '/nonexistent', '--shell', '/usr/sbin/nologin', name], check=True)
        return pwd.getpwnam(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--repository', default='https://gitea.r4public.r4network/R4mbo/R4OS_Studio.git')
    parser.add_argument('--ca-file', type=Path, help='Explicitly trusted CA/leaf certificate for a private Git host')
    parser.add_argument('--resolve', default='', help='Git curl mapping: hostname:443:address')
    parser.add_argument('--check-interval', type=int, default=21600)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run this bootstrap installer as root.')
    url = urlparse(args.repository)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise SystemExit('Use a fixed anonymous HTTPS repository URL without credentials.')
    if args.check_interval < 300 or args.check_interval > 604800:
        raise SystemExit('Check interval must be between 5 minutes and 7 days.')
    app = args.app.resolve()
    scripts = Path(__file__).resolve().parent
    if not (app / 'backend/dist/server.js').is_file() or not (app / 'frontend/dist/index.html').is_file():
        raise SystemExit('Build App before installing update support.')
    # Re-running never replaces the active deployment or its configuration.
    if Path('/etc/r4os-studio-updates/config.json').exists():
        raise SystemExit('Update support is already configured. Keep the existing deployment; host support upgrades require explicit maintenance.')
    node = shutil.which('node')
    corepack = shutil.which('corepack')
    if not node or not corepack or not shutil.which('git'):
        raise SystemExit('Node, Corepack and Git must be installed first.')
    studio = account('r4os-studio')
    builder = account('r4os-studio-updater')
    for path in [BASE / 'releases', BASE / 'bin', STATE, CACHE, Path('/etc/r4os-studio-updates')]:
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o755)
    for name in ['home', 'corepack']:
        path = CACHE / name
        path.mkdir(exist_ok=True)
        os.chown(path, builder.pw_uid, builder.pw_gid)
        path.chmod(0o700)
    data = app / 'Data'
    data.mkdir(exist_ok=True)
    os.chown(data, studio.pw_uid, studio.pw_gid)
    data.chmod(0o700)
    for suffix in ['LLMProvider', 'R4OS/Instances', 'R4OS/Images']:
        path = data / suffix
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, studio.pw_uid, studio.pw_gid)
        path.chmod(0o700)
    config = {'repository': args.repository, 'resolve': args.resolve,
              'checkIntervalSeconds': args.check_interval, 'dataDirectory': str(data),
              'developmentSource': str(app), 'node': str(Path(node).resolve()),
              'corepack': str(Path(corepack).absolute())}
    if args.ca_file:
        certificate = Path('/etc/r4os-studio-updates/source-ca.pem')
        shutil.copyfile(args.ca_file, certificate)
        certificate.chmod(0o644)
        config['caFile'] = str(certificate)
    version = json.loads((app / 'shared/version.json').read_text())['version']
    identity = f'bootstrap-{version}-{datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")}'
    destination = BASE / 'releases' / identity
    copy_release(app, destination)
    commit = None
    if (app / '.git').exists() and not run(['/usr/bin/git', '-C', str(app), 'status', '--porcelain']).strip():
        commit = run(['/usr/bin/git', '-C', str(app), 'rev-parse', 'HEAD']).strip()
    atomic_json(destination / 'release.json', {'version': version, 'commit': commit, 'id': identity})
    switch(destination)
    for source, target in [('host.py', 'update-host.py'), ('vm-dispatch.py', 'vm-dispatch.py'), ('studio-launch.py', 'studio-launch.py')]:
        shutil.copyfile(scripts / source, BASE / 'bin' / target)
        (BASE / 'bin' / target).chmod(0o755)
    atomic_json(Path('/etc/r4os-studio-updates/config.json'), config)
    unit_directory = Path('/etc/systemd/system')
    for source in (scripts / 'systemd').glob('*.service'):
        shutil.copyfile(source, unit_directory / source.name)
    # Package the baseline web service for fresh installs, retain local base-unit configuration otherwise.
    unit = unit_directory / 'r4os-studio.service'
    if not unit.exists():
        template = (scripts / 'systemd/r4os-studio.service.in').read_text()
        unit.write_text(template.replace('@APP_DIRECTORY@', str(app)).replace('@NODE_BINARY@', config['node']))
    dropin = unit_directory / 'r4os-studio.service.d'
    dropin.mkdir(exist_ok=True)
    (dropin / '20-updates.conf').write_text('[Service]\nExecStart=\nExecStart=/usr/bin/python3 /opt/r4os-studio/bin/studio-launch.py\n'
        f'WorkingDirectory={BASE / "current"}\n'
        f'Environment={quoted("STUDIO_DATA_DIR=" + str(data / "LLMProvider"))}\n'
        f'Environment={quoted("STUDIO_R4OS_DIR=" + str(data / "R4OS"))}\n'
        'Environment=STUDIO_UPDATE_SOCKET=/run/r4os-studio-updates/control.sock\n'
        'ReadWritePaths=-/run/r4os-studio-updates\n')
    # Pin existing workers before replacing only the template. Never stop/restart any VM.
    template = unit_directory / 'r4os-studio-vm@.service'
    if template.exists():
        text = template.read_text()
        if 'vm-dispatch.py' not in text:
            for line in run(['/usr/bin/systemctl', 'list-units', '--all', '--plain', '--no-legend', 'r4os-studio-vm@*.service']).splitlines():
                match = re.search(r'r4os-studio-vm@([a-f0-9-]{36})\.service', line)
                if match:
                    runtime = Path('/run/r4os-studio-vms') / match[1]
                    if runtime.exists():
                        pin = runtime / 'worker.json'
                        atomic_json(pin, {'release': str(destination)}, 0o600)
                        os.chown(pin, studio.pw_uid, studio.pw_gid)
            text = re.sub(r'^ExecStart=.*$', 'ExecStart=/usr/bin/python3 /opt/r4os-studio/bin/vm-dispatch.py %i', text, flags=re.M)
            text = re.sub(r'^ExecStopPost=.*$', 'ExecStopPost=/usr/bin/python3 /opt/r4os-studio/bin/vm-dispatch.py %i --sync', text, flags=re.M)
            template.write_text(text)
    run(['/usr/bin/systemctl', 'daemon-reload'])
    run(['/usr/bin/systemctl', 'enable', '--now', 'r4os-studio-updates.service'])
    run(['/usr/bin/systemctl', 'enable', 'r4os-studio.service'])
    run(['/usr/bin/systemctl', 'restart', 'r4os-studio.service'])
    Updater(config).healthy(json.loads((destination / 'release.json').read_text()))
    print(f'Update support installed; persistent data: {data}. No VMs were stopped.')


if __name__ == '__main__':
    main()
