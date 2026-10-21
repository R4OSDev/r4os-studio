"""Matched official SDK tools and an isolated, SDK-checked Rust installation."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

from common import download, publish, read_url, unpack

SPEC = json.loads((Path(__file__).resolve().parents[2] / 'shared/r4os/rust-sdk.json').read_text())
COMPILER = 'Install/Toolchains/Rust/rustup/toolchains/1.99.0-x86_64-unknown-linux-gnu/bin/rustc'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record():
    release = SPEC['release']
    return {'id': SPEC['id'], 'version': SPEC['version'], 'cargoVersion': SPEC['version'],
            'toolchainProfile': 'r4os-sdk', 'sdkVersion': release['sdk']['package_version'],
            'sdkRevision': release['sdk']['source_commit'], 'host': 'x86_64-unknown-linux-gnu',
            'targets': ['x86_64-unknown-none'], 'sha256': SPEC['releaseSha256'],
            'sourceUrl': SPEC['releaseUrl'], 'manifestSha256': release['devkit']['profile_sha256']}


def environment(prefix, work):
    return {'PATH': str(prefix / 'PowerShell') + ':/usr/bin:/bin', 'LANG': 'C.UTF-8',
            'HOME': str(work), 'DOTNET_CLI_TELEMETRY_OPTOUT': '1', 'POWERSHELL_TELEMETRY_OPTOUT': '1'}


def command(args, env, cwd, timeout=120):
    result = subprocess.run([str(a) for a in args], cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError('SDK Rust tools failed: ' + (result.stderr or result.stdout)[-1600:])
    return result.stdout.strip()


def verify_files(prefix, values):
    for relative, checksum in values.items():
        path = prefix / relative
        if (Path(relative).is_absolute() or '..' in Path(relative).parts or not path.is_file()
                or not path.resolve().is_relative_to(prefix.resolve()) or digest(path) != checksum):
            raise ValueError('The SDK Rust toolchain checksum changed. Choose a verified installation.')


def verify(prefix, value):
    prefix = Path(prefix)
    if any(value.get(key) != expected for key, expected in record().items()):
        raise ValueError('The SDK Rust profile identity changed.')
    files = value.get('fileHashes', {})
    if not all(path in files for path in (COMPILER, 'PowerShell/pwsh', 'Tools/RustToolsProfile.json')):
        raise ValueError('The SDK Rust installation is incomplete.')
    toolchain = prefix / Path(COMPILER).parent.parent
    required = [(prefix / COMPILER, 'the Rust compiler'), (toolchain / 'bin/cargo', 'Cargo'),
                (prefix / 'PowerShell/pwsh', 'the PowerShell runner'),
                (prefix / 'Tools/bin/x86_64-unknown-linux-gnu/module-catalog', 'the SDK capability tool')]
    required += [(toolchain / 'lib/rustlib/x86_64-unknown-linux-gnu/bin' / name, 'required LLVM tools')
                 for name in ('rust-lld', 'llvm-readobj', 'llvm-objdump', 'llvm-objcopy', 'llvm-nm', 'llvm-size')]
    for path, label in required:
        if not path.is_file():
            raise ValueError('The SDK Rust toolchain is missing ' + label + '.')
    if not list((toolchain / 'lib/rustlib/x86_64-unknown-none/lib').glob('libcore-*.rlib')):
        raise ValueError('The SDK Rust toolchain is missing target libraries.')
    verify_files(prefix, files)
    for relative, target in value.get('symlinks', {}).items():
        path = prefix / relative
        if (Path(relative).is_absolute() or '..' in Path(relative).parts or not path.is_symlink()
                or os.readlink(path) != target or not path.resolve().is_relative_to(prefix.resolve())):
            raise ValueError('An SDK Rust component link changed.')


def install(manager):
    from service import now, atomic
    release = SPEC['release']
    raw = read_url(SPEC['releaseUrl'])
    if hashlib.sha256(raw).hexdigest() != SPEC['releaseSha256']:
        raise ValueError('The published SDK release manifest changed.')
    root = manager.root / 'Toolchains/Rust'
    root.mkdir(parents=True, exist_ok=True)
    pending = {'schema': 1, 'owner': 'R4OS Studio', 'id': SPEC['id'], 'releaseSha256': SPEC['releaseSha256']}
    destination = root / SPEC['id']
    if destination.is_symlink():
        raise ValueError('An existing SDK Rust directory was preserved.')
    if destination.exists():
        marker = destination / '.studio-installing.json'
        if ((destination / '.studio-component.json').exists() or not marker.is_file()
                or json.loads(marker.read_text()) != pending):
            raise ValueError('An existing SDK Rust directory was preserved. Select a verified installation.')
        destination.rename(root / ('.incomplete-' + SPEC['id'] + '-' + uuid.uuid4().hex))
    with tempfile.TemporaryDirectory(prefix='.sdk-download-', dir=root) as temporary:
        work = Path(temporary)
        prefix = work / 'installed'
        prefix.mkdir()
        for key, name in (('devkit', 'Tools'), ('capabilities', 'capabilities.json')):
            item = release[key]['package']
            archive = work / item['file']
            download(manager, item['url'], archive, item['sha256'], limit=64 * 1024**2)
            if key == 'devkit':
                source = unpack(archive, work / 'tools-unpacked')
                source.rename(prefix / name)
                archive.unlink()
            else:
                archive.rename(prefix / name)
        (prefix / 'SDK-Release.json').write_bytes(raw)
        tools = prefix / 'Tools'
        profile_path = tools / 'RustToolsProfile.json'
        if digest(profile_path) != release['devkit']['profile_sha256']:
            raise ValueError('The SDK tool profile does not match its release manifest.')
        profile = json.loads(profile_path.read_text())
        verify_files(tools, {v['path']: v['sha256'] for v in profile['files']})
        # Rust and Zig may require different revisions with the same Contract
        # package version. Install the release dependency without changing defaults.
        contract = manager.root / 'Contract' / release['contract']['source_commit']
        if not contract.exists():
            from service import package_info
            item = release['contract']['package']
            archive = work / item['file']
            download(manager, item['url'], archive, item['sha256'], limit=64 * 1024**2)
            source = unpack(archive, work / 'contract-unpacked')
            verify_files(source, {v['path']: v['sha256'] for v in profile['contract']['inputs']})
            compiler = next((v for v in manager.installed('zig') if v['version'] == '0.16.0'), None)
            if not compiler:
                raise ValueError('Install Zig 0.16.0 to verify the SDK Contract package.')
            verification = work / 'contract-check'
            verification.mkdir()
            (verification / 'build.zig').write_text('pub fn build(_: *@import("std").Build) void {}\n')
            hashed = command([compiler['binary'], 'fetch', '--global-cache-dir', verification / 'cache', source],
                             {'PATH': '/usr/bin:/bin', 'HOME': str(verification)}, verification)
            contract_record = {**package_info(source), 'id': contract.name, 'revision': contract.name,
                               'archiveUrl': item['url'], 'sourceUrl': release['contract']['source_url'],
                               'sha256': item['sha256'], 'packageHash': hashed, 'installedAt': now()}
            (source / '.studio-component.json').write_text(json.dumps(contract_record, indent=2) + '\n')
            publish(source, contract)
        verify_files(contract, {v['path']: v['sha256'] for v in profile['contract']['inputs']})
        for key in ('catalog', 'packager'):
            (tools / profile['hosts']['Linux'][key]).chmod(0o755)
        item = SPEC['powershell']
        archive = work / 'powershell.tar.gz'
        download(manager, item['url'], archive, item['sha256'], limit=128 * 1024**2)
        unpack(archive, work / 'powershell-unpacked').rename(prefix / 'PowerShell')
        archive.unlink()
        pwsh = prefix / 'PowerShell/pwsh'
        pwsh.chmod(0o755)
        env = environment(prefix, work)
        actual = command([pwsh, '-NoLogo', '-NoProfile', '-Command', '$PSVersionTable.PSVersion.ToString()'], env, work)
        if actual != item['version']:
            raise ValueError('The PowerShell runner version does not match its archive.')
        manager.progress('Installing the SDK-pinned Rust toolchain and LLVM target tools…', received=0, total=0)
        args = [pwsh, '-NoLogo', '-NoProfile', '-File', tools / 'Setup/Rust.ps1',
                '--root', prefix / 'Install', '--cache-root', work / 'cache']
        command(args + ['setup'], env, work, timeout=900)
        description = json.loads(command(args + ['check'], env, work))
        if not description['complete_toolset'] or description['rust_version'] != SPEC['version']:
            raise ValueError('The SDK toolchain readiness check failed.')
        # The query is deliberately compiler-free; the SDK validates its own export.
        catalog = tools / profile['hosts']['Linux']['catalog']
        output = command([catalog, 'capabilities', '--json', '--profile', profile_path], {'PATH': '', 'HOME': str(work)}, work)
        if json.loads(output) != json.loads((prefix / 'capabilities.json').read_text()):
            raise ValueError('The SDK capability query differs from the published catalog.')
        value = {**record(), 'installedAt': now(), 'installationMethod': 'r4os-sdk-profile',
                 'binarySha256': digest(prefix / COMPILER), 'powershellVersion': actual,
                 'fileHashes': {str(p.relative_to(prefix)): digest(p) for p in prefix.rglob('*') if p.is_file() and not p.is_symlink()},
                 'symlinks': {str(p.relative_to(prefix)): os.readlink(p) for p in prefix.rglob('*') if p.is_symlink()}}
        verify(prefix, value)
        atomic(prefix / '.studio-installing.json', pending)
        publish(prefix, root / SPEC['id'])
    # rustup and the PS7 runner must work at the published path as well.
    prefix = root / SPEC['id']
    check = [prefix / 'PowerShell/pwsh', '-NoLogo', '-NoProfile', '-File', prefix / 'Tools/Setup/Rust.ps1',
             '--root', prefix / 'Install', '--cache-root', prefix / 'Install/.cache', 'check']
    result = json.loads(command(check, environment(prefix, prefix / 'Install'), prefix / 'Install'))
    if not result['complete_toolset']:
        raise ValueError('The published SDK Rust toolchain could not be verified.')
    verify(prefix, value)
    atomic(prefix / '.studio-component.json', value)
    (prefix / '.studio-installing.json').unlink()
