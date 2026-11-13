"""Read immutable managed runtime identities without executing repository code."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

MAX_MANIFEST = 32 * 1024 * 1024
SLEIGH_LOCK = re.compile(r'Programs/Ghidra/Ghidra/Processors/[^/]+/data/languages/[^/]+\.sla\.lock')


def read(path, limit=MAX_MANIFEST, *, state=None):
    if path.resolve(strict=True) != path: raise ValueError('Linked runtime metadata.')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit: raise ValueError('Invalid runtime metadata size or type.')
        raw = stream.read(limit + 1)
        if state is not None and (file_state(info) != state or file_state(os.fstat(stream.fileno())) != state):
            raise ValueError('The managed runtime metadata changed while reading.')
    if len(raw) > limit: raise ValueError('Runtime metadata exceeds its limit.')
    return raw


def relative(value):
    if (not isinstance(value, str) or not value or len(os.fsencode(value)) > 4096 or '\0' in value
            or str(PurePosixPath(value)) != value or PurePosixPath(value).is_absolute()
            or any(p in ('.', '..', '.git') for p in PurePosixPath(value).parts)):
        raise ValueError('Invalid managed runtime path.')
    return value


def load(skills, ident, binding, complete=False, catalog_only=False, *, verify=None):
    runtime = binding['runtime']
    if binding['recipe'] != 'rea' or not isinstance(runtime, dict): raise ValueError('No managed runtime is bound.')
    path = relative(runtime['path'])
    if not re.fullmatch('Runtimes/' + binding['commit'] + '/[a-f0-9]{64}', path): raise ValueError('Runtime/source mismatch.')
    root = Path(skills).absolute() / ident / path
    if root.resolve(strict=True) != root or not root.is_dir(): raise ValueError('Linked or missing runtime.')
    manifest_path = root / 'runtime.json'
    state = file_state(manifest_path.lstat())
    raw = read(manifest_path, state=state)
    if hashlib.sha256(raw).hexdigest() != runtime['manifestHash']: raise ValueError('The immutable runtime manifest changed.')
    value = json.loads(raw)
    if (value.get('schema') != 1 or value.get('recipe') != 'rea' or value.get('version') != runtime['version']
            or value.get('source') != dict(repository=binding['repository'], commit=binding['commit'], manifestHash=binding['sourceManifestHash'])
            or not isinstance(value.get('files'), list) or not isinstance(value.get('programs'), dict)):
        raise ValueError('The immutable source/runtime identities do not match.')
    for key in ('node', 'entry', 'catalog'):
        item = value[key]; relative(item['path'])
        if not re.fullmatch('[a-f0-9]{64}', item['sha256']): raise ValueError('Invalid runtime component identity.')
        if catalog_only and key != 'catalog': continue
        actual = read(root / item['path'], 256 * 1024 * 1024 if key == 'node' else MAX_MANIFEST)
        if hashlib.sha256(actual).hexdigest() != item['sha256']: raise ValueError('The managed ' + key + ' changed.')
    if value['entry'].get('arguments') != ['mcp']: raise ValueError('Unexpected managed REA start arguments.')
    catalog = json.loads(read(root / value['catalog']['path']))
    if (catalog.get('version') != 1 or catalog.get('info', {}).get('version') != value['version']
            or not isinstance(catalog.get('tools'), list) or not 1 <= len(catalog['tools']) <= 10000):
        raise ValueError('The managed MCP catalogue is invalid.')
    names = [t['name'] for t in catalog['tools']]
    if len(set(names)) != len(names) or any(not isinstance(t.get('inputSchema'), dict) for t in catalog['tools']):
        raise ValueError('Duplicate methods or invalid MCP schemas.')
    if complete: (verify or verify_files)(root, value['files'], manifest_state=state)
    return root, value, catalog


def generated_sleigh_lock(root, name, files):
    if not SLEIGH_LOCK.fullmatch(name):
        return False
    language = files.get(name.removesuffix('.lock'))
    if language is None or 'link' in language:
        return False
    lock = root / name
    mode = lock.lstat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o111:
        return False
    # Ghidra writes the holder's PID and truncates the file on release.
    return re.fullmatch(rb'(?:[1-9][0-9]{0,9}\n)?', read(lock, 32)) is not None


def file_state(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid,
            info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def inventory_state(root, expected, manifest_state=None):
    observed = {}
    directories = {}
    links = []

    def walk(folder, prefix=''):
        directory = folder.stat(follow_symlinks=False)
        if not stat.S_ISDIR(directory.st_mode):
            raise ValueError('The managed runtime directory changed.')
        with os.scandir(folder) as entries:
            for entry in entries:
                name = prefix + entry.name
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    walk(Path(entry.path), name + '/')
                elif name in expected or name == 'runtime.json':
                    observed[name] = file_state(info)
                    if stat.S_ISLNK(info.st_mode):
                        links.append(name)
                elif not generated_sleigh_lock(root, name, expected):
                    raise ValueError('The immutable runtime inventory changed.')
        directories[folder] = file_state(directory)

    walk(root)
    if observed.keys() != expected.keys() | {'runtime.json'}:
        raise ValueError('The immutable runtime inventory changed.')
    if manifest_state is not None and observed['runtime.json'] != manifest_state:
        raise ValueError('The immutable runtime manifest changed during verification.')
    for name in links:
        target = (root / name).resolve(strict=True)
        if not target.is_relative_to(root):
            raise ValueError('The managed runtime link leaves its namespace.')
        if target in directories:
            observed[name] += directories[target]
    if any(file_state(path.stat(follow_symlinks=False)) != state for path, state in directories.items()):
        raise ValueError('The managed runtime directory changed during inspection.')
    return observed


def verify_files(root, files, *, manifest_state=None, previous=None):
    expected = {}
    for item in files:
        name = relative(item['path'])
        if name in expected:
            raise ValueError('Duplicate runtime file identity.')
        expected[name] = item
    state = inventory_state(root, expected, manifest_state)
    if previous is not None and state == previous:
        return previous

    for name, item in expected.items():
        path = root / name
        info = state[name]
        mode, links, size = info[2], info[3], info[6]
        if 'link' in item:
            if (not stat.S_ISLNK(mode) or os.readlink(path) != item['link']
                    or Path(item['link']).is_absolute() or not path.resolve(strict=True).is_relative_to(root)):
                raise ValueError('The managed runtime link changed or leaves its namespace.')
            continue
        if not stat.S_ISREG(mode) or links != 1 or size != item['bytes'] or bool(mode & 0o111) != item['executable']:
            raise ValueError('The managed runtime file changed.')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            if (file_state(os.fstat(fd)) != state[name]
                    or hashlib.file_digest(stream, 'sha256').hexdigest() != item['sha256']
                    or file_state(os.fstat(fd)) != state[name]):
                raise ValueError('The managed runtime file hash changed.')
    if inventory_state(root, expected, manifest_state) != state:
        raise ValueError('The managed runtime files changed during verification.')
    return state
