#!/usr/bin/env python3
"""Fixed host updater. Only this root-owned bootstrap code controls activation.

Remote source and package scripts are built by a separate sandboxed service user.
No service templates or privileged scripts from downloaded releases are executed.
"""
import copy
import datetime
import fcntl
import grp
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import socketserver
import stat
import struct
import subprocess
import sys
import threading
import time
import urllib.request

CONFIG = Path('/etc/r4os-studio-updates/config.json')
STATE = Path('/var/lib/r4os-studio-updates')
CACHE = Path('/var/cache/r4os-studio-updates')
BASE = Path('/opt/r4os-studio')
SOCKET = Path('/run/r4os-studio-updates/control.sock')
BUILD_UNIT = 'r4os-studio-update-build.service'
STUDIO_UNIT = 'r4os-studio.service'
TAG = re.compile(r'^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')
SHA = re.compile(r'^[a-f0-9]{40}$')
BUSY = {'checking', 'downloading', 'building', 'activating', 'recovering'}
COMPATIBILITY = {'hostProtocol': 1, 'dataSchema': 1, 'vmWorkerProtocol': 1}
AGENT_COMPATIBILITY = {'agentHostProtocol': 1, 'agentWorkerProtocol': 1, 'agentDataSchema': 1}
DEVELOPMENT_COMPATIBILITY = {**COMPATIBILITY, **AGENT_COMPATIBILITY,
    'agentToolProfiles': ['studio-tools-v1', 'studio-tools-v2', 'studio-tools-v3', 'studio-tools-v4'],
    'developmentHostProtocol': 1, 'developmentWorkerProtocol': 1, 'developmentDataSchema': 1}
SKILL_COMPATIBILITY = {**DEVELOPMENT_COMPATIBILITY,
    'agentToolProfiles': DEVELOPMENT_COMPATIBILITY['agentToolProfiles'] + ['studio-skill-tools-v1']}
AUTHOR_COMPATIBILITY = {**SKILL_COMPATIBILITY,
    'agentToolProfiles': SKILL_COMPATIBILITY['agentToolProfiles'] + ['studio-skill-tools-v2']}


def compatible(value):
    # Legacy releases remain valid rollback targets. New agent protocols require
    # this explicit host maintenance, never a downloaded privileged installer.
    previous = {**DEVELOPMENT_COMPATIBILITY, 'agentToolProfiles': ['studio-tools-v1', 'studio-tools-v2']}
    return value in (COMPATIBILITY, {**COMPATIBILITY, **AGENT_COMPATIBILITY}, previous, {**DEVELOPMENT_COMPATIBILITY, 'agentToolProfiles': ['studio-tools-v1', 'studio-tools-v2', 'studio-tools-v3']}, DEVELOPMENT_COMPATIBILITY, SKILL_COMPATIBILITY, AUTHOR_COMPATIBILITY)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def atomic_json(path, value, mode=0o644):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    with open(temp, 'w', encoding='utf-8') as stream:
        os.fchmod(stream.fileno(), mode)
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_json(path):
    return json.loads(Path(path).read_text())


def run(args, **kwargs):
    # No interactive credentials, global Git configuration or caller-supplied env.
    env = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_TERMINAL_PROMPT': '0', 'GIT_ASKPASS': '/bin/false'}
    result = subprocess.run(args, env=env, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=kwargs.pop('timeout', 90), **kwargs)
    if result.returncode:
        raise RuntimeError(f'{Path(args[0]).name} failed: {result.stdout[-1600:]}')
    return result.stdout


def git(config):
    args = ['/usr/bin/git', '-c', 'credential.helper=', '-c', 'core.hooksPath=/dev/null',
            '-c', 'protocol.file.allow=never', '-c', 'http.sslVerify=true']
    if config.get('caFile'):
        args += ['-c', f'http.sslCAInfo={config["caFile"]}']
    if config.get('resolve'):
        args += ['-c', f'http.curloptResolve={config["resolve"]}']
    return args


def reset_build_failure():
    # Unlike start/stop, reset-failed does not load an inactive, garbage-collected
    # unit. Reset only an actually failed (therefore still loaded) build service.
    result = subprocess.run(['/usr/bin/systemctl', 'is-failed', '--quiet', BUILD_UNIT], timeout=10)
    if result.returncode == 0:
        run(['/usr/bin/systemctl', 'reset-failed', BUILD_UNIT])


def releases(text):
    """Stable numeric tags only; peel annotated tags to their commit identity."""
    values = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 2 or not SHA.fullmatch(parts[0]):
            continue
        name = parts[1].removeprefix('refs/tags/')
        peeled = name.endswith('^{}')
        name = name.removesuffix('^{}')
        match = TAG.fullmatch(name)
        if match and (peeled or name not in values):
            values[name] = {'version': name[1:], 'tag': name, 'commit': parts[0]}
    return sorted(values.values(), key=lambda r: tuple(map(int, r['version'].split('.'))))


def switch(path):
    temp = BASE / '.current-next'
    temp.unlink(missing_ok=True)
    temp.symlink_to(path)
    os.replace(temp, BASE / 'current')
    descriptor = os.open(BASE, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def copy_release(source, destination):
    """Copy stopped build output, rejecting special files and escaping links."""
    source = source.resolve()
    for root, directories, files in os.walk(source, followlinks=False):
        directories[:] = [name for name in directories if name not in {'.git', 'Data', '.local-data'}]
        for name in directories + files:
            item = Path(root) / name
            info = item.lstat()
            if item.is_symlink():
                if os.path.isabs(os.readlink(item)) or not item.resolve().is_relative_to(source):
                    raise RuntimeError('Build contains a link outside its release directory.')
            elif not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise RuntimeError('Build contains a special file.')
    shutil.copytree(source, destination, symlinks=True,
                    ignore=shutil.ignore_patterns('.git', 'Data', '.local-data', '.env', '.env.*', '__pycache__'))
    for root, directories, files in os.walk(destination, followlinks=False):
        for item in [Path(root)] + [Path(root) / name for name in directories + files]:
            os.chown(item, 0, 0, follow_symlinks=False)
            if not item.is_symlink():
                os.chmod(item, 0o755 if item.is_dir() or item.stat().st_mode & 0o111 else 0o644)


class Updater:
    def __init__(self, config):
        self.config = config
        self.lock = threading.RLock()
        self.working = False
        self.state = {'latest': None, 'phase': 'idle', 'message': 'Automatic checks are enabled.',
                      'error': None, 'lastChecked': None, 'history': []}
        if (STATE / 'status.json').exists():
            self.state.update(read_json(STATE / 'status.json'))

    def installed(self):
        return read_json(BASE / 'current/release.json')

    def status(self):
        with self.lock:
            value = copy.deepcopy(self.state)
            installed = self.installed()
            latest = value['latest']
            value.update(enabled=True, installed={'version': installed['version'], 'commit': installed['commit']},
                         source=self.config['repository'], checkIntervalSeconds=self.config['checkIntervalSeconds'])
            value['available'] = bool(latest and tuple(map(int, latest['version'].split('.'))) >
                                      tuple(map(int, installed['version'].split('.'))))
            checked = value['lastChecked']
            value['nextCheck'] = (datetime.datetime.fromisoformat(checked) + datetime.timedelta(
                seconds=self.config['checkIntervalSeconds'])).isoformat() if checked else None
            return value

    def change(self, **values):
        with self.lock:
            self.state.update(values)
            atomic_json(STATE / 'status.json', self.state, 0o600)

    def discover(self):
        candidates = releases(run(git(self.config) + ['ls-remote', '--tags', self.config['repository']], timeout=60))
        self.change(latest=candidates[-1] if candidates else None, lastChecked=now(), error=None)
        return self.state['latest']

    def check(self):
        self.change(phase='checking', message='Checking published versions…', error=None)
        latest = self.discover()
        self.change(phase='idle', message='A new version is available.' if self.status()['available'] else
                    ('R4OS Studio is up to date.' if latest else 'No stable version tags have been published yet.'))

    def healthy(self, manifest):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(45):
            try:
                with opener.open('http://127.0.0.1:5010/api/health', timeout=1) as response:
                    value = json.load(response)
                if value.get('status') == 'ok' and value.get('version') == manifest['version'] and value.get('release') == manifest['id']:
                    return
            except (OSError, ValueError):
                pass
            time.sleep(1)
        raise RuntimeError('The new Studio version did not pass its startup health check.')

    def restart(self):
        # A broken release can exhaust Restart=on-failure's start limit before rollback.
        run(['/usr/bin/systemctl', 'reset-failed', STUDIO_UNIT])
        run(['/usr/bin/systemctl', 'restart', STUDIO_UNIT], timeout=60)

    def activate(self, destination):
        previous = (BASE / 'current').resolve()
        manifest = read_json(destination / 'release.json')
        atomic_json(STATE / 'transaction.json', {'previous': str(previous), 'next': str(destination)}, 0o600)
        self.change(phase='activating', message='Restarting R4OS Studio. Virtual machines keep running.')
        try:
            switch(destination)
            self.restart()
            self.healthy(manifest)
        except Exception as original:
            switch(previous)
            self.restart()
            try:
                self.healthy(read_json(previous / 'release.json'))
            except Exception as rollback:
                raise RuntimeError(f'Update failed; the previous release was selected but recovery needs host attention: {rollback}') from original
            (STATE / 'transaction.json').unlink(missing_ok=True)
            self.record(manifest['version'], 'rolled_back', 'Startup failed. The previous version was restored.')
            self.change(phase='rolled_back', message='Update failed. The previous version was restored.', error=str(original))
            return False
        (STATE / 'transaction.json').unlink(missing_ok=True)
        self.record(manifest['version'], 'installed', 'Update installed successfully.')
        self.change(phase='complete', message='Update installed successfully.', error=None)
        return True

    def recover(self):
        pending = STATE / 'transaction.json'
        if pending.exists():
            value = read_json(pending)
            previous = Path(value['previous']).resolve()
            if not previous.is_relative_to(BASE / 'releases') or not (previous / 'release.json').is_file():
                raise RuntimeError('Invalid recovery release; host intervention is required.')
            self.change(phase='recovering', message='Recovering an interrupted update.')
            switch(previous)
            self.restart()
            self.healthy(read_json(previous / 'release.json'))
            pending.unlink()
            self.record(self.installed()['version'], 'rolled_back', 'Recovered an interrupted update.')
            self.change(phase='rolled_back', message='Recovered the previous version after an interrupted update.')
        elif self.state['phase'] in BUSY:
            self.change(phase='failed', message='The previous operation was interrupted. Check again to retry.', error='Operation interrupted.')

    def record(self, version, outcome, message):
        history = self.state['history'][-9:] + [{'version': version, 'outcome': outcome, 'message': message, 'time': now()}]
        self.change(history=history)

    def install(self, expected):
        self.change(phase='downloading', message='Verifying the selected release…', error=None)
        latest = self.discover()
        if not latest or expected != {'tag': latest['tag'], 'commit': latest['commit']} or not self.status()['available']:
            raise RuntimeError('The selected update has changed. Check for updates and try again.')
        source = self.config.get('developmentSource')
        if source and (Path(source) / '.git').exists():
            dirty = run(['/usr/bin/git', '-C', source, 'status', '--porcelain', '--untracked-files=normal'])
            if dirty.strip():
                raise RuntimeError('Local source changes exist. Commit or preserve them before installing an update.')
        if any(shutil.disk_usage(path).free < 1024 ** 3 for path in [CACHE, BASE]):
            raise RuntimeError('At least 1 GiB of free space is required for staging and release storage.')
        reset_build_failure()
        run(['/usr/bin/systemctl', 'stop', BUILD_UNIT])
        build = CACHE / 'build'
        shutil.rmtree(build, ignore_errors=True)
        build.mkdir(mode=0o755)
        account = pwd.getpwnam('r4os-studio-updater')
        os.chown(build, account.pw_uid, account.pw_gid)
        atomic_json(STATE / 'job.json', latest)
        self.change(phase='building', message='Downloading and building the release. Studio and VMs remain available.')
        run(['/usr/bin/systemctl', 'start', BUILD_UNIT], timeout=1250)
        # Type=oneshot and KillMode=control-group leave no writer in the build service.
        run(['/usr/bin/systemctl', 'stop', BUILD_UNIT])
        source = build / 'source'
        if source.is_symlink() or not source.resolve().is_relative_to(build.resolve()):
            raise RuntimeError('Invalid build output directory.')
        version = read_json(source / 'shared/version.json')['version']
        if not compatible(read_json(source / 'shared/update-host.json')):
            raise RuntimeError('This release requires host support or a data migration. Manual maintenance is required.')
        if version != latest['version'] or not (source / 'backend/dist/server.js').is_file() or not (source / 'frontend/dist/index.html').is_file():
            raise RuntimeError('The built application does not match its published version.')
        identity = f'{version}-{latest["commit"][:12]}'
        destination = BASE / 'releases' / identity
        if destination.exists():
            # Never reuse a failed or partially copied tree.
            identity += f'-{int(time.time())}'
            destination = BASE / 'releases' / identity
        try:
            copy_release(source, destination)
            atomic_json(destination / 'release.json', {**latest, 'id': identity})
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        self.activate(destination)

    def start(self, command, release=None):
        if command not in {'check', 'install'}:
            raise ValueError('Unsupported update command.')
        with self.lock:
            if self.working:
                raise ValueError('Another update operation is already running.')
            if command == 'install' and (not isinstance(release, dict) or set(release) != {'tag', 'commit'}
                or not isinstance(release['tag'], str) or not TAG.fullmatch(release['tag'])
                or not isinstance(release['commit'], str) or not SHA.fullmatch(release['commit'])):
                raise ValueError('Invalid selected release.')
            if command == 'install' and not self.status()['available']:
                raise ValueError('No newer version is available.')
            self.working = True
            self.change(phase='checking' if command == 'check' else 'downloading', error=None,
                        message='Checking for updates…' if command == 'check' else 'Preparing the selected update…')

        def task():
            try:
                self.check() if command == 'check' else self.install(release)
            except Exception as error:
                if command == 'check':
                    self.change(lastChecked=now())
                else:
                    self.record(release['tag'][1:], 'failed', 'Update failed before activation or recovery could not finish.')
                self.change(phase='failed', message='The update check failed.' if command == 'check' else 'The update could not be completed.', error=str(error)[-2000:])
            finally:
                with self.lock:
                    self.working = False
        threading.Thread(target=task, daemon=True).start()


def build():
    config = read_json(CONFIG)
    release = read_json(STATE / 'job.json')
    if not TAG.fullmatch(release['tag']) or not SHA.fullmatch(release['commit']):
        raise RuntimeError('Invalid build job.')
    directory = CACHE / 'build/source'
    run(git(config) + ['init', str(directory)])
    run(git(config) + ['-C', str(directory), 'remote', 'add', 'origin', config['repository']])
    run(git(config) + ['-C', str(directory), 'fetch', '--depth=1', 'origin', f'refs/tags/{release["tag"]}'], timeout=180)
    actual = run(git(config) + ['-C', str(directory), 'rev-parse', 'FETCH_HEAD^{commit}']).strip()
    if actual != release['commit']:
        raise RuntimeError('The release tag changed after checking. Refusing to install.')
    run(git(config) + ['-C', str(directory), 'checkout', '--detach', actual])
    if (directory / 'Data').exists() or read_json(directory / 'shared/version.json')['version'] != release['version']:
        raise RuntimeError('Release metadata does not match the selected version.')
    package = read_json(directory / 'package.json')
    if not compatible(read_json(directory / 'shared/update-host.json')):
        raise RuntimeError('This release requires host support or a data migration. Manual maintenance is required.')
    if package.get('packageManager') != 'pnpm@10.18.3':
        raise RuntimeError('This release needs a different package manager. Update host support manually.')
    for args in [['install', '--frozen-lockfile'], ['build']]:
        print(run([config['corepack'], 'pnpm', *args], cwd=directory, timeout=900), flush=True)
    # Verify the actual commit and the canonical version again after executing build scripts.
    if run(git(config) + ['-C', str(directory), 'rev-parse', 'HEAD']).strip() != actual:
        raise RuntimeError('The build changed the release identity.')


def serve():
    # Prevent two coordinators from sharing a transaction or builder.
    handle = open(STATE / 'lock', 'w')
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    manager = Updater(read_json(CONFIG))
    manager.recover()
    uid = pwd.getpwnam('r4os-studio').pw_uid

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(5)
            try:
                _, peer, _ = struct.unpack('3i', self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if peer not in {0, uid}:
                    raise ValueError('Access denied.')
                data = self.rfile.readline(4097)
                if len(data) > 4096 or not data.endswith(b'\n'):
                    raise ValueError('Invalid request.')
                request = json.loads(data)
                if not isinstance(request, dict) or set(request) - {'command', 'release'}:
                    raise ValueError('Invalid request.')
                command = request.get('command')
                if command == 'status':
                    pass
                elif command in {'check', 'install'}:
                    manager.start(command, request.get('release'))
                else:
                    raise ValueError('Unsupported update command.')
                result = {'status': manager.status()}
            except Exception as error:
                result = {'error': str(error), 'code': 409}
            try:
                self.wfile.write((json.dumps(result) + '\n').encode())
            except (BrokenPipeError, TimeoutError):
                pass

    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True
        request_queue_size = 16

    SOCKET.unlink(missing_ok=True)
    with Server(str(SOCKET), Handler) as server:
        os.chown(SOCKET, 0, grp.getgrnam('r4os-studio').gr_gid)
        SOCKET.chmod(0o660)

        def automatic():
            time.sleep(3)
            try:
                manager.start('check')
            except ValueError:
                pass
            while True:
                status = manager.status()
                if not manager.working and (not status['nextCheck'] or datetime.datetime.fromisoformat(status['nextCheck']).timestamp() <= time.time()):
                    try:
                        manager.start('check')
                    except ValueError:
                        pass
                time.sleep(30)
        threading.Thread(target=automatic, daemon=True).start()
        server.serve_forever()


if __name__ == '__main__':
    if sys.argv[1:] == ['build']:
        build()
    elif sys.argv[1:] == ['serve']:
        serve()
    else:
        raise SystemExit('Usage: host.py serve|build')
