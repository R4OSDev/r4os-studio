"""Versioned host tools from official archives; no downloaded installer runs as root."""
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import tempfile
import time

from common import download, publish, read_url, unpack
from service import FOLDERS, digest, now, run

VERSION = re.compile(r'^\d+\.\d+\.\d+$')
QEMU_KEY = 'CEACC9E15534EBABB82D3FA03353C9CEF108B584'


def page(manager, kind, values, older):
    count = len(manager.catalogs.get(kind, {}).get('versions', [])) + 10 if older else 10
    return {'versions': values[:count], 'latestId': values[0]['id'] if values else None, 'hasMore': len(values) > count}


class Zig:
    def catalog(self, manager, kind, older):
        data = json.loads(read_url('https://ziglang.org/download/index.json'))
        values = []
        for version, entry in data.items():
            asset = entry.get('x86_64-linux')
            if VERSION.fullmatch(version) and asset:
                values.append({'id': version, 'version': version, 'sourceUrl': 'https://ziglang.org/download/',
                               'archiveUrl': asset['tarball'], 'sha256': asset['shasum']})
        values.sort(key=lambda item: tuple(map(int, item['version'].split('.'))), reverse=True)
        return page(manager, kind, values, older)

    def install(self, manager, kind, record):
        root = manager.root / FOLDERS[kind]
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.download-', dir=root) as temporary:
            temporary = Path(temporary)
            archive = temporary / 'zig.tar'
            download(manager, record['archiveUrl'], archive, record['sha256'])
            source = unpack(archive, temporary / 'unpacked')
            if run([str(source / 'zig'), 'version']) != record['version']:
                raise ValueError('The downloaded compiler does not match its version.')
            value = {**record, 'binarySha256': digest(source / 'zig'), 'installedAt': now()}
            (source / '.studio-component.json').write_text(json.dumps(value, indent=2) + '\n')
            publish(source, root / value['id'])


def probe_codex(binary, temporary):
    home = temporary / 'probe-home'
    home.mkdir()
    environment = {**os.environ, 'CODEX_HOME': str(home)}
    for key in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'CODEX_ACCESS_TOKEN', 'CODEX_AUTH_JSON', 'CODEX_INTERNAL_ORIGINATOR_OVERRIDE'):
        environment.pop(key, None)
    schemas = temporary / 'schemas'
    run([str(binary), 'app-server', 'generate-json-schema', '--out', str(schemas)], env=environment)
    schema = '\n'.join(path.read_text() for path in schemas.rglob('*.json'))
    required = ('account/login/start', 'account/login/cancel', 'account/read', 'account/rateLimits/read',
                'account/rateLimitResetCredit/consume', 'chatgptDeviceCode')
    if not all(method in schema for method in required):
        raise ValueError('This Codex version does not provide the account protocol required by Studio.')
    process = subprocess.Popen([str(binary), 'app-server', '--listen', 'stdio://', '-c', 'cli_auth_credentials_store="file"'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, bufsize=1, cwd=home, env=environment)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        request = {'id': 1, 'method': 'initialize', 'params': {'clientInfo': {
            'name': 'r4os_studio', 'title': 'R4OS Studio', 'version': json.loads((Path(__file__).resolve().parents[2] / 'shared/version.json').read_text())['version']}, 'capabilities': {'experimentalApi': False}}}
        process.stdin.write(json.dumps(request) + '\n')
        process.stdin.flush()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if not selector.select(1):
                continue
            line = process.stdout.readline(1024 * 1024)
            if not line:
                break
            response = json.loads(line)
            if response.get('id') == 1:
                if 'error' in response or 'result' not in response:
                    break
                return
        raise ValueError('The Codex app-server initialization probe failed.')
    finally:
        selector.close()
        process.terminate()
        try:
            process.wait(5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


class Codex:
    def catalog(self, manager, kind, older):
        release = json.loads(read_url('https://api.github.com/repos/openai/codex/releases/latest'))
        version = release['tag_name'].removeprefix('rust-v')
        if release['draft'] or release['prerelease'] or not VERSION.fullmatch(version):
            raise ValueError('The official Codex stable release is unavailable.')
        asset = next(value for value in release['assets'] if value['name'] == 'codex-x86_64-unknown-linux-musl.tar.gz')
        checksum = asset.get('digest') or ''
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', checksum):
            raise ValueError('The official Codex archive checksum is unavailable.')
        value = {'id': version, 'version': version, 'sourceUrl': release['html_url'],
                 'archiveUrl': asset['browser_download_url'], 'sha256': checksum.removeprefix('sha256:')}
        return {'versions': [value], 'latestId': version, 'hasMore': False}

    def install(self, manager, kind, record):
        if self.catalog(manager, kind, False)['versions'][0] != record:
            raise ValueError('The latest Codex release changed. Check again before downloading.')
        root = manager.root / FOLDERS[kind]
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.download-', dir=root) as temporary:
            temporary = Path(temporary)
            archive = temporary / 'codex.tar'
            download(manager, record['archiveUrl'], archive, record['sha256'])
            unpacked = unpack(archive, temporary / 'unpacked')
            binary = unpacked / 'codex-x86_64-unknown-linux-musl'
            if not binary.is_file():
                binary = unpacked / 'codex'
            if run([str(binary), '--version']) != 'codex-cli ' + record['version']:
                raise ValueError('The downloaded Codex binary does not match its version.')
            manager.progress('Verifying Codex app-server compatibility…', received=0, total=0)
            probe_codex(binary, temporary)
            target = temporary / 'tool'
            target.mkdir()
            shutil.copy2(binary, target / 'codex')
            value = {**record, 'binarySha256': digest(target / 'codex'), 'installedAt': now()}
            (target / '.studio-component.json').write_text(json.dumps(value, indent=2) + '\n')
            publish(target, root / value['id'])


class Qemu:
    def catalog(self, manager, kind, older):
        text = read_url('https://download.qemu.org/').decode()
        versions = set(re.findall(r'href=["\'][^"\']*qemu-(\d+\.\d+\.\d+)\.tar\.xz["\']', text))
        values = [{'id': version, 'version': version, 'sourceUrl': 'https://www.qemu.org/download/',
                   'archiveUrl': f'https://download.qemu.org/qemu-{version}.tar.xz',
                   'signatureUrl': f'https://download.qemu.org/qemu-{version}.tar.xz.sig'}
                  for version in sorted(versions, key=lambda version: tuple(map(int, version.split('.'))), reverse=True)]
        return page(manager, kind, values, older)

    def install(self, manager, kind, record):
        for binary in ('cc', 'c++', 'ninja', 'meson', 'pkg-config', 'gpg'):
            if not shutil.which(binary):
                raise ValueError(f'QEMU source builds require {binary}. Install the documented host build prerequisites first.')
        run(['pkg-config', '--print-errors', '--exists', 'glib-2.0', 'pixman-1', 'slirp', 'zlib', 'libpng'])
        root = manager.root / FOLDERS[kind]
        root.mkdir(parents=True, exist_ok=True)
        destination = root / record['id']
        # QEMU rejects spaces/colons in its source and build directory. The data
        # root may contain either; use the service's private /tmp for the build.
        with tempfile.TemporaryDirectory(prefix='r4os-qemu-', dir='/tmp') as temporary:
            temporary = Path(temporary)
            archive = temporary / 'qemu.tar.xz'
            archive_hash = download(manager, record['archiveUrl'], archive)
            signature = temporary / 'qemu.tar.xz.sig'
            signature.write_bytes(read_url(record['signatureUrl'], 65536))
            key = temporary / 'release-key.asc'
            key.write_bytes(read_url('https://keys.openpgp.org/vks/v1/by-fingerprint/' + QEMU_KEY, 1024 * 1024))
            home = temporary / 'gpg'
            home.mkdir(mode=0o700)
            run(['gpg', '--batch', '--no-autostart', '--homedir', str(home), '--import', str(key)])
            fingerprints = run(['gpg', '--batch', '--homedir', str(home), '--with-colons', '--fingerprint']).splitlines()
            if next((line.split(':')[9] for line in fingerprints if line.startswith('fpr:')), None) != QEMU_KEY:
                raise ValueError('The QEMU release signing key has an unexpected fingerprint.')
            verified = run(['gpg', '--batch', '--homedir', str(home), '--status-fd', '1', '--verify', str(signature), str(archive)])
            signatures = [line.split() for line in verified.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
            if not any(line[2] == QEMU_KEY or line[-1] == QEMU_KEY for line in signatures):
                raise ValueError('The archive was not signed by the pinned QEMU release key.')
            manager.progress('Building the signature-verified QEMU source…', received=0, total=0)
            # Upstream's unused EDK2 host-emulator helper links to /usr/include.
            # Keep tar's data filter; this firmware-source helper is not built here.
            omitted = ('roms/edk2/EmulatorPkg/Unix/Host/X11IncludeHack',)
            source = unpack(archive, temporary / 'source', exclude=omitted)
            build = temporary / 'build'
            build.mkdir()
            arguments = ['--prefix=' + str(destination), '--target-list=x86_64-softmmu', '--disable-docs',
                         '--disable-guest-agent', '--disable-gtk', '--disable-sdl', '--disable-user',
                         '--disable-plugins', '--disable-werror', '--enable-slirp', '--enable-vnc', '--enable-png', '--disable-download']
            run([str(source / 'configure'), *arguments], cwd=build, timeout=300)
            run(['ninja', '-j', str(min(8, os.cpu_count() or 2))], cwd=build, timeout=1800)
            manager.progress('Installing and verifying the QEMU tool pair…')
            staging = temporary / 'install'
            run(['ninja', 'install'], cwd=build, timeout=180, env={**os.environ, 'DESTDIR': str(staging)})
            target = staging / str(destination).lstrip('/')
            binary, image_binary = target / 'bin/qemu-system-x86_64', target / 'bin/qemu-img'
            if not all(record['version'] in run([str(value), '--version']) for value in (binary, image_binary)):
                raise ValueError('The QEMU tool pair does not match its version.')
            provenance = target / 'Sources'
            provenance.mkdir()
            for path in (archive, signature, key):
                shutil.copy2(path, provenance / path.name)
            for name in ('COPYING', 'COPYING.LIB'):
                if (source / name).is_file():
                    shutil.copy2(source / name, provenance / name)
            value = {**record, 'sha256': archive_hash, 'signatureKey': QEMU_KEY, 'installedAt': now(),
                     'binarySha256': digest(binary), 'imageBinarySha256': digest(image_binary), 'buildArguments': arguments,
                     'omittedBuildLinks': omitted}
            (target / '.studio-component.json').write_text(json.dumps(value, indent=2) + '\n')
            # /tmp may be another filesystem. Copy to a private data-side stage
            # before the final rename so no partial installation becomes visible.
            with tempfile.TemporaryDirectory(prefix='.publish-', dir=root) as publication:
                staged = Path(publication) / 'tool'
                shutil.copytree(target, staged, symlinks=True)
                publish(staged, destination)
