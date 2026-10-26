"""Materialize only regular, bounded Git blobs; never run checkout filters or repository hooks."""
import os
from pathlib import Path
import re
from common import ProjectFault, source_path, folder, MAX_FILES, MAX_FILE, MAX_BYTES, inventory, digest


def entries(git, commit):
    if not re.fullmatch('[a-f0-9]{40,64}', commit or ''): raise ProjectFault('Invalid source commit.', 400)
    raw = git.run('ls-tree', '-r', '-z', '--full-tree', commit)[0]
    result, folded = [], set()
    for entry in raw.split(b'\0'):
        if not entry: continue
        header, path = entry.split(b'\t', 1); mode, kind, oid = header.decode('ascii').split(' ')
        path = source_path(path.decode('utf8'))
        if mode not in ('100644', '100755') or kind != 'blob' or path == '.gitmodules':
            raise ProjectFault('Import supports regular files only; submodules and links need a separate adapter.', 409)
        if path.casefold() in folded: raise ProjectFault('Repository has conflicting filename case variants.', 409)
        folded.add(path.casefold()); result.append((path, mode, oid))
        if len(result) > MAX_FILES: raise ProjectFault('Repository exceeds the 10,000-file import limit.', 409)
    return result


def materialize(git, commit, destination):
    destination = folder(destination)
    if any(destination.iterdir()): raise ProjectFault('Import staging is not empty. Original data was preserved.', 409)
    total = 0
    for relative, mode, oid in entries(git, commit):
        size = int(git.text('cat-file', '-s', oid)); total += size
        if size > MAX_FILE or total > MAX_BYTES: raise ProjectFault('Repository exceeds import byte limits.', 409)
        raw = git.run('cat-file', 'blob', oid)[0]
        if len(raw) != size: raise ProjectFault('Git blob size changed.', 409)
        if raw.startswith(b'version https://git-lfs.github.com/spec/v1\n') and b'\noid sha256:' in raw:
            raise ProjectFault('Git LFS content is not supported by this import adapter.', 409)
        path = destination / relative; path.parent.mkdir(mode=0o700, parents=True, exist_ok=True); folder(path.parent)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o755 if mode == '100755' else 0o644)
        with os.fdopen(fd, 'wb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return digest(inventory(destination))
