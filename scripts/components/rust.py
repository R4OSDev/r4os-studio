"""Official Rust component archives, isolated from host rustup and project SDK support."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib
import urllib.parse

from common import download, publish, read_url, safe_url, unpack
from service import FOLDERS, digest, now

HOST = 'x86_64-unknown-linux-gnu'
TARGET = 'x86_64-unknown-none'
VERSION = re.compile(r'^\d+\.\d+\.\d+$')
BASE = 'https://static.rust-lang.org/dist/'


def manifest(version):
    if version != 'stable' and not VERSION.fullmatch(version):
        raise ValueError('Invalid Rust version.')
    url = BASE + 'channel-rust-' + version + '.toml'
    data = read_url(url)
    expected = read_url(url + '.sha256', 1024).decode().split()[0]
    if not re.fullmatch('[a-f0-9]{64}', expected) or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('The Rust manifest SHA-256 does not match its published checksum.')
    value = tomllib.loads(data.decode())
    if value.get('manifest-version') != '2':
        raise ValueError('Unsupported official Rust manifest format.')
    actual = value['pkg']['rust']['version'].split()[0]
    if not VERSION.fullmatch(actual) or (version != 'stable' and actual != version):
        raise ValueError('The Rust release does not match the requested version.')
    return value, data, expected, url


def release(version):
    value, _, checksum, url = manifest(version)
    archives = []
    for component, target in (('rustc', HOST), ('cargo', HOST), ('rust-std', HOST), ('rust-std', TARGET)):
        item = value['pkg'][component]['target'][target]
        source = item.get('xz_url', '')
        if (not item.get('available') or not re.fullmatch('[a-f0-9]{64}', item.get('xz_hash', ''))
                or urllib.parse.urlparse(safe_url(source)).hostname != 'static.rust-lang.org'
                or not urllib.parse.urlparse(source).path.startswith('/dist/')):
            raise ValueError('A required official Rust component is unavailable.')
        archives.append({'component': component, 'target': target, 'archiveUrl': source, 'sha256': item['xz_hash']})
    return {'id': version, 'version': version, 'sourceUrl': 'https://www.rust-lang.org/tools/install',
            'manifestUrl': url, 'sha256': checksum, 'manifestSha256': checksum,
            'date': value['date'], 'host': HOST, 'targets': [TARGET], 'archives': archives,
            'compilerSourceVersion': value['pkg']['rustc']['version'], 'cargoSourceVersion': value['pkg']['cargo']['version']}


def environment(prefix, work):
    return {'PATH': str(prefix / 'bin') + ':/usr/bin:/bin', 'LANG': 'C.UTF-8',
            'HOME': str(work / 'home'), 'CARGO_HOME': str(work / 'cargo-home'),
            'RUSTUP_HOME': str(work / 'rustup-home'), 'RUSTC': str(prefix / 'bin/rustc'), 'CARGO_NET_OFFLINE': 'true'}


def command(args, env, cwd, timeout=90):
    result = subprocess.run([str(a) for a in args], env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError('Rust toolchain verification failed: ' + (result.stderr or result.stdout)[-1200:])
    return result.stdout.strip()


def verify_installation(prefix, record):
    prefix = Path(prefix)
    expected = record.get('fileHashes')
    if not expected or not all(path in expected for path in ('bin/rustc', 'bin/cargo', record.get('linker', ''))):
        raise ValueError('The Rust installation has no verified compiler/component inventory.')
    if not any(path.startswith('lib/rustlib/' + TARGET + '/lib/libcore-') and path.endswith('.rlib') for path in expected):
        raise ValueError('The Rust target component is missing from the verified inventory.')
    for relative, checksum in expected.items():
        path = prefix / relative
        if (Path(relative).is_absolute() or '..' in Path(relative).parts or not path.is_file()
                or not path.resolve().is_relative_to(prefix.resolve()) or digest(path) != checksum):
            raise ValueError('The Rust installation checksum changed. Choose a verified installation.')
    if not (prefix / 'lib/rustlib' / TARGET / 'lib').is_dir():
        raise ValueError('The Rust target component is missing.')
    saved_manifest = prefix / 'release/channel.toml'
    if not saved_manifest.is_file() or digest(saved_manifest) != record.get('manifestSha256') or record.get('sha256') != record.get('manifestSha256'):
        raise ValueError('The saved Rust manifest checksum changed.')
    for relative, target in record.get('symlinks', {}).items():
        path = prefix / relative
        if Path(relative).is_absolute() or '..' in Path(relative).parts or not path.is_symlink() or os.readlink(path) != target or not path.resolve().is_relative_to(prefix.resolve()):
            raise ValueError('A Rust component link changed.')


class Rust:
    def catalog(self, manager, kind, older):
        stable, _, _, _ = manifest('stable')
        latest = stable['pkg']['rust']['version'].split()[0]
        count = len(manager.catalogs.get(kind, {}).get('versions', [])) + 10 if older else 1
        tags = json.loads(read_url('https://api.github.com/repos/rust-lang/rust/releases?per_page=100'))
        versions = {entry['tag_name'] for entry in tags if not entry['draft'] and not entry['prerelease'] and VERSION.fullmatch(entry['tag_name'])}
        versions.add(latest)
        newest = tuple(map(int, latest.split('.')))
        versions = sorted((v for v in versions if tuple(map(int, v.split('.'))) <= newest), key=lambda v: tuple(map(int, v.split('.'))), reverse=True)
        values = []
        for version in versions[:count]:
            manager.progress('Checking official Rust ' + version + '…')
            values.append(release(version))
        from rust_sdk import record as sdk_record, for_sdk
        selected = manager.state['defaults'].get('sdk')
        if selected:
            sdk = sdk_record(for_sdk(selected)); values.append(sdk)
        return {'versions': values, 'latestId': latest, 'hasMore': len(versions) > count}

    def install(self, manager, kind, record):
        from rust_sdk import record as sdk_record, install as install_sdk, for_sdk
        if record['id'].startswith('sdk-'):
            sdk = next((v for v in manager.installed('sdk') if v['version'] == record['sdkVersion']), None)
            if not sdk: raise ValueError('Install the matching SDK before its Rust toolchain.')
            spec = for_sdk(sdk)
            if record != sdk_record(spec): raise ValueError('The SDK Rust release profile changed. Check for updates again.')
            return install_sdk(manager, spec)
        # Re-read the immutable release manifest before trusting saved catalog URLs.
        verified = release(record['version'])
        if verified != record:
            raise ValueError('The official Rust release metadata changed. Check for updates again.')
        root = manager.root / FOLDERS[kind]
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.download-', dir=root) as temporary, tempfile.TemporaryDirectory(prefix='r4os-rust-', dir='/tmp') as scratch_directory:
            work = Path(temporary)
            scratch = Path(scratch_directory)
            # The official shell installer splits prefixes containing spaces.
            # Final binaries are relocatable; publish from the data filesystem.
            prefix = scratch / 'installed'
            prefix.mkdir()
            env = environment(prefix, scratch)
            for index, item in enumerate(record['archives']):
                archive = work / f'component-{index}.tar.xz'
                download(manager, item['archiveUrl'], archive, item['sha256'])
                extraction = scratch / f'component-{index}'
                source = unpack(archive, extraction)
                installer = source / 'install.sh'
                if not installer.is_file() or not installer.resolve().is_relative_to(source.resolve()):
                    raise ValueError('The official Rust component installer is missing.')
                manager.progress('Installing ' + item['component'] + ' (' + item['target'] + ')…')
                command(['/bin/sh', installer, '--prefix=' + str(prefix), '--disable-ldconfig'], env, source)
                archive.unlink()
                shutil.rmtree(extraction)
            compiler = command([prefix / 'bin/rustc', '--version', '--verbose'], env, work)
            cargo = command([prefix / 'bin/cargo', '--version'], env, work)
            if not compiler.startswith('rustc ' + record['version'] + ' '):
                raise ValueError('The Rust compiler version does not match the release.')
            for actual, source in ((compiler, record['compilerSourceVersion']), (cargo, record['cargoSourceVersion'])):
                match = re.search(r'\(([a-f0-9]{7,40}) ', source)
                if not match or match[1] not in actual:
                    raise ValueError('The Rust component build does not match its official manifest.')
            target = Path(command([prefix / 'bin/rustc', '--print', 'target-libdir', '--target', TARGET], env, work))
            if not target.is_relative_to(prefix) or not list(target.glob('libcore-*.rlib')):
                raise ValueError('The required Rust target libraries are missing.')
            linker = Path('lib/rustlib') / HOST / 'bin/rust-lld'
            if not (prefix / linker).is_file():
                raise ValueError('The bundled Rust linker is missing.')
            command([prefix / linker, '-flavor', 'gnu', '--version'], env, work)
            sample = work / 'probe.rs'
            sample.write_text('#![no_std]\npub fn studio_toolchain_probe(value: u64) -> u64 { value.wrapping_add(1) }\n')
            command([prefix / 'bin/rustc', '--crate-name', 'studio_toolchain_probe', '--crate-type', 'lib',
                     '--target', TARGET, '--emit=obj', sample, '-o', work / 'probe.o'], env, work)
            release_folder = prefix / 'release'
            release_folder.mkdir()
            _, raw, checksum, _ = manifest(record['version'])
            (release_folder / 'channel.toml').write_bytes(raw)
            (release_folder / 'channel.toml.sha256').write_text(checksum + '\n')
            files = {str(path.relative_to(prefix)): digest(path) for path in prefix.rglob('*')
                     if path.is_file() and not path.is_symlink()}
            symlinks = {str(path.relative_to(prefix)): os.readlink(path) for path in prefix.rglob('*') if path.is_symlink()}
            # Include a safe bundled-linker symlink as an explicit verified input too.
            files[str(linker)] = digest(prefix / linker)
            value = {**record, 'installedAt': now(), 'cargoVersion': cargo.split()[1],
                     'binarySha256': files['bin/rustc'], 'cargoSha256': files['bin/cargo'],
                     'linker': str(linker), 'fileHashes': files, 'symlinks': symlinks, 'installationMethod': 'official-components'}
            verify_installation(prefix, value)
            (prefix / '.studio-component.json').write_text(json.dumps(value, indent=2) + '\n')
            staged = work / 'installed'
            shutil.copytree(prefix, staged, symlinks=True)
            verify_installation(staged, value)
            relocated = environment(staged, scratch)
            command([staged / 'bin/rustc', '--version'], relocated, scratch)
            command([staged / 'bin/cargo', '--version'], relocated, scratch)
            command([staged / 'bin/rustc', '--crate-name', 'studio_toolchain_probe', '--crate-type', 'lib',
                     '--target', TARGET, '--emit=obj', sample, '-o', work / 'relocated-probe.o'], relocated, scratch)
            publish(staged, root / record['id'])
