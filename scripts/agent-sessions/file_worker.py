"""Bounded UTF-8 file tools using the current workspace and ordinary host paths."""
import hashlib
from functools import lru_cache
import json
import os
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from workspace_context import Workspace
import re
import stat
import subprocess
import time
import uuid


class Fault(Exception): pass


def parts(path):
    if not isinstance(path, str) or len(path) > 4096 or '\x00' in path:
        raise Fault('Supply a valid file path.')
    return list(Path(path).parts)


def context():
    return working_context(os.environ.get('STUDIO_WORKSPACE',os.getcwd()),os.environ.get('STUDIO_PATHS','{}'))


@lru_cache(maxsize=4)
def working_context(workspace,paths):
    return Workspace(workspace,json.loads(paths))


def root_fd(name):
    if name not in ('workspace', 'sdk', 'contract', 'zig', 'rust'): raise Fault('Unknown file root.')
    selected = context().paths.get('/' + name)
    if selected is None: raise Fault('The selected component is unavailable.')
    return os.open(selected, os.O_RDONLY | os.O_DIRECTORY)


def selected(root, path):
    parts(path)
    value = Path(path)
    if value.is_absolute(): return context().path(value).resolve()
    # dirfd stays local to this request; no global cwd is changed.
    base = Path(os.readlink('/proc/self/fd/' + str(root)))
    working = context()
    for alias, target in working.paths.items():
        if target == base: return working.path(alias + '/' + str(value)).resolve()
    return (base / value).resolve()


def parent(root, path, create=False):
    target = selected(root, path)
    if not target.name: raise Fault('Select a file or subdirectory.')
    if create: target.parent.mkdir(parents=True, exist_ok=True)
    return os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY), target.name


def directory(root, path):
    return os.open(selected(root, path), os.O_RDONLY | os.O_DIRECTORY)


def read(root, path, limit=8*1024*1024):
    par, name = parent(root, path)
    try: fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK, dir_fd=par)
    finally: os.close(par)
    with os.fdopen(fd, 'rb') as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit: raise Fault('Select a regular file within the size limit.')
        value = f.read(limit+1)
        if len(value) > limit: raise Fault('File size limit exceeded.')
        return value, info


def sha(value): return hashlib.sha256(value).hexdigest()


def generation(info):
    return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns


def file_lines(root,path,cache):
    if cache is not None and cache.get('generation')==generation(selected(root,path).stat()):
        return cache['lines'],cache['hash']
    data,info=read(root,path)
    lines=data.decode('utf8').splitlines(); checksum=sha(data)
    if cache is not None:
        cache.clear()
        if len(data)<=2*1024*1024 and len(lines)<=100000 and generation(info)==generation(selected(root,path).stat()):
            cache.update(generation=generation(info),lines=lines,hash=checksum)
    return lines,checksum


def validate_expected(expected):
    if expected is not None and (not isinstance(expected,str) or not re.fullmatch('[a-f0-9]{64}',expected)):
        raise Fault('Use JSON null for a new file, or the exact lowercase 64-character SHA-256 read from an existing file. The string "null" is not JSON null. No file was written.')


def check(root, path, expected):
    validate_expected(expected)
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
    if not targets or len(targets) > 64: raise Fault('Patch must contain between one and 64 file entries.')
    translated = []
    for line in text.splitlines():
        for prefix in ('*** Add File: ', '*** Delete File: ', '*** Update File: ', '*** Move to: '):
            if line.startswith(prefix):
                line = prefix + str(selected(root, line[len(prefix):])); break
        translated.append(line)
    text = '\n'.join(translated)
    result = subprocess.run([os.environ['STUDIO_PATCH_BINARY'], '--codex-run-as-apply-patch', text], capture_output=True, timeout=15, cwd=os.readlink('/proc/self/fd/' + str(root)), env=dict(os.environ))
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
                before = os.stat(name, dir_fd=par, follow_symlinks=True)
                if not (stat.S_ISREG(before.st_mode) or stat.S_ISDIR(before.st_mode)):
                    raise SearchFault('Search requires a regular file or directory; special files are unavailable.', 'unsupportedSearchType')
                selected = os.open(name, os.O_RDONLY | os.O_NONBLOCK, dir_fd=par)
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
            try: after = os.stat(name, dir_fd=par, follow_symlinks=True)
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
        stack = [base]; seen = set()
        while stack and not limited:
            if scanned >= 2000 or used >= 8*1024*1024 or visited >= 2000 or entries >= 20000 or time.monotonic() >= deadline:
                truncated = True; break
            relative = stack.pop()
            try: fd = directory(root, relative)
            except (OSError, Fault):
                skipped += 1; continue
            identity = os.fstat(fd)
            key = (identity.st_dev, identity.st_ino)
            if key in seen: os.close(fd); continue
            seen.add(key); visited += 1
            try:
                values = os.listdir(fd)
                if len(values) > 10000:
                    truncated = True; continue
                for name in sorted(values):
                    entries += 1
                    if entries > 20000 or scanned >= 2000 or used >= 8*1024*1024 or limited or time.monotonic() >= deadline:
                        truncated = True; limited = True; break
                    path = relative.rstrip('/') + '/' + name
                    try: info = os.stat(name, dir_fd=fd, follow_symlinks=True)
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


def execute(tool, args, cache=None):
    if tool == 'write_file': validate_expected(args.get('expectedSha256'))
    root_name = args.get('root', 'workspace'); root = root_fd(root_name)
    try:
        if tool == 'read_file':
            lines,checksum=file_lines(root,args['path'],cache)
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
            return {'success': True, 'output': '\n'.join(rendered), 'sha256': checksum, 'totalLines': len(lines),
                    'truncated': next_line is not None or line_truncated is not None, 'nextLine': next_line,
                    'lineTruncated': line_truncated}
        if tool == 'list_directory':
            fd = directory(root, args['path'])
            try:
                names = sorted(os.listdir(fd)); offset = args.get('offset', 0)
                if len(names) > 10000: raise Fault('Directory entry limit exceeded.')
                values = []
                for name in names[offset:offset+100]:
                    info = os.stat(name, dir_fd=fd, follow_symlinks=True)
                    values.append({'name': name, 'type': 'directory' if stat.S_ISDIR(info.st_mode) else ('file' if stat.S_ISREG(info.st_mode) else 'linkOrSpecial'), 'bytes': info.st_size})
                return {'success': True, 'output': json.dumps(values, ensure_ascii=False), 'nextOffset': offset+100 if offset+100 < len(names) else None}
            finally: os.close(fd)
        if tool == 'search': return search(root, args)
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
                else: os.link(temp, name, src_dir_fd=par, dst_dir_fd=par, follow_symlinks=True); os.unlink(temp, dir_fd=par)
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
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY, dir_fd=par); os.close(child)
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


def response(raw,cache=None):
    value = {}
    try:
        value = json.loads(raw)
        if cache is not None and value['tool'] not in ('read_file','list_directory','search'):
            raise Fault('The file reader accepts only read operations.')
        return execute(value['tool'],value['arguments'],cache)
    except (Fault, UnicodeError, OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as e:
        return failure(value.get('tool'),e)


if __name__ == '__main__':
    if sys.argv[1:]==['--serve']:
        cache={}
        for raw in sys.stdin.buffer:
            print(json.dumps(response(raw,cache),ensure_ascii=False),flush=True)
    else:
        print(json.dumps(response(sys.stdin.buffer.read()),ensure_ascii=False))
