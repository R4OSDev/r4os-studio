"""Private Git storage and bounded, source-only operations. No repository code executes."""
from contextlib import contextmanager
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'projects'))
from store import ProjectFault
from project_use import acquire, project_id
from project_maintenance import project, require_idle
from layout import folder

MAX_FILES, MAX_BYTES, MAX_FILE = 10000, 256 * 1024 * 1024, 32 * 1024 * 1024


def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(path, value):
    path = Path(path); folder(path.parent)
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1: raise ProjectFault('Invalid Git publication target.', 503)
    temporary = path.with_name('.' + path.name + '.' + str(uuid.uuid4()) + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(parent)
        finally: os.close(parent)
    finally: temporary.unlink(missing_ok=True)


def document(path, limit=2 * 1024 * 1024):
    path = Path(path)
    if path.resolve(strict=True) != path: raise ProjectFault('Invalid Git storage path.', 503)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise ProjectFault('Invalid Git storage document.', 503)
        return json.load(stream)


def storage(projects, identity):
    base = folder(Path(projects) / project_id(identity))
    for relative in ('.studio', '.studio/git'):
        path = base / relative; path.mkdir(mode=0o700, exist_ok=True); folder(path)
    return base / '.studio/git'


def branch(value):
    if (not isinstance(value, str) or not 1 <= len(value.encode()) <= 255 or value.startswith(('-', '/', '.'))
            or value.endswith(('/', '.', '.lock')) or any(v in value for v in ('..', '@{', '//', '\\'))
            or any(ord(c) <= 32 or ord(c) == 127 or c in '~^:?*[' for c in value)
            or any(v.startswith('.') or v.endswith('.lock') for v in value.split('/'))):
        raise ProjectFault('Invalid Git branch name.', 400)
    return value


def name(value, owner=False):
    pattern = r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?' if owner else r'[A-Za-z0-9_.-]{1,100}'
    if not isinstance(value, str) or not re.fullmatch(pattern, value) or value in ('.', '..'):
        raise ProjectFault('Invalid GitHub repository identity.', 400)
    return value


def binding(projects, identity):
    path = storage(projects, identity) / 'binding.json'
    if not path.exists() and not path.is_symlink(): return None
    value = document(path, 16384)
    if (value.get('schema') != 1 or not isinstance(value.get('revision'), int) or value['revision'] < 1
            or not isinstance(value.get('userId'), int) or value['userId'] <= 0
            or not isinstance(value.get('repository', {}).get('id'), int) or value['repository']['id'] <= 0):
        raise ProjectFault('Invalid Git project binding. Existing data was preserved.', 503)
    project_id(value['connectionId']); branch(value['branch'])
    name(value['repository']['owner'], True); name(value['repository']['name'])
    return value


def source_path(value):
    if not isinstance(value, str) or not value or len(value.encode()) > 1024 or '\\' in value:
        raise ProjectFault('Unsupported repository path.', 400)
    parts = value.split('/')
    if any(p in ('', '.', '..') or p.casefold() in ('.git', '.studio') or p.endswith((' ', '.'))
           or any(ord(c) < 32 or ord(c) == 127 for c in p) for p in parts):
        raise ProjectFault('Unsupported repository path. Private Git paths are reserved.', 400)
    return value


def inventory(root, excluded=(), only=None):
    root = folder(root); result = {}; total = 0; entries = 0; deadline = time.monotonic() + 30
    def visit(current, depth):
        nonlocal total, entries
        if depth > 32: raise ProjectFault('Project exceeds the Git directory-depth limit.', 409)
        for entry in sorted(current.iterdir()):
            entries += 1
            if entries > 20000 or time.monotonic() > deadline: raise ProjectFault('Git source inspection exceeded its directory or time limit.', 409)
            relative = entry.relative_to(root).as_posix()
            if any(relative == p or relative.startswith(p + '/') for p in excluded): continue
            if only is not None and relative not in only and not any(p.startswith(relative + '/') for p in only): continue
            source_path(relative); info = entry.lstat()
            if stat.S_ISDIR(info.st_mode): visit(entry, depth + 1)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                if info.st_size > MAX_FILE: raise ProjectFault('A source file exceeds the 32 MiB Git limit.', 409)
                descriptor = os.open(entry, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(descriptor, 'rb') as stream:
                    opened = os.fstat(stream.fileno())
                    if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                        raise ProjectFault('Source file identity changed during inspection.', 409)
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                after = entry.lstat()
                if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise ProjectFault('Sources changed during Git inspection. Refresh and retry.', 409)
                result[relative] = {'sha256': digest, 'size': info.st_size, 'executable': bool(info.st_mode & 0o111)}
                total += info.st_size
                if len(result) > MAX_FILES or total > MAX_BYTES: raise ProjectFault('Project exceeds Git source limits (10,000 files / 256 MiB).', 409)
            else: raise ProjectFault('Git source operations do not support links or special files.', 409)
    visit(root, 0)
    return result


def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@contextmanager
def locks(projects, identity, mutate=True, agent=None):
    # Lifetime and workspace lock order matches existing project maintenance.
    lifetime = acquire(projects, identity, exclusive=mutate and agent is None)
    workspace_lock = None
    try:
        project(projects, identity)
        if mutate:
            if agent is not None: agent.verify(projects, identity)
            else:
                require_idle(projects, identity)
                path = folder(Path(projects) / '.studio') / ('workspace-' + identity + '.lock')
                fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600); workspace_lock = os.fdopen(fd, 'a')
                try: fcntl.flock(workspace_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError: raise ProjectFault('Another worker holds this project workspace.', 409) from None
        yield
    finally:
        if workspace_lock: workspace_lock.close()
        lifetime.close()
