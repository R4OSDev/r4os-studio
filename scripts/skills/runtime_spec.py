"""Read immutable managed runtime identities without executing repository code."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

MAX_MANIFEST = 32 * 1024 * 1024
SLEIGH_LOCK = re.compile(r'Programs/Ghidra/Ghidra/Processors/[^/]+/data/languages/[^/]+\.sla\.lock')


def read(path, limit=MAX_MANIFEST):
    if path.resolve(strict=True) != path: raise ValueError('Linked runtime metadata.')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit: raise ValueError('Invalid runtime metadata size or type.')
        raw = stream.read(limit + 1)
    if len(raw) > limit: raise ValueError('Runtime metadata exceeds its limit.')
    return raw


def relative(value):
    if (not isinstance(value, str) or not value or len(os.fsencode(value)) > 4096 or '\0' in value
            or str(PurePosixPath(value)) != value or PurePosixPath(value).is_absolute()
            or any(p in ('.', '..', '.git') for p in PurePosixPath(value).parts)):
        raise ValueError('Invalid managed runtime path.')
    return value


def load(skills, ident, binding, complete=False, catalog_only=False):
    runtime = binding['runtime']
    if binding['recipe'] != 'rea' or not isinstance(runtime, dict): raise ValueError('No managed runtime is bound.')
    path = relative(runtime['path'])
    if not re.fullmatch('Runtimes/' + binding['commit'] + '/[a-f0-9]{64}', path): raise ValueError('Runtime/source mismatch.')
    root = Path(skills).absolute() / ident / path
    if root.resolve(strict=True) != root or not root.is_dir(): raise ValueError('Linked or missing runtime.')
    raw = read(root / 'runtime.json')
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
    if complete: verify_files(root, value['files'])
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


def verify_files(root, files):
    expected = {}
    for item in files:
        path = root / relative(item['path'])
        if item['path'] in expected: raise ValueError('Duplicate runtime file identity.')
        expected[item['path']] = item
        info = path.lstat()
        if 'link' in item:
            if (not stat.S_ISLNK(info.st_mode) or os.readlink(path) != item['link']
                    or Path(item['link']).is_absolute() or not path.resolve(strict=True).is_relative_to(root)):
                raise ValueError('The managed runtime link changed or leaves its namespace.')
        else:
            if (path.resolve(strict=True) != path or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_size != item['bytes'] or bool(info.st_mode & 0o111) != item['executable']):
                raise ValueError('The managed runtime file changed.')
            with path.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != item['sha256']: raise ValueError('The managed runtime file hash changed.')
    actual = set()
    for directory, folders, names in os.walk(root, followlinks=False):
        for name in folders + names:
            path = Path(directory) / name
            if path.is_symlink() or not path.is_dir(): actual.add(path.relative_to(root).as_posix())
    required = expected.keys() | {'runtime.json'}
    if not required <= actual or any(not generated_sleigh_lock(root, name, expected) for name in actual - required):
        raise ValueError('The immutable runtime inventory changed.')
