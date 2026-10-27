"""Hash-bound local snapshots and create-only Workspace publication, no host paths."""
from contextlib import closing
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from catalog import CatalogFault, identity, regular, sync
from editor_files import parts, signature
from layout import workspace
from transport import private_directory
from sftp_client import MAX_FILE

PRIVATE = {'.git', '.studio', '.r4os-studio', '.studio-cache', '.codex'}


def sha(value): return hashlib.sha256(value).hexdigest()


def digest(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value): raise CatalogFault('Supply the confirmed lowercase SHA-256.', 400)
    return value


def relative(value):
    try: names = parts(value, new=True)
    except Exception: raise CatalogFault('Use a relative Workspace filename within240 UTF-8 bytes.', 400) from None
    if any(n.casefold() in PRIVATE or n.startswith('.studio-') for n in names): raise CatalogFault('Private Studio and Git paths are unavailable to remote transfers.', 403)
    return names


def parent(root, relative_path):
    names = relative(relative_path); descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for index, name in enumerate(names):
            entries = []
            with os.scandir(descriptor) as iterator:
                for entry in iterator:
                    entries.append(entry.name)
                    if len(entries) > 10000: raise CatalogFault('The local directory exceeds its entry limit.', 413)
            if any(n.casefold() == name.casefold() and n != name for n in entries): raise CatalogFault('Resolve the local filename case collision before transfer.', 409)
            if index == len(names) - 1: return descriptor, name
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor); descriptor = child
    except BaseException: os.close(descriptor); raise


def read_file(root, name, maximum=MAX_FILE):
    par, filename = parent(root, name)
    try: descriptor = os.open(filename, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=par)
    finally: os.close(par)
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > maximum: raise CatalogFault('Select an ordinary unlinked file within8 MiB.', 413)
        content = stream.read(maximum + 1)
        if len(content) > maximum or signature(before) != signature(os.fstat(stream.fileno())): raise CatalogFault('The local source changed during snapshot.', 409)
    return content


def source(actor, content):
    if actor.config['permissions'].get('studio.read_file') is not True: raise CatalogFault('Workspace file reading is disabled for this run.', 403)
    if 'sourcePath' in content:
        value = read_file(workspace(actor.projects, actor.project_id, True), content['sourcePath'])
    else:
        # Only an explicitly selected, verified current-project artifact. Do not
        # instantiate Jobs: this lookup must not initialize or migrate its DB.
        artifact_id = identity(content['artifactId']); root = actor.projects / actor.project_id / 'Development'
        path = root / 'Development.sqlite'; regular(path)
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            row = db.execute('SELECT payload FROM artifacts WHERE id=?', (artifact_id,)).fetchone()
            if not row: raise CatalogFault('This project artifact was not found.', 404)
            record = json.loads(row[0]); build_row = db.execute('SELECT payload FROM jobs WHERE id=?', (record['buildId'],)).fetchone()
            build = json.loads(build_row[0]) if build_row else {}
            if (record.get('projectId') != actor.project_id or record.get('pins') != actor.config['projectPins']
                    or build.get('kind') != 'build' or build.get('state') != 'completed' or build.get('artifactId') != artifact_id
                    or build.get('sessionId') not in (None, actor.context['sessionId'])):
                raise CatalogFault('Choose a completed artifact owned by this project, pins and session, or a user build.', 403)
            from jobs import Jobs
            store = Jobs.__new__(Jobs); store.db = db; store.root = root
            record = store.artifact(artifact_id)
        filename = content['artifactPath']; relative(filename)
        selected = next((item for item in record['files'] if item['path'] == filename), None)
        if selected is None: raise CatalogFault('Choose a declared file from this verified artifact.', 400)
        value = read_file(root / 'Artifacts' / artifact_id, filename)
        if len(value) != selected['bytes'] or sha(value) != selected['sha256']: raise CatalogFault('The selected artifact bytes changed.', 409)
    if sha(value) != content['sha256']: raise CatalogFault('The selected source hash changed. Read its current saved bytes before upload.', 409)
    return value


def snapshot(actor, job_id, content):
    value = source(actor, content)
    root = private_directory(actor.projects / actor.project_id / 'RemoteHosts' / 'Snapshots')
    entries = list(root.iterdir())
    for entry in entries: regular(entry)
    if len(entries) >= 32 or sum(p.stat().st_size for p in entries) + len(value) > 128 * 1024 * 1024:
        raise CatalogFault('Preserved transfer snapshots need local maintenance.', 503)
    path = root / identity(job_id)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as stream: stream.write(value); stream.flush(); os.fsync(stream.fileno())
    sync(root)
    return {'id': job_id, 'bytes': len(value), 'sha256': sha(value)}


def snapshot_bytes(projects, project_id, value):
    root = Path(projects) / project_id / 'RemoteHosts/Snapshots'
    content = read_file(root, identity(value['id']))
    if len(content) != value['bytes'] or sha(content) != value['sha256']: raise CatalogFault('The original upload snapshot changed.', 409)
    return content


def destination(actor, content):
    if actor.config['permissions'].get('studio.write_file') is not True: raise CatalogFault('Workspace file writing is disabled for this run.', 403)
    relative(content['localPath'])
    if content['expectedSha256'] is not None:
        digest(content['expectedSha256'])
        raise CatalogFault('Remote downloads create new Workspace files only. Keep existing files and editor drafts; choose an unused local path.', 409)
    root = workspace(actor.projects, actor.project_id, True); par, filename = parent(root, content['localPath'])
    try:
        try: os.stat(filename, dir_fd=par, follow_symlinks=False)
        except FileNotFoundError: return list(signature(os.stat(root)))[:2]
        raise CatalogFault('The local destination already exists. Keep its saved bytes and editor draft; choose an unused path.', 409)
    finally: os.close(par)


def publish(projects, project_id, content, raw, original_root, before_publish):
    if sha(raw) != content['remoteSha256']: raise CatalogFault('The downloaded bytes differ from the selected remote hash.', 409)
    root = workspace(projects, project_id, True)
    if list(signature(os.stat(root)))[:2] != original_root: raise CatalogFault('The accepted Workspace identity changed.', 409)
    par, filename = parent(root, content['localPath']); temporary = '.studio-remote-' + str(__import__('uuid').uuid4())
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=par)
        with os.fdopen(descriptor, 'wb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        # Revalidate parents, case collisions and root immediately before a
        # create-only rename. The active inherited lease excludes Studio writers.
        check, _ = parent(root, content['localPath'])
        try:
            if signature(os.fstat(check))[:2] != signature(os.fstat(par))[:2] or signature(os.stat(root))[:2] != original_root:
                raise CatalogFault('The accepted destination changed.', 409)
        finally: os.close(check)
        before_publish()
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.renameat2(par, os.fsencode(temporary), par, os.fsencode(filename), 1):
            if ctypes.get_errno() == errno.EEXIST: raise CatalogFault('The local destination appeared during download. Existing bytes and drafts were kept.', 409)
            raise CatalogFault('Local publication could not be confirmed.', 503)
        os.fsync(par)
    finally:
        try: os.unlink(temporary, dir_fd=par)
        except FileNotFoundError: pass
        os.close(par)
    return {'localPath': content['localPath'], 'bytes': len(raw), 'sha256': sha(raw), 'published': True, 'createOnly': True}
