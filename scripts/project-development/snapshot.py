"""Bounded no-follow capture, including uncommitted files, before a build."""
from collections import defaultdict
import hashlib
import os
from pathlib import Path
import shutil
import stat

from contracts import DevelopmentFault, LIMITS, hash_value, relative
from jobs import folder
from layout import save, sync

EXCLUDED = {'.git', '.cache', '.zig-cache', 'zig-out', 'zig-pkg', 'target', 'build', '.R4OSRust', 'node_modules'}


def signature(info): return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode)


def inventory(root, inputs=None):
    from sdk_inputs import read, git_roots, git_metadata
    roots = git_roots(inputs if inputs is not None else read(root))
    result = {}
    folders = []
    observed = {'bytes':0, 'files':0, 'directories':0}
    contributions = defaultdict(lambda: {'bytes':0, 'files':0, 'directories':0})

    def count(path, field, amount, directory=False):
        observed[field] += amount
        group = path.split('/', 1)[0] if directory or '/' in path else '.'
        contributions[group][field] += amount

    def refuse(kind, field, measured, maximum, path):
        raise BuildInputLimit(kind, measured, maximum, path, observed, [
            {'path':key, **values} for key, values in
            sorted(contributions.items(), key=lambda item: (-item[1][field], item[0]))[:5]
        ])

    for base, directories, files, fd in os.fwalk(root, follow_symlinks=False):
        def included(name):
            path = str((Path(base) / name).relative_to(root))
            # Root ExFiles is local reference data, outside the build input.
            return path != 'ExFiles' and (name not in EXCLUDED or name == '.git') and git_metadata(path, roots)
        directories[:] = sorted(name for name in directories if included(name))
        for name in directories:
            if not stat.S_ISDIR(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
                raise DevelopmentFault('Linked project directories cannot be captured.')
            path = relative(str((Path(base) / name).relative_to(root)))
            if len(path.encode()) > 240: raise DevelopmentFault('A project input path exceeds 240 UTF-8 bytes.')
            count(path, 'directories', 1, directory=True)
            if observed['directories'] > LIMITS['inputFiles']:
                refuse('directories', 'directories', observed['directories'], LIMITS['inputFiles'], path)
            folders.append(path)
        for name in sorted(files):
            path = relative(str((Path(base) / name).relative_to(root)))
            if not git_metadata(path, roots):
                continue
            if len(path.encode()) > 240: raise DevelopmentFault('A project input path exceeds 240 UTF-8 bytes.')
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise DevelopmentFault('Linked, hardlinked or special project files cannot be captured.')
            count(path, 'bytes', info.st_size)
            count(path, 'files', 1)
            if info.st_size > LIMITS['fileBytes']:
                refuse('fileBytes', 'bytes', info.st_size, LIMITS['fileBytes'], path)
            if observed['bytes'] > LIMITS['inputBytes']:
                refuse('inputBytes', 'bytes', observed['bytes'], LIMITS['inputBytes'], path)
            if observed['files'] > LIMITS['inputFiles']:
                refuse('inputFiles', 'files', observed['files'], LIMITS['inputFiles'], path)
            result[path] = signature(info)
    if 'module.R4MF' not in result: raise DevelopmentFault('The project manifest is missing.')
    return result, sorted(folders)


class BuildInputLimit(DevelopmentFault):
    def __init__(self, kind, measured, maximum, path, observed, directories):
        label = {'fileBytes':'Single input file bytes', 'inputBytes':'Total input bytes',
                 'inputFiles':'Input file count', 'directories':'Input directory count'}[kind]
        super().__init__(f'{label} exceeded ({measured} > {maximum}) at {path}. '
                         'The scan stopped at this limit. Counts are partial. The compiler did not start.',
                         reason_code='build_input_limit')
        self.diagnosis = {'limit':kind, 'maximum':maximum, 'measured':measured, 'path':path,
                          'observed':dict(observed), 'partial':True, 'topDirectories':directories,
                          'excludedDirectories':sorted(EXCLUDED - {'.git'}), 'excludedRootPaths':['ExFiles'],
                          'gitMetadata':'Only required declared SDK input metadata is included.',
                          'compilerStarted':False, 'compilerReceipt':None}


def checked_inventory(store, job, inputs):
    try: return inventory(store.workspace, inputs)
    except BuildInputLimit as error:
        store.update(job['id'], buildInputLimit=error.diagnosis, reasonCode=error.reason_code)
        raise


def capture(store, job):
    from sdk_inputs import read, verify_inventory
    inputs = read(store.workspace)
    if job.get('sdkInputs') != inputs:
        raise DevelopmentFault('SDK input selection changed after this build was accepted. Start a new build explicitly.')
    before, directories = checked_inventory(store, job, inputs)
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
                    executable = bool(expected[5] & 0o111)
                    files.append({'path': path, 'bytes': expected[2], 'sha256': checksum.hexdigest(), 'executable': executable})
                    target.chmod(0o500 if executable else 0o400)
            finally:
                for fd in reversed(descriptors): os.close(fd)
        if checked_inventory(store, job, inputs) != (before, directories): raise DevelopmentFault('Project changed while its build input was captured. Retry explicitly.')
        verify_inventory(inputs, files)
        value = {'id': job['id'], 'sha256': hash_value({'files': files, 'directories': directories}),
                 'manifestSha256': next(item['sha256'] for item in files if item['path'] == 'module.R4MF'),
                 'files': files, 'directories': directories, 'pins': job['pins']}
        # Identity is outside the source tree so it cannot shadow a user file.
        save(parent / (job['id'] + '.json'), value)
        sync(temp); os.rename(temp, final); sync(parent)
        return value, final
    finally: os.close(rootfd)
