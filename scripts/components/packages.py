"""Official R4OS package versions, pinned to exact Git revisions and Zig package hashes."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from common import download, publish, unpack
from service import FOLDERS, now, package_info, parse_package_info, run


def git(repository, *arguments, timeout=180):
    environment = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
                   'GIT_TERMINAL_PROMPT': '0', 'GIT_ASKPASS': '/bin/false'}
    return run(['/usr/bin/git', '-c', 'credential.helper=', '-c', 'core.hooksPath=/dev/null',
                '-c', 'protocol.file.allow=never', '-c', 'http.sslVerify=true', '-C', str(repository),
                *arguments], timeout=timeout, env=environment)


def source_repository(manager, kind):
    directory = manager.root / 'Profiles/Sources' / (kind + '.git')
    url = f'https://github.com/R4OSDev/r4os-{kind}.git'
    if directory.is_symlink():
        raise ValueError('Invalid source cache.')
    if not directory.exists():
        directory.parent.mkdir(parents=True, exist_ok=True)
        directory.mkdir()
        git(directory, 'init', '--bare')
        git(directory, 'remote', 'add', 'origin', url)
    if git(directory, 'remote', 'get-url', 'origin') != url:
        raise ValueError('The cached source repository has an unexpected origin.')
    manager.progress(f'Reading official {kind} version history…')
    git(directory, 'fetch', '--filter=blob:none', 'origin', '+refs/heads/main:refs/remotes/origin/main')
    return directory


def record(repository, kind, revision):
    if not re.fullmatch('[a-f0-9]{40}', revision):
        raise ValueError('Invalid official source revision.')
    metadata = git(repository, 'show', revision + ':build.zig.zon')
    info = parse_package_info(metadata)
    return {**info, 'id': revision, 'revision': revision,
            'sourceUrl': f'https://github.com/R4OSDev/r4os-{kind}/tree/{revision}',
            'archiveUrl': f'https://codeload.github.com/R4OSDev/r4os-{kind}/tar.gz/{revision}',
            'metadataHash': hashlib.sha256(metadata.encode()).hexdigest()}


class PackageAdapter:
    def catalog(self, manager, kind, older):
        directory = source_repository(manager, kind)
        head = git(directory, 'rev-parse', 'refs/remotes/origin/main')
        history = git(directory, 'log', '--format=%H', 'refs/remotes/origin/main', '--', 'build.zig.zon').splitlines()
        previous = manager.catalogs.get(kind, {}).get('versions', [])
        limit = len(previous) + 10 if older else 10
        limit = min(limit, 200)
        values, versions = [], set()
        for revision in dict.fromkeys([head, *history]):
            try:
                value = record(directory, kind, revision)
            except ValueError:
                continue
            if value['version'] not in versions:
                values.append(value)
                versions.add(value['version'])
            if len(values) > limit:
                break
        more = len(values) > limit
        values = values[:limit]
        latest = values[0]['id'] if values else None
        if kind == 'contract':
            # SDK pins can refer to another revision with the same package version.
            sdks = manager.installed('sdk') + manager.catalogs.get('sdk', {}).get('versions', [])
            pins = {sdk.get('dependencies', {}).get('contract', {}).get('revision') for sdk in sdks}
            for revision in sorted(value for value in pins if value):
                if any(value['id'] == revision for value in values):
                    continue
                try:
                    value = record(directory, kind, revision)
                except ValueError:
                    git(directory, 'fetch', 'origin', revision)
                    value = record(directory, kind, revision)
                values.append(value)
        return {'versions': values, 'latestId': latest, 'hasMore': more}

    def install(self, manager, kind, selected):
        directory = source_repository(manager, kind)
        value = record(directory, kind, selected['revision'])
        if value != selected:
            raise ValueError('Package metadata changed. Check versions again.')
        root = manager.root / FOLDERS[kind]
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.download-', dir=root) as temporary:
            temporary = Path(temporary)
            archive = temporary / 'package.tar'
            archive_hash = download(manager, value['archiveUrl'], archive)
            source = unpack(archive, temporary / 'unpacked')
            metadata = (source / 'build.zig.zon').read_text().strip()
            if hashlib.sha256(metadata.encode()).hexdigest() != value['metadataHash']:
                raise ValueError('Archive metadata does not match its official source revision.')
            actual_info = package_info(source)
            if actual_info['version'] != value['version']:
                raise ValueError('Package version does not match its selected revision.')
            minimum = value.get('minZigVersion')
            compiler = next((item for item in manager.installed('zig') if item['version'] == minimum), None)
            if not compiler:
                raise ValueError(f'Download Zig {minimum} before verifying this package.')
            verification = temporary / 'verify'
            verification.mkdir()
            (verification / 'build.zig').write_text('pub fn build(_: *@import("std").Build) void {}\n')
            manager.progress('Verifying the Zig package contents…', received=0, total=0)
            hashed = run([compiler['binary'], 'fetch', '--global-cache-dir', str(verification / 'cache'), str(source)], cwd=verification)
            if not re.fullmatch(r'[a-zA-Z0-9_.+-]+', hashed):
                raise ValueError('The compiler returned an invalid package hash.')
            if kind == 'contract':
                for sdk in manager.installed('sdk') + manager.catalogs.get('sdk', {}).get('versions', []):
                    pin = sdk.get('dependencies', {}).get('contract')
                    if pin and pin['revision'] == value['revision'] and pin['packageHash'] != hashed:
                        raise ValueError('Contract contents do not match the SDK package pin.')
            value.update(sha256=archive_hash, packageHash=hashed, installedAt=now())
            (source / '.studio-component.json').write_text(json.dumps(value, indent=2) + '\n')
            publish(source, root / value['id'])


ADAPTER = PackageAdapter()
