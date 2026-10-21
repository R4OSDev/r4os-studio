"""Bounded UTF-8 file tools. Runs only inside the project Bubblewrap namespace."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
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
                try: os.mkdir(name, 0o755, dir_fd=fd)
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
        except OSError: changed[path] = 'unavailable'
    return {'success': result.returncode == 0, 'output': (result.stdout+result.stderr).decode('utf8', 'replace')[:24000],
            'files': changed, **({'error': 'patchFailed', 'partialChangesPossible': True} if result.returncode else {})}


def execute(tool, args):
    root_name = args.get('root', 'workspace'); root = root_fd(root_name)
    try:
        if tool == 'read_file':
            data, _ = read(root, args['path']); lines = data.decode('utf8').splitlines()
            start = args.get('startLine', 1); selected = lines[start-1:start-1+args.get('maxLines', 200)]
            output = '\n'.join(f'{i}: {s}' for i, s in enumerate(selected, start))
            truncated = len(output.encode()) > 60000
            return {'success': True, 'output': output.encode()[:60000].decode('utf8', 'ignore'), 'sha256': sha(data), 'totalLines': len(lines), 'truncated': truncated}
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
        if tool == 'search':
            query = args['query']; results = []; scanned = 0; used = 0; truncated = False
            base = args.get('path', '.'); fd = directory(root, base); os.close(fd)
            stack = [base]
            while stack and len(results) < 100 and scanned < 2000 and used < 8*1024*1024:
                relative = stack.pop(); fd = directory(root, relative)
                try:
                    names = sorted(os.listdir(fd))
                    if len(names) > 10000: truncated = True; continue
                    for name in names:
                        path = relative.rstrip('/') + '/' + name; info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                        if stat.S_ISDIR(info.st_mode):
                            if name not in ('.git', '.studio-cache', '.zig-cache', 'target', 'node_modules') and len(stack) < 2000: stack.append(path)
                        elif stat.S_ISREG(info.st_mode):
                            scanned += 1
                            if args.get('filenames'):
                                if query in name: results.append({'path': path})
                            elif info.st_size <= 262144:
                                try:
                                    content, _ = read(root, path, 262144); used += len(content)
                                    for index, line in enumerate(content.decode('utf8').splitlines(), 1):
                                        if query in line: results.append({'path': path, 'line': index, 'text': line[:500]})
                                        if len(results) >= 100: break
                                except (UnicodeError, OSError, Fault): pass
                        if len(results) >= 100 or scanned >= 2000 or used >= 8*1024*1024: truncated = True; break
                finally: os.close(fd)
            return {'success': True, 'output': json.dumps(results, ensure_ascii=False), 'truncated': truncated or bool(stack)}
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


if __name__ == '__main__':
    try:
        value = json.load(sys.stdin)
        result = execute(value['tool'], value['arguments'])
    except (Fault, UnicodeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
        result = {'success': False, 'error': 'fileError', 'output': str(e)[:1000]}
    print(json.dumps(result, ensure_ascii=False))
