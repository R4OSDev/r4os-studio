"""Fixed minimal source closure, reproducible native packer, no project pins changed."""
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

SPEC = json.loads((Path(__file__).resolve().parents[2] / 'shared/r4os/r4upack-profile.json').read_text())
SPEC_HASH = hashlib.sha256(json.dumps(SPEC, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def regular(path, limit=16 * 1024 * 1024):
    path = Path(path).absolute()
    info = path.lstat()
    if path.resolve(strict=True) != path or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
        raise ValueError('R4UPack requires an unlinked regular file at its bound path.')
    return path


def verify(directory, binary=None):
    directory = Path(directory).absolute()
    if directory.resolve(strict=True) != directory or not directory.is_dir(): raise ValueError('Invalid R4UPack profile directory.')
    marker = regular(directory / '.studio-component.json')
    value = json.loads(marker.read_text())
    if (value.get('schema') != 1 or value.get('id') != SPEC['id'] or value.get('version') != SPEC['version'] or value.get('profileSha256') != SPEC_HASH
            or value.get('sha256') != SPEC['binarySha256'] or value.get('host') != SPEC['host']
            or value.get('revision') != SPEC['distributionRevision'] or value.get('sdkRevision') != SPEC['sdkRevision']):
        raise ValueError('The R4UPack qualification profile changed.')
    if json.loads(regular(directory / 'source-profile.json').read_text()) != SPEC: raise ValueError('The R4UPack source profile changed.')
    binary = regular(binary or directory / 'r4upack')
    if not binary.stat().st_mode & 0o111 or digest(binary) != SPEC['binarySha256']:
        raise ValueError('The R4UPack binary SHA-256 does not match its qualified profile.')
    for key, source in SPEC['sources'].items():
        if digest(regular(directory / 'sources' / key)) != source['sha256']:
            raise ValueError('The retained R4UPack source or license SHA-256 changed.')
    return {**value, 'directory': str(directory), 'binary': str(binary)}


def inventory(root, external=None):
    root = Path(root)
    records = []
    folder = root / 'Toolchains/R4UPack'
    if folder.exists():
        if folder.resolve(strict=True) != folder: raise ValueError('The R4UPack profile folder is linked.')
        for path in folder.iterdir():
            if path.name.startswith('.'): continue
            try:
                value = verify(path)
                if value['id'] != path.name: raise ValueError('R4UPack directory identity mismatch.')
                records.append(value)
            except (OSError, ValueError, TypeError, KeyError):
                continue  # Invalid installations stay on disk and cannot be selected.
    if external is not None:
        if (not isinstance(external, dict) or set(external) != {'binary', 'directory', 'sha256'}
                or external['sha256'] != SPEC['binarySha256']):
            raise ValueError('The administrator R4UPack binding is invalid.')
        value = verify(external['directory'], external['binary'])
        value.update(id='external-' + SPEC['id'], external=True)
        records.append(value)
    return records


def selected(root, records):
    path = Path(root) / 'Profiles/r4upack.json'
    if not path.exists(): return None
    value = json.loads(regular(path).read_text())
    if value.get('schema') != 1 or set(value) != {'schema', 'id', 'sha256', 'profileSha256'}:
        raise ValueError('Unsupported R4UPack selection; existing configuration was preserved.')
    return next((entry for entry in records if all(entry.get(key) == value[key] for key in ('id', 'sha256', 'profileSha256'))), None)


def pin(root, external=None):
    """Resolve once at job admission; callers persist this exact identity/hash/path."""
    value = selected(root, inventory(root, external))
    if value is None: raise ValueError('Select a qualified installed R4UPack profile in System updates first.')
    return value


def choose(root, ident, records):
    value = next((entry for entry in records if entry['id'] == ident), None)
    if value is None: raise ValueError('Only a qualified installed R4UPack profile can be selected.')
    atomic(Path(root) / 'Profiles/r4upack.json', {'schema': 1, **{key: value[key] for key in ('id', 'sha256', 'profileSha256')}})


def install(manager, source_dir=None):
    if platform.system() != 'Linux' or platform.machine() != 'x86_64': raise ValueError('This R4UPack profile requires Linux x86_64.')
    base = manager.root / 'Toolchains/R4UPack'
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    if base.resolve(strict=True) != base: raise ValueError('Linked R4UPack installation path.')
    target = base / SPEC['id']
    if target.exists():
        return verify(target)  # Never overwrite or repair a mismatched installation.
    compiler = regular(manager.root / 'Toolchains/Zig' / SPEC['compiler']['version'] / 'zig', limit=512 * 1024 * 1024)
    if digest(compiler) != SPEC['compiler']['binarySha256']: raise ValueError('The bound Zig compiler SHA-256 changed.')
    with tempfile.TemporaryDirectory(prefix='.build-', dir=base) as temporary:
        work = Path(temporary); output = work / 'profile'; output.mkdir(mode=0o700)
        for key, source in SPEC['sources'].items():
            manager.progress('Reading pinned R4UPack sources and licenses…')
            if source_dir is not None:
                data = regular(Path(source_dir) / key).read_bytes()
            else:
                data = read_url('https://raw.githubusercontent.com/R4OSDev/' + key.partition('/')[0] + '/' + source['revision'] + '/' + source['path'], limit=2 * 1024 * 1024)
            if hashlib.sha256(data).hexdigest() != source['sha256']: raise ValueError('The pinned R4UPack source SHA-256 changed.')
            path = output / 'sources' / key; path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
        environment = {'PATH': '/usr/bin:/bin', 'HOME': str(work), 'LANG': 'C.UTF-8'}
        version = subprocess.run([str(compiler), 'version'], env=environment, capture_output=True, text=True, timeout=10)
        if version.returncode or version.stdout.strip() != SPEC['compiler']['version']: raise ValueError('The bound Zig compiler version changed.')
        argv = [str(compiler), 'build-exe', '-O', 'ReleaseSafe', '-target', 'x86_64-linux-gnu', '-fstrip', '--dep', 'r4u_artifact',
                '-Mroot=' + str(output / 'sources/r4os-distribution/Tools/R4UPack/src/main.zig'),
                '-Mr4u_artifact=' + str(output / 'sources/r4os-sdk/r4os/r4u_artifact.zig'),
                '--cache-dir', str(work / 'cache'), '--global-cache-dir', str(work / 'global'), '-femit-bin=' + str(output / 'r4upack')]
        manager.progress('Building the pinned minimal R4UPack profile…')
        result = subprocess.run(argv, env=environment, capture_output=True, text=True, timeout=240)
        if result.returncode: raise ValueError('R4UPack compilation failed: ' + (result.stderr or result.stdout)[-1800:])
        binary = output / 'r4upack'
        if digest(binary) != SPEC['binarySha256']: raise ValueError('The reproduced R4UPack binary SHA-256 differs from the qualified build.')
        help_result = subprocess.run([str(binary), '--help'], env=environment, capture_output=True, text=True, timeout=10)
        help_text = help_result.stdout + help_result.stderr
        if help_result.returncode or not all(word in help_text for word in ('--description-file', '--payload', '--require', '4294967295')):
            raise ValueError('The qualified R4UPack help contract is unavailable.')
        (output / 'qualification.txt').write_text('Build exit: 0\nHelp exit: 0\n' + help_text)
        (output / 'source-profile.json').write_text(json.dumps(SPEC, indent=2) + '\n')
        atomic(output / '.studio-component.json', {'schema': 1, 'id': SPEC['id'], 'version': SPEC['version'],
            'revision': SPEC['distributionRevision'], 'sdkRevision': SPEC['sdkRevision'], 'host': SPEC['host'],
            'sourceUrl': 'https://github.com/R4OSDev/r4os-distribution/tree/' + SPEC['distributionRevision'] + '/Tools/R4UPack',
            'sha256': SPEC['binarySha256'], 'profileSha256': SPEC_HASH, 'installedAt': now()})
        for path in output.rglob('*'):
            if path.is_file():
                with path.open('rb') as stream: os.fsync(stream.fileno())
        for path in [p for p in output.rglob('*') if p.is_dir()] + [output]:
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
        publish(output, target)
    return verify(target)


class R4UPack:
    def catalog(self, manager, kind, older):
        return {'versions': [{'id': SPEC['id'], 'version': SPEC['version'], 'revision': SPEC['distributionRevision'],
                'sdkRevision': SPEC['sdkRevision'], 'host': SPEC['host'], 'sha256': SPEC['binarySha256'],
                'profileSha256': SPEC_HASH}], 'latestId': SPEC['id'], 'hasMore': False}

    def install(self, manager, kind, record):
        if record['id'] != SPEC['id']: raise ValueError('Unsupported R4UPack build profile.')
        install(manager)
