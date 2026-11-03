"""Provision one immutable SDK package; native SDK tools own its validation."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import tempfile

from common import download, publish, read_url
import sdk_host
import sdk_package as package
from service import atomic, now, package_info, run

MAX_INSTALLATION_METADATA = 32 * 1024**2


def package_root(root, revision):
    if not isinstance(revision, str) or not package.COMMIT.fullmatch(revision):
        raise ValueError('An SDK package needs its exact source revision.')
    path = Path(root) / 'Packages' / revision
    if path.absolute() != path.resolve():
        raise ValueError('Invalid SDK package directory.')
    return path


def paths(root, revision):
    base = package_root(root, revision)
    saved = package.decode(package.regular_bytes(base / 'bundle.json', MAX_INSTALLATION_METADATA), MAX_INSTALLATION_METADATA)
    if saved.get('schema') != 1 or saved.get('interface') != package.INTERFACE or saved.get('revision') != revision:
        raise ValueError('The SDK package is not completely prepared.')
    manifest_raw = package.regular_bytes(base / 'SDK-Release.json')
    document = package.manifest(manifest_raw, saved['version'], revision)
    if package.sha256(manifest_raw) != saved['manifestSha256']:
        raise ValueError('The SDK package manifest changed.')
    package.checksums(package.regular_bytes(base / 'SHA256SUMS.txt'), manifest_raw, document)
    result = {name: Path(root) / package.relative(value) for name, value in saved['paths'].items()}
    for path in result.values():
        if path.resolve(strict=True) != path.absolute():
            raise ValueError('An SDK package root is missing or indirect.')
    return base, saved, document, result


def verify(root, revision, *, sources=True):
    base, saved, document, roots = paths(root, revision)
    capability = package.regular_bytes(base / package.asset(document, 'capabilities')['path'])
    profiles = package.profiles(roots['sdk'], document, capability)
    if sources:
        for name, checksum in saved['hostFiles'].items():
            file = base / package.relative(name)
            if file.is_symlink() or not file.is_file():
                raise ValueError('An SDK host tool changed: ' + name)
            with file.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != checksum:
                    raise ValueError('An SDK host tool changed: ' + name)
        for name, target in saved['hostLinks'].items():
            file = base / package.relative(name)
            if not file.is_symlink() or os.readlink(file) != target or not file.resolve(strict=True).is_relative_to(base / 'Install'):
                raise ValueError('An SDK host tool link changed: ' + name)
    runner = sdk_host.powershell(root)
    if sources:
        receipt = package.decode(sdk_host.invoke(runner, roots['sdk'], 'Profile.ps1',
            ['-Action', 'Validate'], base / 'Work'))
        if receipt.get('valid') is not True or receipt.get('hashes') != package.profile_hashes(document):
            raise ValueError('The native SDK profile receipt changed.')
    return {'base': base, 'record': saved, 'manifest': document, 'paths': roots,
            'profiles': profiles, 'capabilities': package.decode(capability), 'runner': runner}


def extract(archive, destination, prefix):
    with tarfile.open(archive) as source:
        members = source.getmembers()
        if len(members) > 200_000 or sum(item.size for item in members) > 2 * 1024**3:
            raise ValueError('The SDK archive exceeds extraction limits.')
        seen = set()
        for item in members:
            name = package.relative(item.name.rstrip('/'))
            if (name.split('/')[0] != prefix or name.casefold() in seen
                    or not (item.isfile() or item.isdir())):
                raise ValueError('The SDK archive has an invalid or conflicting entry.')
            seen.add(name.casefold())
        source.extractall(destination, filter='data')
    return destination / prefix


def collect_host_files(base):
    result, links = {}, {}
    for path in sorted((base / 'Install').rglob('*')):
        if path.is_symlink():
            if not path.resolve(strict=True).is_relative_to(base / 'Install'):
                raise ValueError('The SDK host installation has an escaping link.')
            links[str(path.relative_to(base))] = os.readlink(path)
        elif path.is_file() and '/.Cache/' not in str(path):
            with path.open('rb') as stream:
                result[str(path.relative_to(base))] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return result, links


def prepare(manager, selected):
    """Ready is published only after all archives, sources and tools verify."""
    from sdk_sets import manifest_url, resolve
    resolved = resolve(manager, selected)
    revision = selected['id']
    base = package_root(manager.root, revision)
    base.mkdir(parents=True, exist_ok=True)
    if (base / 'bundle.json').is_file():
        context = verify(manager.root, revision)
        if context['record']['manifestSha256'] != resolved['manifestSha256']:
            raise ValueError('The installed SDK package belongs to different release metadata.')
        records = context['record']['components']
        for kind in package.SOURCE_ROLES:
            marker = context['paths'][kind] / '.studio-component.json'
            if not marker.exists():
                atomic(marker, records[kind])
        return records
    url = manifest_url(selected)
    raw = read_url(url, package.MAX_METADATA)
    document = package.manifest(raw, selected['version'], revision)
    if package.sha256(raw) != resolved['manifestSha256']:
        raise ValueError('The selected SDK manifest changed during preparation.')
    sums = read_url(url.removesuffix('SDK-Release.json') + 'SHA256SUMS.txt', 65536)
    package.checksums(sums, raw, document)
    identity = {'schema': 1, 'revision': revision, 'manifestSha256': package.sha256(raw)}
    marker = base / 'preparing.json'
    if marker.exists() and package.decode(package.regular_bytes(marker)) != identity:
        raise ValueError('An unfinished SDK preparation has another identity.')
    atomic(marker, identity)
    for name, data in [('SDK-Release.json', raw), ('SHA256SUMS.txt', sums)]:
        target = base / name
        if target.exists() and package.regular_bytes(target) != data:
            raise ValueError('Existing SDK package metadata changed.')
        if not target.exists():
            target.write_bytes(data)
    targets = {'sdk-source': manager.root / 'SDK' / revision,
               'contract-source': manager.root / 'Contract' / document['sources']['contract']['commit'],
               'libraries-source': manager.root / 'Libraries' / document['sources']['libraries']['commit']}
    targets.update({role: base / package.asset(document, role)['prefix'] for role in ('tools', 'recovery-sources')})
    for item in document['assets']:
        target = base / item['path']
        if target.exists():
            with target.open('rb') as stream:
                checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
            if target.is_symlink() or target.stat().st_size != item['bytes'] or checksum != item['sha256']:
                raise ValueError('An installed SDK package asset changed: ' + item['path'])
        else:
            partial = target.with_suffix(target.suffix + '.partial')
            if partial.exists():
                if partial.is_symlink() or not partial.is_file():
                    raise ValueError('Invalid interrupted SDK download.')
                partial.unlink()
            manager.progress('Downloading SDK package: ' + item['role'] + '…', received=0, total=item['bytes'])
            download(manager, item['url'], partial, item['sha256'], limit=item['bytes'])
            if partial.stat().st_size != item['bytes']:
                raise ValueError('The SDK package asset size changed.')
            partial.rename(target)
        if 'prefix' in item:
            destination = targets[item['role']]
            if destination.exists():
                if destination.is_symlink() or destination.resolve() != destination.absolute():
                    raise ValueError('An SDK source path is indirect.')
                continue
            with tempfile.TemporaryDirectory(prefix='.extract-', dir=base) as name:
                extracted = extract(target, Path(name), item['prefix'])
                publish(extracted, destination)
    roots = {'contract': str(targets['contract-source']), 'libraries': str(targets['libraries-source']),
             'recovery-sdk': str(targets['recovery-sources'] / 'Platform/SDK'),
             'recovery-contract': str(targets['recovery-sources'] / 'Platform/Contract'),
             'recovery-libraries': str(targets['recovery-sources'] / 'Legal/Sources/Libraries.zip')}
    atomic(base / 'roots.json', roots)
    runner = sdk_host.powershell(manager.root)
    home = base / 'Work'
    manager.progress('Verifying the complete SDK package and source set…')
    result = package.decode(sdk_host.invoke(runner, targets['sdk-source'], 'Package.ps1',
        ['-Action', 'Verify', '-PayloadRoot', base, '-Manifest', base / 'SDK-Release.json',
         '-RootsFile', base / 'roots.json', '-ToolsRoot', targets['tools']], home, log=base / 'package-verify'))
    if result.get('valid') is not True or result.get('technical') is not False or result.get('hashes') != package.profile_hashes(document):
        raise ValueError('The SDK package did not produce a complete native verification receipt.')
    package.profiles(targets['sdk-source'], document, package.regular_bytes(base / package.asset(document, 'capabilities')['path']))
    manager.progress('Provisioning SDK-selected Zig and Rust host tools…')
    install = base / 'Install'
    sdk_host.invoke(runner, targets['sdk-source'], 'Setup.ps1', ['-InstallRoot', install, '-Tools', 'zig'],
                    home, timeout=1200, log=base / 'setup-zig')
    sdk_host.invoke(runner, targets['sdk-source'], 'Setup.ps1', ['-InstallRoot', install, '-Tools', 'zig', '-Check'],
                    home, log=base / 'check-zig')
    sdk_host.invoke(runner, targets['sdk-source'], 'Rust.ps1', ['--root', install, '--profile', 'sdk', 'setup'],
                    home, timeout=1800, log=base / 'setup-rust')
    rust = sdk_host.rust_check(runner, targets['sdk-source'], install, home, log=base / 'check-rust')
    host_files, host_links = collect_host_files(base)
    zig = install / 'Toolchains/Zig/zig'
    expected_zig = document['tools']['zig']
    # zig fetch needs a build context even though this operation never compiles
    # project sources. This private empty context selects no build policy.
    (home / 'build.zig').write_text('pub fn build(_: *@import("std").Build) void {}\n')
    records = {}
    for kind, role in package.SOURCE_ROLES.items():
        source = targets[role]
        value = resolved['components'][kind]
        info = package_info(source)
        if info['version'] != value['version']:
            raise ValueError('The SDK source version contradicts its release.')
        package_hash = run([str(zig), 'fetch', '--global-cache-dir', str(home / 'zig-cache'), str(source)], cwd=home, timeout=180)
        if not re.fullmatch(r'[A-Za-z0-9_.+-]+', package_hash) or value.get('packageHash', package_hash) != package_hash:
            raise ValueError('The SDK source package hash contradicts its profile.')
        record = {**info, 'id': value['revision'], 'revision': value['revision'], 'sourceUrl': value['sourceUrl'],
                  'archiveUrl': value['url'], 'sha256': value['sha256'], 'zigPackageHash': package_hash,
                  'packageHash': package_hash, 'installedAt': now(), 'sdkReleaseManifestSha256': package.sha256(raw)}
        previous_marker = source / '.studio-component.json'
        if previous_marker.exists():
            previous = package.decode(package.regular_bytes(previous_marker))
            if (previous.get('revision') != value['revision'] or previous.get('version') != value['version']
                    or (previous.get('zigPackageHash') or previous.get('packageHash')) != package_hash):
                raise ValueError('The previously installed component identity changed.')
            record = previous
        if kind == 'sdk':
            record['sdkPackage'] = {'schema': 1, 'manifestSha256': package.sha256(raw),
                                    'profileSources': package.profile_hashes(document)}
        records[kind] = record
    all_paths = {'sdk': str(targets['sdk-source'].relative_to(manager.root)),
                 'contract': str(targets['contract-source'].relative_to(manager.root)),
                 'libraries': str(targets['libraries-source'].relative_to(manager.root)),
                 'tools': str(targets['tools'].relative_to(manager.root)),
                 'recovery': str(targets['recovery-sources'].relative_to(manager.root)),
                 'install': str(install.relative_to(manager.root))}
    record = {'schema': 1, 'interface': package.INTERFACE, 'version': document['sdk_version'],
              'revision': revision, 'manifestSha256': package.sha256(raw), 'profileSources': package.profile_hashes(document),
              'components': records, 'paths': all_paths, 'hostFiles': host_files, 'hostLinks': host_links,
              'rust': rust, 'zig': {'version': expected_zig['version'], 'url': expected_zig['hosts']['Linux']['url'],
                                  'sha256': expected_zig['hosts']['Linux']['sha256'],
                                  'binarySha256': host_files['Install/Toolchains/Zig/zig']},
              'verifiedAt': now(), 'technical': False, 'verification': result}
    atomic(base / 'bundle.json', record)
    for kind, role in package.SOURCE_ROLES.items():
        atomic(targets[role] / '.studio-component.json', records[kind])
    return records
