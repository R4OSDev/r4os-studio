"""Distribution packer sources, built with the selected SDK's host policy."""
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import tempfile

from common import read_url, publish
from service import atomic, digest, now
import sdk_host
import sdk_package
import sdk_provision

SPEC = json.loads((Path(__file__).resolve().parents[2] / 'shared/r4os/r4upack-profile.json').read_text())
SPEC_HASH = hashlib.sha256(json.dumps(SPEC, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def regular(path, limit=16 * 1024**2):
    path = Path(path).absolute()
    info = path.lstat()
    if path.resolve(strict=True) != path or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
        raise ValueError('R4UPack requires an unlinked regular file at its bound path.')
    return path


def sdk(root, revision=None, sources=False):
    if revision is None:
        state = json.loads(regular(Path(root) / 'Profiles/versions.json').read_text())
        revision = state['defaults'].get('sdk', {}).get('revision')
    return sdk_provision.verify(root, revision, sources=sources)


def profile_id(context):
    profiles = [(ident, value) for ident, value in context['profiles']['Build']['profiles'].items()
                if value['language'] == 'Zig' and value['role'] == 'host']
    if len(profiles) != 1:
        raise ValueError('The SDK does not identify one native host-tool profile.')
    return profiles[0][0]


def identity(context):
    data = {'distribution': SPEC_HASH, 'sdk': context['record']['revision'],
            'profileSources': context['record']['profileSources'], 'hostProfile': profile_id(context)}
    return 'distribution-' + SPEC['distributionRevision'][:12] + '-sdk-' + hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:24]


def verify(directory, binary=None, root=None):
    directory = Path(directory).absolute()
    if directory.resolve(strict=True) != directory or not directory.is_dir():
        raise ValueError('Invalid R4UPack profile directory.')
    value = json.loads(regular(directory / '.studio-component.json').read_text())
    if value.get('schema') != 2 or value.get('distributionProfileSha256') != SPEC_HASH:
        raise ValueError('This historical R4UPack needs explicit migration to SDK-owned host profiles.')
    root = Path(root) if root is not None else directory.parents[2]
    context = sdk(root, value['sdkRevision'])
    sources = json.loads(regular(directory / 'source-profile.json').read_text())
    proof = json.loads(regular(directory / 'native-build.json', 2 * 1024**2).read_text())
    if (value['id'] != identity(context) or value['version'] != SPEC['version']
            or value['revision'] != SPEC['distributionRevision'] or value.get('host') != 'x86_64-linux'
            or value['profileSha256'] != digest(directory / 'source-profile.json')
            or value.get('buildProofSha256') != digest(directory / 'native-build.json')
            or sources.get('sdkManifestSha256') != context['record']['manifestSha256']
            or sources.get('profileSources') != context['record']['profileSources']
            or sources.get('distribution') != SPEC or proof.get('exitCode') != 0
            or proof.get('sdkProfile', {}).get('hashes') != context['record']['profileSources']
            or proof['sdkProfile'].get('id') != profile_id(context)
            or proof['sdkProfile'].get('technical') is not False):
        raise ValueError('The R4UPack SDK/source/build binding changed.')
    for key, source in SPEC['sources'].items():
        if digest(regular(directory / 'sources' / key)) != source['sha256']:
            raise ValueError('The retained Distribution source or license changed.')
    binary = regular(binary or directory / 'r4upack')
    if not binary.stat().st_mode & 0o111 or digest(binary) != value['sha256'] or proof.get('binarySha256') != value['sha256']:
        raise ValueError('The SDK-bound R4UPack binary changed.')
    return {**value, 'directory': str(directory), 'binary': str(binary)}


def inventory(root, external=None):
    root = Path(root); records = []
    folder = root / 'Toolchains/R4UPack'
    if folder.exists():
        if folder.resolve(strict=True) != folder:
            raise ValueError('The R4UPack profile folder is linked.')
        for path in folder.iterdir():
            if path.name.startswith('.') or not path.is_dir() or path.is_symlink():
                continue
            try:
                value = verify(path, root=root)
                if value['id'] != path.name:
                    raise ValueError('R4UPack directory identity mismatch.')
                records.append(value)
            except (OSError, ValueError, TypeError, KeyError):
                continue
    if external is not None:
        if not isinstance(external, dict) or set(external) != {'binary', 'directory', 'sha256'}:
            raise ValueError('Invalid administrator R4UPack binding.')
        value = verify(external['directory'], external['binary'], root=root)
        if value['sha256'] != external['sha256']:
            raise ValueError('The administrator R4UPack binary binding changed.')
        records.append({**value, 'id': 'external-' + value['id'], 'external': True})
    return records


def selected(root, records):
    path = Path(root) / 'Profiles/r4upack.json'
    if not path.exists():
        return None
    value = json.loads(regular(path).read_text())
    if value.get('schema') != 1 or set(value) != {'schema', 'id', 'sha256', 'profileSha256'}:
        raise ValueError('Unsupported R4UPack selection; existing configuration was preserved.')
    return next((entry for entry in records if all(entry.get(key) == value[key] for key in ('id', 'sha256', 'profileSha256'))), None)


def pin(root, external=None):
    value = selected(root, inventory(root, external))
    if value is None:
        raise ValueError('Select an installed SDK-bound R4UPack in System updates.')
    return value


def choose(root, ident, records):
    value = next((entry for entry in records if entry['id'] == ident), None)
    if value is None:
        raise ValueError('Only an SDK-bound installed R4UPack can be selected.')
    atomic(Path(root) / 'Profiles/r4upack.json', {'schema': 1, **{key: value[key] for key in ('id', 'sha256', 'profileSha256')}})


def install(manager, source_dir=None, sdk_revision=None):
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('R4UPack requires Linux x86_64.')
    context = sdk(manager.root, sdk_revision, sources=True)
    ident = identity(context)
    base = manager.root / 'Toolchains/R4UPack'
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    if base.resolve(strict=True) != base:
        raise ValueError('Linked R4UPack installation path.')
    target = base / ident
    if target.exists():
        return verify(target, root=manager.root)
    with tempfile.TemporaryDirectory(prefix='.build-', dir=base) as temporary:
        work = Path(temporary); output = work / 'profile'; output.mkdir(mode=0o700)
        for key, source in SPEC['sources'].items():
            manager.progress('Reading Distribution sources and licenses…')
            data = regular(Path(source_dir) / key).read_bytes() if source_dir else read_url(
                'https://raw.githubusercontent.com/R4OSDev/' + key.partition('/')[0] + '/' + source['revision'] + '/' + source['path'], limit=2 * 1024**2)
            if hashlib.sha256(data).hexdigest() != source['sha256']:
                raise ValueError('The Distribution source SHA-256 changed.')
            path = output / 'sources' / key; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        resolved = sdk_package.decode(sdk_host.invoke(context['runner'], context['paths']['sdk'], 'Profile.ps1',
            ['-Action', 'Resolve', '-Profile', profile_id(context), '-ContractRoot', context['paths']['contract'],
             '-LibrariesRoot', context['paths']['libraries']], work, log=output / 'sdk-host-profile'))
        if resolved['technical'] is not False or resolved['hashes'] != context['record']['profileSources']:
            raise ValueError('The SDK host profile is not regular or its original hashes changed.')
        optimize = resolved['codegen']['optimize']
        if optimize not in resolved['codegen']['allowed_optimize_modes']:
            raise ValueError('The SDK host optimization policy is inconsistent.')
        compiler = context['paths']['install'] / 'Toolchains/Zig/zig'
        native = [str(compiler), 'build-exe', '-O' + optimize, '--dep', 'r4u_artifact',
            '-Mroot=' + str(output / 'sources/r4os-distribution/Tools/R4UPack/src/main.zig'),
            '-Mr4u_artifact=' + str(context['paths']['sdk'] / 'r4os/r4u_artifact.zig'),
            '--cache-dir', str(work / 'cache'), '--global-cache-dir', str(work / 'global'), '-femit-bin=' + str(output / 'r4upack')]
        manager.progress('Building R4UPack with the SDK host profile…')
        environment = {'PATH': '/usr/bin:/bin', 'HOME': str(work), 'LANG': 'C.UTF-8'}
        result = subprocess.run(native, env=environment, capture_output=True, timeout=240)
        (output / 'build.stdout').write_bytes(result.stdout); (output / 'build.stderr').write_bytes(result.stderr)
        if result.returncode:
            raise ValueError('SDK-bound R4UPack compilation failed: ' + result.stderr[-1800:].decode(errors='replace'))
        binary = output / 'r4upack'; checksum = digest(binary)
        help_result = subprocess.run([str(binary), '--help'], env=environment, capture_output=True, text=True, timeout=10)
        help_text = help_result.stdout + help_result.stderr
        if help_result.returncode or not all(word in help_text for word in ('--description-file', '--payload', '--require', '4294967295')):
            raise ValueError('The SDK-bound R4UPack help interface is unavailable.')
        (output / 'help.txt').write_text(help_text)
        source_profile = {'schema': 2, 'distribution': SPEC, 'sdkRevision': context['record']['revision'],
                          'sdkManifestSha256': context['record']['manifestSha256'], 'profileSources': resolved['hashes']}
        atomic(output / 'source-profile.json', source_profile)
        atomic(output / 'native-build.json', {'schema': 1, 'arguments': native, 'exitCode': result.returncode,
            'sdkProfile': {'id': resolved['profile'], 'hashes': resolved['hashes'], 'technical': False},
            'codegen': resolved['codegen'], 'compilerSha256': digest(compiler), 'binarySha256': checksum})
        atomic(output / '.studio-component.json', {'schema': 2, 'id': ident, 'version': SPEC['version'], 'kind': 'r4upack',
            'host': 'x86_64-linux', 'revision': SPEC['distributionRevision'], 'sdkRevision': context['record']['revision'],
            'sha256': checksum, 'profileSha256': digest(output / 'source-profile.json'),
            'buildProofSha256': digest(output / 'native-build.json'),
            'distributionProfileSha256': SPEC_HASH, 'installedAt': now()})
        publish(output, target)
    return verify(target, root=manager.root)


class R4UPack:
    def catalog(self, manager, kind, older):
        context = sdk(manager.root)
        ident = identity(context)
        return {'versions': [{'id': ident, 'version': SPEC['version'], 'revision': SPEC['distributionRevision'],
            'sdkRevision': context['record']['revision'], 'host': 'x86_64-linux'}], 'latestId': ident, 'hasMore': False}

    def install(self, manager, kind, record):
        if record['id'] != identity(sdk(manager.root)):
            raise ValueError('The SDK packer selection changed. Refresh before installing.')
        install(manager)
