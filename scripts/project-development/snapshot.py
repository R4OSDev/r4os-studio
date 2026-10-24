"""Bounded no-follow capture, including uncommitted files, before a build."""
import hashlib
import os
from pathlib import Path
import shutil
import stat

from contracts import DevelopmentFault, LIMITS, hash_value, relative
from jobs import folder
from layout import save, sync

EXCLUDED = {'.git', '.zig-cache', 'zig-out', 'zig-pkg', 'target', 'build', '.R4OSRust', 'node_modules'}


def signature(info): return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def inventory(root):
    result = {}; total = 0; folders = []
    for base, directories, files, fd in os.fwalk(root, follow_symlinks=False):
        directories[:] = sorted(name for name in directories if name not in EXCLUDED)
        for name in directories:
            if not stat.S_ISDIR(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
                raise DevelopmentFault('Linked project directories cannot be captured.')
            path = relative(str((Path(base) / name).relative_to(root)))
            if len(path.encode()) > 240 or len(folders) >= LIMITS['inputFiles']:
                raise DevelopmentFault('Project directories exceed the build input limit.')
            folders.append(path)
        for name in sorted(files):
            path = relative(str((Path(base) / name).relative_to(root)))
            if len(path.encode()) > 240: raise DevelopmentFault('A project input path exceeds 240 UTF-8 bytes.')
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise DevelopmentFault('Linked, hardlinked or special project files cannot be captured.')
            total += info.st_size
            if info.st_size > LIMITS['fileBytes'] or total > LIMITS['inputBytes'] or len(result) >= LIMITS['inputFiles']:
                raise DevelopmentFault('Project sources exceed the build input limit.')
            result[path] = signature(info)
    if 'module.R4MF' not in result: raise DevelopmentFault('The project manifest is missing.')
    return result, sorted(folders)


def capture(store, job):
    before, directories = inventory(store.workspace)
    parent = folder(store.root / 'Inputs'); final = parent / job['id']; temp = parent / (job['id'] + '.new')
    if final.exists() or temp.exists(): raise DevelopmentFault('This build input already exists; it was preserved.')
    folder(temp); files = []
    for path in directories: folder(temp / path)
    rootfd = os.open(store.workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for path, expected in sorted(before.items()):
            descriptors = []; fd = rootfd
            try:
                parts = path.split('/')
                for part in parts[:-1]:
                    fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd); descriptors.append(fd)
                source = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                with os.fdopen(source, 'rb') as src:
                    if signature(os.fstat(src.fileno())) != expected: raise DevelopmentFault('Project changed while its build input was captured. Retry explicitly.')
                    target = temp / path; folder(target.parent)
                    checksum = hashlib.sha256()
                    with target.open('xb') as dst:
                        remaining = expected[2]
                        while remaining:
                            data = src.read(min(65536, remaining))
                            if not data: raise DevelopmentFault('Project changed while its build input was captured. Retry explicitly.')
                            dst.write(data); checksum.update(data); remaining -= len(data)
                        if src.read(1): raise DevelopmentFault('Project changed while its build input was captured. Retry explicitly.')
                        dst.flush(); os.fsync(dst.fileno())
                    if signature(os.fstat(src.fileno())) != expected or target.stat().st_size != expected[2]:
                        raise DevelopmentFault('Project changed while its build input was captured. Retry explicitly.')
                    files.append({'path': path, 'bytes': expected[2], 'sha256': checksum.hexdigest()})
                    target.chmod(0o400)
            finally:
                for fd in reversed(descriptors): os.close(fd)
        if inventory(store.workspace) != (before, directories): raise DevelopmentFault('Project changed while its build input was captured. Retry explicitly.')
        value = {'id': job['id'], 'sha256': hash_value({'files': files, 'directories': directories}),
                 'manifestSha256': next(item['sha256'] for item in files if item['path'] == 'module.R4MF'),
                 'files': files, 'directories': directories, 'pins': job['pins']}
        # Identity is outside the source tree so it cannot shadow a user file.
        save(parent / (job['id'] + '.json'), value)
        sync(temp); os.rename(temp, final); sync(parent)
        return value, final
    finally: os.close(rootfd)
