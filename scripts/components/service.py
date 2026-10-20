#!/usr/bin/env python3
"""Unprivileged component manager. The web process only accesses a bounded socket API."""
import argparse
import copy
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import stat
import struct
import subprocess
import sys
import threading
import time

KINDS = ('sdk', 'contract', 'libraries', 'zig', 'qemu', 'codex', 'r4os')
FOLDERS = {'sdk': 'SDK', 'contract': 'Contract', 'libraries': 'Libraries',
           'zig': 'Toolchains/Zig', 'qemu': 'Toolchains/QEMU', 'codex': 'Toolchains/Codex', 'r4os': 'Images'}
IDENTITY = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.+-]{0,127}$')


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def atomic(path, value):
    path = Path(path)
    temp = path.with_name('.' + path.name + '.tmp')
    with temp.open('w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(args, timeout=60, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kwargs)
    if result.returncode:
        raise ValueError(f'{Path(args[0]).name} failed: {(result.stderr or result.stdout)[-1500:]}')
    return result.stdout.strip()


def package_info(path):
    return parse_package_info((Path(path) / 'build.zig.zon').read_text())


def parse_package_info(text):
    version = re.search(r'\.version\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', text)
    if not version:
        raise ValueError('Package version is missing.')
    result = {'version': version[1]}
    minimum = re.search(r'\.minimum_zig_version\s*=\s*"([^"]+)"', text)
    if minimum:
        result['minZigVersion'] = minimum[1]
    dependency = re.search(r'\.r4os_contract\s*=\s*\.\{(.*?)\}', text, re.S)
    if dependency:
        revision = re.search(r'/([a-f0-9]{40})(?:\.tar\.gz|["/])', dependency[1])
        package_hash = re.search(r'\.hash\s*=\s*"([^"]+)"', dependency[1])
        if not revision or not package_hash:
            raise ValueError('The SDK contract pin could not be verified.')
        result['dependencies'] = {'contract': {'revision': revision[1], 'packageHash': package_hash[1]}}
    return result


def public(record):
    return {key: value for key, value in record.items() if key not in ('directory', 'binary', 'imageBinary', 'archiveUrl', 'size', 'signatureUrl', 'metadataHash')}


class Manager:
    def __init__(self, root, external=None, adapters=None):
        self.root = Path(root).resolve()
        self.external = external or {}
        self.adapters = adapters or {}
        self.lock = threading.RLock()
        self.busy = False
        self.job = None
        self.catalogs = {}
        self.profile = self.root / 'Profiles/versions.json'
        self.root.joinpath('Profiles').mkdir(parents=True, exist_ok=True)
        self.state = json.loads(self.profile.read_text()) if self.profile.exists() else {'schema': 1, 'defaults': {}}
        if self.state.get('schema') != 1:
            raise ValueError('Unsupported component profile schema.')
        if not self.profile.exists():
            for kind in KINDS:
                installed = self.installed(kind)
                if installed:
                    self.state['defaults'][kind] = installed[0]
            atomic(self.profile, self.state)

    def installed(self, kind):
        records = []
        folder = self.root / FOLDERS[kind]
        if folder.is_dir():
            for path in folder.iterdir():
                if path.name.startswith('.') or path.is_symlink() or not path.is_dir():
                    continue
                marker = path / ('image.json' if kind == 'r4os' else '.studio-component.json')
                if not marker.is_file() or marker.is_symlink():
                    continue
                try:
                    record = json.loads(marker.read_text())
                    if kind == 'r4os':
                        if record.get('variant') != 'full' or record.get('architecture') != 'x86_64' or not (path / 'disk.img').is_file():
                            continue
                    elif kind in ('sdk', 'contract', 'libraries'):
                        record.update(package_info(path))
                        if record.get('zigPackageHash'):
                            record['packageHash'] = record['zigPackageHash']
                    if not re.fullmatch(r'\d+\.\d+\.\d+', record['version']):
                        continue
                    record.update(id=path.name, directory=str(path))
                    if kind == 'zig':
                        record['binary'] = str(path / 'zig')
                    elif kind in ('qemu', 'codex'):
                        binary = path / ('bin/qemu-system-x86_64' if kind == 'qemu' else 'codex')
                        if not binary.is_file():
                            continue
                        record['binary'] = str(binary)
                        if kind == 'qemu':
                            record['imageBinary'] = str(path / 'bin/qemu-img')
                    records.append(record)
                except (OSError, ValueError, KeyError):
                    continue
        if kind in self.external:
            record = self.external[kind]
            try:
                info = Path(record['binary']).stat()
                if info.st_size == record['binarySize'] and info.st_mtime_ns == record['binaryMtimeNs']:
                    records.append(record)
            except OSError:
                pass
        return sorted(records, key=lambda record: tuple(map(int, record['version'].split('.'))), reverse=True)

    def status(self):
        with self.lock:
            components = {}
            for kind in KINDS:
                catalog = self.catalogs.get(kind, {})
                active = self.state['defaults'].get(kind)
                installed = self.installed(kind)
                components[kind] = {'installed': [public(record) for record in installed],
                                    'available': [public(record) for record in catalog.get('versions', [])],
                                    'activeId': active['id'] if active else None,
                                    'latestId': catalog.get('latestId'), 'checkedAt': catalog.get('checkedAt'),
                                    'error': catalog.get('error'), 'hasMore': catalog.get('hasMore', False)}
            return {'enabled': True, 'components': components, 'job': copy.deepcopy(self.job),
                    'message': 'Downloads and active defaults are managed independently.'}

    def progress(self, message, **values):
        with self.lock:
            self.job.update(message=message, **values)

    def start(self, kind, action, identity=None, older=False):
        if kind not in KINDS or action not in ('check', 'download'):
            raise ValueError('Unsupported component action.')
        if identity is not None and not IDENTITY.fullmatch(identity):
            raise ValueError('Invalid version identity.')
        with self.lock:
            if self.busy:
                raise ValueError('Another component operation is already running.')
            if kind not in self.adapters:
                raise ValueError('The version source for this component is not available in this release.')
            self.busy = True
            self.job = {'kind': kind, 'action': action, 'phase': 'working', 'message': 'Preparing…', 'error': None}
            thread = threading.Thread(target=self.work, args=(kind, action, identity, older), daemon=True)
            thread.start()
        return self.status()

    def work(self, kind, action, identity, older):
        try:
            adapter = self.adapters[kind]
            if action == 'check':
                self.progress('Checking official versions…')
                catalog = adapter.catalog(self, kind, older)
                with self.lock:
                    self.catalogs[kind] = {**catalog, 'checkedAt': now(), 'error': None}
            else:
                catalog = self.catalogs.get(kind, {})
                record = next((value for value in catalog.get('versions', []) if value['id'] == identity), None)
                if not record:
                    raise ValueError('Check the official version list before downloading this version.')
                if kind == 'codex':
                    latest = adapter.catalog(self, kind, False)
                    if latest['latestId'] != identity:
                        raise ValueError('Only the latest Codex version can be downloaded. Check again.')
                if not any(value['id'] == identity for value in self.installed(kind)):
                    adapter.install(self, kind, record)
            self.progress('Version check complete.' if action == 'check' else 'Download verified and installed. Choose a default separately.', phase='complete')
        except Exception as error:
            message = str(error)[:1600]
            with self.lock:
                if action == 'check':
                    self.catalogs.setdefault(kind, {})['error'] = message
                self.job.update(phase='failed', message='The component operation failed. Existing versions were kept.', error=message)
        finally:
            with self.lock:
                self.busy = False

    def set_default(self, kind, identity):
        if kind not in KINDS or not IDENTITY.fullmatch(identity):
            raise ValueError('Invalid component version.')
        with self.lock:
            if self.busy:
                raise ValueError('Wait for the current component operation to finish.')
            record = next((value for value in self.installed(kind) if value['id'] == identity), None)
            if not record:
                raise ValueError('Only a complete local installation can be selected as default.')
            defaults = copy.deepcopy(self.state['defaults'])
            defaults[kind] = record
            if kind == 'sdk' and record.get('dependencies', {}).get('contract'):
                pin = record['dependencies']['contract']
                contract = next((value for value in self.installed('contract') if value.get('revision', value['id']) == pin['revision']), None)
                if not contract or contract.get('packageHash') != pin['packageHash']:
                    raise ValueError('Download the exact Contract required by this SDK before activating it.')
                defaults['contract'] = contract
                required = record.get('minZigVersion')
                compiler = next((value for value in self.installed('zig') if value['version'] == required), None)
                if required and not compiler:
                    raise ValueError(f'Download Zig {required} before selecting this SDK.')
                if compiler:
                    defaults['zig'] = compiler
            sdk = defaults.get('sdk', {})
            contract = defaults.get('contract', {})
            pin = sdk.get('dependencies', {}).get('contract')
            if kind in ('sdk', 'contract', 'zig'):
                if pin and (contract.get('revision', contract.get('id')) != pin['revision'] or contract.get('packageHash') != pin['packageHash']):
                    raise ValueError('This Contract does not match the active SDK. Select the matching SDK instead.')
                required = sdk.get('minZigVersion')
                if required and defaults.get('zig', {}).get('version') != required:
                    raise ValueError(f'This SDK requires the verified Zig {required} profile. Download and select the matching compiler first.')
            next_state = {'schema': 1, 'defaults': defaults, 'updatedAt': now()}
            atomic(self.profile, next_state)
            self.state = next_state
        return self.status()


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        uid = struct.unpack('3i', self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
        if uid not in (self.server.allowed_uid, 0):
            return
        self.request.settimeout(5)
        try:
            line = self.rfile.readline(4097)
            if len(line) > 4096 or not line.endswith(b'\n'):
                raise ValueError('Invalid component request.')
            request = json.loads(line)
            allowed = {'command', 'kind', 'id', 'older'}
            if not isinstance(request, dict) or set(request) - allowed:
                raise ValueError('Unsupported component request.')
            command = request.get('command')
            manager = self.server.manager
            if command == 'status' and set(request) == {'command'}:
                result = manager.status()
            elif command == 'default' and set(request) == {'command', 'kind', 'id'}:
                result = manager.set_default(request['kind'], request['id'])
            elif command in ('check', 'download') and request.get('kind') in KINDS:
                if command == 'check' and set(request) <= {'command', 'kind', 'older'} and isinstance(request.get('older', False), bool):
                    result = manager.start(request['kind'], command, older=request.get('older', False))
                elif command == 'download' and set(request) == {'command', 'kind', 'id'} and isinstance(request.get('id'), str):
                    result = manager.start(request['kind'], command, request['id'])
                else:
                    raise ValueError('Unsupported component request.')
            else:
                raise ValueError('Unsupported component command.')
            response = {'status': result}
        except (ValueError, TypeError) as error:
            response = {'error': str(error), 'code': 409}
        except Exception:
            response = {'error': 'Component host operation failed. Check the host service log.', 'code': 503}
        self.wfile.write((json.dumps(response) + '\n').encode())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='/etc/r4os-studio-components/config.json')
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    os.umask(0o077)
    from sources import ADAPTERS
    manager = Manager(config['root'], config.get('external'), ADAPTERS)
    lock = (manager.root / 'Profiles/.components.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    # Follow a completed Studio release switch only between jobs. No root code is replaced.
    release = Path(__file__).resolve().parents[2]
    def follow_release():
        if not release.is_relative_to('/opt/r4os-studio/releases'):
            return
        while True:
            time.sleep(3)
            selected = Path('/opt/r4os-studio/current').resolve()
            with manager.lock:
                if not manager.busy and selected != release and (selected / 'scripts/components/service.py').is_file():
                    os.execv(sys.executable, [sys.executable, '-B', '/opt/r4os-studio/bin/components-launch.py'])
    threading.Thread(target=follow_release, daemon=True).start()
    path = Path('/run/r4os-studio-components/control.sock')
    if path.exists():
        if not stat.S_ISSOCK(path.lstat().st_mode):
            raise ValueError('Component socket path is not a socket.')
        path.unlink()
    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True
    with Server(str(path), Handler) as server:
        server.manager = manager
        server.allowed_uid = config['uid']
        path.chmod(0o600)
        server.serve_forever()


if __name__ == '__main__':
    main()
