"""Descriptor-relative cleanup files. No links, replacement or foreign targets."""
from contextlib import contextmanager
import codecs
import ctypes
import errno
import hashlib
import os
from pathlib import PurePosixPath
import stat
import uuid

from layout import workspace
from storage import RoadmapFault

MAX_DOCUMENT = 4 * 1024 * 1024
MAX_BASELINE = 64 * 1024 * 1024


def signature(info):
    return {'device': info.st_dev, 'inode': info.st_ino}


def names(descriptor):
    entries = os.listdir(descriptor)
    if len(entries) > 1024 or len({v.casefold() for v in entries}) != len(entries):
        raise RoadmapFault('Docs has too many entries or ambiguous filenames. All files were preserved.', 409)
    return entries


def directory(parent, name, create=False):
    if any(v.casefold() == name.casefold() and v != name for v in names(parent)):
        raise RoadmapFault('Resolve the conflicting Docs directory capitalization first.', 409)
    try: return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    except FileNotFoundError:
        if not create: raise
        try: os.mkdir(name, 0o700, dir_fd=parent); os.fsync(parent)
        except FileExistsError: pass
        return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    except OSError: raise RoadmapFault('Docs directories must be ordinary directories, without links.', 409) from None


def file_hash(parent, name, maximum=MAX_DOCUMENT, utf8=False):
    try: fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    except FileNotFoundError: raise
    except OSError: raise RoadmapFault('A cleanup file is unavailable or a link. Existing files were preserved.', 409) from None
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > maximum:
            raise RoadmapFault('Cleanup needs ordinary, singly linked files within its byte limit.', 409)
        digest, count = hashlib.sha256(), 0
        decoder = codecs.getincrementaldecoder('utf-8')() if utf8 else None
        try:
            while chunk := stream.read(65536):
                count += len(chunk)
                if count > maximum: raise RoadmapFault('A cleanup file grew beyond its byte limit.', 413)
                digest.update(chunk)
                if decoder: decoder.decode(chunk)
            if decoder: decoder.decode(b'', final=True)
        except UnicodeError: raise RoadmapFault('Knowledge documentation must contain valid UTF-8 text.', 409) from None
        after = os.fstat(fd)
        observed = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if observed(before) != observed(after) or count != after.st_size:
            raise RoadmapFault('A cleanup file changed while being checked. Retry its original workflow.', 409)
        named = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if observed(named) != observed(after): raise RoadmapFault('The checked cleanup file was replaced concurrently.', 409)
        return {'sha256': digest.hexdigest(), 'byteLength': count, **signature(after)}


@contextmanager
def root(projects, project_id, expected=None):
    path = workspace(projects, project_id, require_current=True)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        current = signature(os.fstat(fd))
        if signature(path.stat()) != current or (expected is not None and current != expected):
            raise RoadmapFault('The original cleanup workspace changed. Preserve files and reconcile the workflow.', 409)
        yield fd, current
        if signature(path.stat()) != current:
            raise RoadmapFault('The cleanup workspace was replaced concurrently.', 409)
    finally: os.close(fd)


def baseline(root_fd):
    result, total = {}, 0
    try: docs = directory(root_fd, 'Docs')
    except FileNotFoundError: return result

    def walk(fd, prefix, depth):
        nonlocal total
        if depth > 12: raise RoadmapFault('Docs exceeds the cleanup depth limit.', 413)
        for name in sorted(names(fd)):
            if '/' in name or '\\' in name or name in ('.', '..') or any(ord(c) < 32 for c in name):
                raise RoadmapFault('Resolve unsupported Docs filenames before cleanup.', 409)
            if prefix == 'Docs' and name.casefold() == 'changelogs':
                if name != 'Changelogs': raise RoadmapFault('Resolve Changelogs capitalization first.', 409)
                child = directory(fd, name); os.close(child)
                continue
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            path = prefix + '/' + name
            if stat.S_ISDIR(info.st_mode):
                child = directory(fd, name)
                try: walk(child, path, depth + 1)
                finally: os.close(child)
            else:
                if len(result) >= 512: raise RoadmapFault('Docs exceeds the cleanup baseline file limit.', 413)
                value = file_hash(fd, name); total += value['byteLength']
                if total > MAX_BASELINE: raise RoadmapFault('Docs exceeds the cleanup baseline byte limit.', 413)
                result[path] = value
    try: walk(docs, 'Docs', 0)
    finally: os.close(docs)
    return result


def archive(root_fd, stream, info, temporary, check, create=True):
    check()
    try:
        docs = directory(root_fd, 'Docs', create=create)
        try:
            check()
            changelogs = directory(docs, 'Changelogs', create=create)
        finally: os.close(docs)
    except FileNotFoundError:
        raise RoadmapFault('The confirmed archive directory is missing. Reconcile it without recreating files.', 409) from None
    try:
        filename = info['filename']
        if filename not in names(changelogs) and any(v.casefold() == filename.casefold() for v in names(changelogs)):
            raise RoadmapFault('A conflicting archive filename exists. It was preserved.', 409)
        try:
            existing = file_hash(changelogs, filename, 96 * 1024 * 1024)
            if existing['sha256'] != info['sha256'] or existing['byteLength'] != info['byteLength']:
                raise RoadmapFault('A different archive already exists. Preserve it and reconcile this workflow.', 409)
            return {'path': 'Docs/Changelogs/' + filename, **existing}
        except FileNotFoundError:
            if not create: raise RoadmapFault('The confirmed archive is missing. Reconcile it without recreating files.', 409) from None
        # An interrupted own stage is preserved. Its journalled name is never
        # overwritten; a fresh attempt can publish only the same full archive.
        check()
        staged = [os.stat(v, dir_fd=changelogs, follow_symlinks=False) for v in names(changelogs)
                  if v.startswith('.roadmap-') and v.endswith('.tmp')]
        if any(not stat.S_ISREG(v.st_mode) or v.st_nlink != 1 for v in staged) or sum(v.st_size for v in staged) + info['byteLength'] > 192 * 1024 * 1024:
            raise RoadmapFault('Cleanup staging needs maintenance. Existing staged files were preserved.', 413)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=changelogs)
        digest, size = hashlib.sha256(), 0
        with os.fdopen(fd, 'wb') as output:
            stream.seek(0)
            while chunk := stream.read(65536):
                size += len(chunk)
                if size > info['byteLength']: raise RoadmapFault('The original archive grew unexpectedly.', 409)
                output.write(chunk); digest.update(chunk)
            output.flush(); os.fsync(output.fileno())
        if size != info['byteLength'] or digest.hexdigest() != info['sha256']:
            raise RoadmapFault('The full archive checksum did not match. Original files were preserved.', 409)
        check()
        rename = ctypes.CDLL(None, use_errno=True).renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(changelogs, temporary.encode(), changelogs, filename.encode(), 1):
            code = ctypes.get_errno()
            if code != errno.EEXIST: raise OSError(code, 'Archive publication failed.')
        os.fsync(changelogs)
        saved = file_hash(changelogs, filename, 96 * 1024 * 1024)
        if saved['sha256'] != info['sha256'] or saved['byteLength'] != info['byteLength']:
            raise RoadmapFault('The archive changed during publication. All files were preserved.', 409)
        return {'path': 'Docs/Changelogs/' + filename, **saved}
    finally: os.close(changelogs)


def document_parts(path):
    if (not isinstance(path, str) or len(path.encode()) > 1024 or '\\' in path
            or any(ord(c) < 32 or ord(c) == 127 for c in path)):
        raise RoadmapFault('Select a regular UTF-8 document under Docs/.', 400)
    parts = PurePosixPath(path).parts
    if (len(parts) < 2 or len(parts) > 14 or parts[0] != 'Docs' or any(v in ('.', '..') for v in parts)
            or '/'.join(parts) != path or parts[1].casefold() == 'changelogs'):
        raise RoadmapFault('Knowledge receipts must select canonical files under Docs/, outside Changelogs.', 400)
    return parts


def document(root_fd, path):
    parts = document_parts(path)
    fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = directory(fd, part); os.close(fd); fd = child
        if any(v.casefold() == parts[-1].casefold() and v != parts[-1] for v in names(fd)):
            raise RoadmapFault('The document filename is ambiguous.', 409)
        return file_hash(fd, parts[-1], utf8=True)
    finally: os.close(fd)


def temporary_name(workflow_id):
    return '.roadmap-' + workflow_id + '-' + str(uuid.uuid4()) + '.tmp'
