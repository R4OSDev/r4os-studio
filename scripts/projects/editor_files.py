"""Bounded descriptor-relative Workspace access. Never invokes an agent or shell."""
import hashlib
import errno
import json
import os
import stat
from layout import folder, project_directory
from project_maintenance import project
from store import ProjectFault

MAX_TEXT = 512 * 1024
MAX_ENTRIES = 10000
PAGE_SIZE = 100
MAX_OPEN = 20


def parts(path, root=False, new=False):
    try:
        valid = isinstance(path, str) and len(path.encode('utf-8')) <= (240 if new else 1024)
    except UnicodeError: valid = False
    if not valid or '\\' in path or ':' in path or any(ord(c) < 32 or ord(c) == 127 for c in path):
        raise ProjectFault('Use a valid relative Workspace path.', 400)
    if path == '' and root: return []
    result = path.split('/')
    if any(name in ('', '.', '..') for name in result):
        raise ProjectFault('Use a relative Workspace path without parent segments.', 400)
    return result


def root_path(projects, identity):
    project(projects, identity)
    base = project_directory(projects, identity)
    if (base / 'module.R4MF').exists() or (base / 'module.R4MF').is_symlink():
        raise ProjectFault('Resolve the legacy project layout before opening the editor.', 409)
    # Unlike build admission, an editor can repair a missing module.R4MF.
    return folder(base / 'Workspace')


def signature(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode, info.st_nlink]


def revision(info):
    return hashlib.sha256(json.dumps(signature(info)).encode()).hexdigest()


def directory(root, path):
    descriptor = os.dup(root)
    try:
        for name in parts(path, root=True):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor); descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor); raise


def parent(root, path):
    names = parts(path)
    return directory(root, '/'.join(names[:-1])), names[-1]


def metadata(path, info):
    kind = 'file' if stat.S_ISREG(info.st_mode) else 'directory' if stat.S_ISDIR(info.st_mode) else 'link' if stat.S_ISLNK(info.st_mode) else 'special'
    result = {'path': path, 'name': path.rsplit('/', 1)[-1], 'kind': kind, 'bytes': info.st_size,
              'revision': revision(info), 'editable': False}
    if kind in ('link', 'special'): result['reason'] = 'Linked and special files are unavailable in the editor.'
    elif kind == 'file' and info.st_nlink != 1: result['reason'] = 'Hardlinked files are unavailable in the editor.'
    return result


def node(root, path, content=False, byte_limit=MAX_TEXT):
    names = parts(path)
    missing = {'path': path, 'name': names[-1], 'kind': 'missing', 'editable': False,
               'reason': 'This file or its parent directory is no longer available.'}
    try: descriptor, name = parent(root, path)
    except OSError as error:
        if error.errno in (errno.ENOENT, errno.ENOTDIR, errno.ELOOP): return missing
        raise
    try:
        try: info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError: return {'path': path, 'name': name, 'kind': 'missing', 'editable': False, 'reason': 'This file no longer exists.'}
        result = metadata(path, info)
        if not content or result['kind'] != 'file' or info.st_nlink != 1: return result
        limit = min(MAX_TEXT, byte_limit)
        if info.st_size > limit:
            return {**result, 'reason': 'This file exceeds the 512 KiB text editor limit.'}
        file = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(file, 'rb') as stream:
            if signature(os.fstat(stream.fileno())) != signature(info):
                raise ProjectFault('The file changed while being read. Refresh it.', 409)
            raw = stream.read(limit + 1)
            if len(raw) > limit or signature(os.fstat(stream.fileno())) != signature(info):
                raise ProjectFault('The file changed while being read. Refresh it.', 409)
        if signature(os.stat(name, dir_fd=descriptor, follow_symlinks=False)) != signature(info):
            raise ProjectFault('The file changed while being read. Refresh it.', 409)
        result['sha256'] = hashlib.sha256(raw).hexdigest()
        try: text = raw.decode('utf-8')
        except UnicodeError: return {**result, 'reason': 'This file is not UTF-8 text.'}
        if any(ord(c) < 32 and c not in '\t\n\r' or ord(c) == 127 for c in text):
            return {**result, 'reason': 'Binary files cannot be edited as text.'}
        bom = text.startswith('\ufeff')
        if bom: text = text[1:]
        crlf, lf, cr = text.count('\r\n'), text.count('\n'), text.count('\r')
        eol = 'mixed' if cr != crlf or (crlf and lf != crlf) else 'crlf' if crlf else 'lf'
        result.update(text=text.replace('\r\n', '\n'), format={'bom': bom, 'eol': eol}, editable=eol != 'mixed')
        if eol == 'mixed': result['reason'] = 'Mixed line endings are opened read-only.'
        if path.casefold() == 'agents.md':
            from project_agents import validate
            if path != 'Agents.md' or any(n.casefold() == 'agents.md' and n != 'Agents.md' for n in os.listdir(root)):
                result.update(editable=False, reason='Resolve the conflicting Agents.md filename first.')
            else:
                try: validate(raw.decode('utf-8'))
                except ProjectFault as error: result.update(editable=False, reason=str(error))
        return result
    finally: os.close(descriptor)


def tree(root, path='', offset=0, expected=None):
    descriptor = directory(root, path)
    try:
        before = os.fstat(descriptor); stamp = revision(before)
        if expected is not None and expected != stamp:
            raise ProjectFault('The directory changed. Refresh it before loading more entries.', 409)
        names = []
        with os.scandir(descriptor) as entries:
            for entry in entries:
                names.append(entry.name)
                if len(names) > MAX_ENTRIES: raise ProjectFault('This directory exceeds the 10000-entry limit.', 413)
        names.sort(key=lambda name: (name.casefold(), name))
        selected = []
        for name in names[offset:offset + PAGE_SIZE]:
            relative = path + '/' + name if path else name
            value = metadata(relative, os.stat(name, dir_fd=descriptor, follow_symlinks=False))
            try: parts(relative)
            except ProjectFault: value.update(kind='special', reason='This filename is not supported by the editor.')
            selected.append(value)
        if signature(os.fstat(descriptor)) != signature(before):
            raise ProjectFault('The directory changed while being read. Refresh it.', 409)
        return {'path': path, 'revision': stamp, 'entries': selected,
                'nextOffset': offset + PAGE_SIZE if offset + PAGE_SIZE < len(names) else None}
    finally: os.close(descriptor)
