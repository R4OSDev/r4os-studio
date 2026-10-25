"""Bounded UTF-8 file tools. Runs only inside the project Bubblewrap namespace."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import uuid


class Fault(Exception): pass


def parts(path):
    if (not isinstance(path, str) or len(path) > 1024 or path.startswith('/') or '\\' in path
        or any(ord(c) < 32 or ord(c) == 127 for c in path)):
        raise Fault('Use a relative path inside the selected root.')
    result = path.split('/')
    if '..' in result: raise Fault('Parent path traversal is unavailable.')
    return [v for v in result if v not in ('', '.')]


def root_fd(name):
    if name not in ('workspace', 'sdk', 'contract', 'zig', 'rust'): raise Fault('Unknown file root.')
    return os.open('/' + name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def parent(root, path, create=False):
    names = parts(path)
    if not names: raise Fault('Select a file or subdirectory.')
    fd = os.dup(root)
    try:
        for name in names[:-1]:
            if create:
                try:
                    os.mkdir(name, 0o755, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError: pass
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        return fd, names[-1]
    except BaseException:
        os.close(fd); raise


def directory(root, path):
    fd = os.dup(root)
    try:
        for name in parts(path):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd); raise


def read(root, path, limit=8*1024*1024):
    par, name = parent(root, path)
    try: fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=par)
    finally: os.close(par)
    with os.fdopen(fd, 'rb') as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit: raise Fault('Select a regular file within the size limit.')
        value = f.read(limit+1)
        if len(value) > limit: raise Fault('File size limit exceeded.')
        return value, info


def sha(value): return hashlib.sha256(value).hexdigest()


def check(root, path, expected):
    try: value, info = read(root, path)
    except FileNotFoundError:
        if expected is not None: raise Fault('File disappeared. Read the current file before changing it.')
        return None
    if not isinstance(expected, str) or not re.fullmatch('[a-f0-9]{64}', expected) or sha(value) != expected:
        raise Fault('File changed. Read the current file before changing it.')
    return info


def patch(root, args):
    text = args['patch']; hashes = args['expectedHashes']; targets = []
    lines = text.strip().splitlines()
    if not lines or lines[0] != '*** Begin Patch' or lines[-1] != '*** End Patch': raise Fault('Supply a Codex-format patch.')
    for line in lines:
        for prefix, role in [('*** Add File: ', 'new'), ('*** Delete File: ', 'old'), ('*** Update File: ', 'old'), ('*** Move to: ', 'new')]:
            if line.startswith(prefix):
                path = line[len(prefix):]; parts(path); targets.append(path)
                if role == 'old' and path not in hashes: raise Fault('Supply an expected hash for every existing source file.')
                check(root, path, hashes.get(path))
                # Existing parents must be real directories. New patch parents
                # are created by the official engine inside the confined root.
                names = parts(path)
                fd = os.dup(root)
                try:
                    for name in names[:-1]:
                        try: child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                        except FileNotFoundError: break
                        os.close(fd); fd = child
                finally: os.close(fd)
    if not targets or len(targets) > 64: raise Fault('Patch must contain between one and 64 file entries.')
    result = subprocess.run(['/runner/codex', '--codex-run-as-apply-patch', text], capture_output=True, timeout=15, cwd='/workspace', env={'PATH': '/usr/bin:/bin', 'HOME': '/home/studio'})
    changed = {}
    for path in dict.fromkeys(targets):
        try: changed[path] = sha(read(root, path)[0])
        except FileNotFoundError: changed[path] = None
        except (OSError, Fault): changed[path] = 'unavailable'
    return {'success': result.returncode == 0, 'output': (result.stdout+result.stderr).decode('utf8', 'replace')[:24000],
            'files': changed, **({'error': 'patchFailed', 'partialChangesPossible': True} if result.returncode else {})}


class SearchFault(Fault):
    def __init__(self, message, reason):
        super().__init__(message); self.reason = reason


def search(root, args):
    base = args.get('path', '.'); names = parts(base)
    try:
        if not names: selected = os.dup(root)
        else:
            par, name = parent(root, base)
            try:
                before = os.stat(name, dir_fd=par, follow_symlinks=False)
                if not (stat.S_ISREG(before.st_mode) or stat.S_ISDIR(before.st_mode)):
                    raise SearchFault('Search requires a regular file or directory; links and special files are unavailable.', 'unsupportedSearchType')
                selected = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=par)
                actual = os.fstat(selected)
                if (before.st_dev, before.st_ino) != (actual.st_dev, actual.st_ino):
                    os.close(selected); raise SearchFault('The search path changed. Read its current state before searching again.', 'searchPathChanged')
            finally: os.close(par)
        try: initial = os.fstat(selected)
        finally: os.close(selected)
    except FileNotFoundError:
        raise SearchFault('The search file or directory does not exist.', 'searchPathMissing') from None
    except NotADirectoryError:
        raise SearchFault('A search parent is not a directory.', 'invalidSearchParent') from None
    is_file = stat.S_ISREG(initial.st_mode)
    if not is_file and not stat.S_ISDIR(initial.st_mode):
        raise SearchFault('Search requires a regular file or directory.', 'unsupportedSearchType')
    query = args['query']; results = []; scanned = 0; used = 0; rendered = 0; skipped = 0
    visited = 0; entries = 0; truncated = False; limited = False
    deadline = time.monotonic() + 10

    def append(value):
        nonlocal rendered, limited
        size = len(json.dumps(value, ensure_ascii=False).encode()) + 2
        if len(results) >= 100 or rendered + size > 60000:
            limited = True; return False
        results.append(value); rendered += size
        return True

    def scan(path, info):
        nonlocal scanned, used, skipped, truncated, limited
        scanned += 1
        if len(path.encode()) > 1024:
            skipped += 1; return
        if args.get('filenames'):
            if query in path.rsplit('/', 1)[-1]: append({'path': path})
            return
        if info.st_size > min(262144, 8*1024*1024 - used):
            skipped += 1; return
        try:
            content, opened = read(root, path, min(262144, 8*1024*1024 - used)); used += len(content)
            if b'\x00' in content:
                skipped += 1; return
            par, name = parent(root, path)
            try: after = os.stat(name, dir_fd=par, follow_symlinks=False)
            finally: os.close(par)
            fingerprint = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
            if fingerprint(info) != fingerprint(opened) or fingerprint(opened) != fingerprint(after):
                skipped += 1; return
            text = content.decode('utf8')
        except (UnicodeError, OSError, Fault):
            skipped += 1; return
        for index, line in enumerate(text.splitlines(), 1):
            if time.monotonic() >= deadline:
                limited = True; return
            if query in line and not append({'path': path, 'line': index, 'text': line[:500]}): return

    if is_file: scan(base, initial)
    else:
        stack = [base]
        while stack and not limited:
            if scanned >= 2000 or used >= 8*1024*1024 or visited >= 2000 or entries >= 20000 or time.monotonic() >= deadline:
                truncated = True; break
            relative = stack.pop()
            try: fd = directory(root, relative)
            except (OSError, Fault):
                skipped += 1; continue
            visited += 1
            try:
                values = os.listdir(fd)
                if len(values) > 10000:
                    truncated = True; continue
                for name in sorted(values):
                    entries += 1
                    if entries > 20000 or scanned >= 2000 or used >= 8*1024*1024 or limited or time.monotonic() >= deadline:
                        truncated = True; limited = True; break
                    path = relative.rstrip('/') + '/' + name
                    try: info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    except OSError:
                        skipped += 1; continue
                    if stat.S_ISDIR(info.st_mode):
                        if name not in ('.git', '.studio-cache', '.zig-cache', 'target', 'node_modules'):
                            if len(stack) < 2000 and len(path.encode()) <= 1024: stack.append(path)
                            else: truncated = True
                    elif stat.S_ISREG(info.st_mode): scan(path, info)
                    else: skipped += 1
            finally: os.close(fd)
        truncated = truncated or bool(stack)
    return {'success': True, 'output': json.dumps(results, ensure_ascii=False),
            'truncated': truncated or limited or bool(skipped), 'skippedFiles': skipped}


def execute(tool, args):
    root_name = args.get('root', 'workspace'); root = root_fd(root_name)
    try:
        if tool == 'read_file':
            data, _ = read(root, args['path']); lines = data.decode('utf8').splitlines()
            start = args.get('startLine', 1); selected = lines[start-1:start-1+args.get('maxLines', 200)]
            rendered = []; used = 0; next_line = None; line_truncated = None
            for index, line in enumerate(selected, start):
                raw = f'{index}: {line}'.encode()
                if used + len(raw) + bool(rendered) > 60000:
                    if rendered: next_line = index
                    else:
                        rendered.append(raw[:60000].decode('utf8', 'ignore')); line_truncated = index
                        next_line = index+1 if index < len(lines) else None
                    break
                rendered.append(raw.decode()); used += len(raw) + (len(rendered)>1)
            else:
                end = start+len(selected)
                next_line = end if end <= len(lines) else None
            return {'success': True, 'output': '\n'.join(rendered), 'sha256': sha(data), 'totalLines': len(lines),
                    'truncated': next_line is not None or line_truncated is not None, 'nextLine': next_line,
                    'lineTruncated': line_truncated}
        if tool == 'list_directory':
            fd = directory(root, args['path'])
            try:
                names = sorted(os.listdir(fd)); offset = args.get('offset', 0)
                if len(names) > 10000: raise Fault('Directory entry limit exceeded.')
                values = []
                for name in names[offset:offset+100]:
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    values.append({'name': name, 'type': 'directory' if stat.S_ISDIR(info.st_mode) else ('file' if stat.S_ISREG(info.st_mode) else 'linkOrSpecial'), 'bytes': info.st_size})
                return {'success': True, 'output': json.dumps(values, ensure_ascii=False), 'nextOffset': offset+100 if offset+100 < len(names) else None}
            finally: os.close(fd)
        if tool == 'search': return search(root, args)
        if root_name != 'workspace': raise Fault('This component root is read-only.')
        if tool == 'write_file':
            content = args['content'].encode()
            if len(content) > 65536: raise Fault('File write limit exceeded.')
            info = check(root, args['path'], args['expectedSha256']); par, name = parent(root, args['path'])
            temp = '.studio-write-' + uuid.uuid4().hex
            try:
                fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, stat.S_IMODE(info.st_mode) if info else 0o644, dir_fd=par)
                with os.fdopen(fd, 'wb') as f: f.write(content); f.flush(); os.fsync(f.fileno())
                check(root, args['path'], args['expectedSha256'])
                if info: os.replace(temp, name, src_dir_fd=par, dst_dir_fd=par)
                else: os.link(temp, name, src_dir_fd=par, dst_dir_fd=par, follow_symlinks=False); os.unlink(temp, dir_fd=par)
                os.fsync(par)
            finally:
                try: os.unlink(temp, dir_fd=par)
                except FileNotFoundError: pass
                os.close(par)
            return {'success': True, 'output': 'File written.', 'sha256': sha(content)}
        if tool == 'create_directory':
            par, name = parent(root, args['path'], True)
            try:
                try: os.mkdir(name, 0o755, dir_fd=par)
                except FileExistsError:
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=par); os.close(child)
                os.fsync(par)
            finally: os.close(par)
            return {'success': True, 'output': 'Directory created.'}
        if tool == 'apply_patch': return patch(root, args)
        raise Fault('Unknown file tool.')
    finally: os.close(root)


def failure(tool, error):
    uncertain = tool in ('write_file', 'apply_patch', 'create_directory') and isinstance(error, (OSError, subprocess.SubprocessError))
    return {'success': False, 'error': 'unknown' if uncertain else 'fileError', 'output': str(error)[:1000],
            **({'partialChangesPossible': True} if uncertain else {}),
            **({'reasonCode': error.reason} if isinstance(error, SearchFault) else {})}


if __name__ == '__main__':
    value = {}
    try:
        value = json.load(sys.stdin)
        result = execute(value['tool'], value['arguments'])
    except (Fault, UnicodeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
        result = failure(value.get('tool'), e)
    print(json.dumps(result, ensure_ascii=False))
