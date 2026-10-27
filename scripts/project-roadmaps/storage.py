"""Shared project roadmap storage. Initialization is explicit and atomic."""
from contextlib import contextmanager
import ctypes
import datetime
import errno
import fcntl
import os
from pathlib import Path
import sqlite3
import stat
import uuid

from schema import APPLICATION_ID, SCHEMA, SCHEMA_VERSION
from project_maintenance import project
from project_use import acquire
from layout import project_directory, sync, workspace
from store import ProjectFault

MAX_DATABASE_BYTES = 64 * 1024 * 1024


class RoadmapFault(ProjectFault):
    pass


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def regular(path):
    info = path.lstat()
    if (path.resolve(strict=True) != path or not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1 or info.st_size > MAX_DATABASE_BYTES):
        raise RoadmapFault('Invalid roadmap storage. Existing data was preserved.', 503)


def folder(path):
    if path.resolve(strict=True) != path or not stat.S_ISDIR(path.lstat().st_mode):
        raise RoadmapFault('Invalid roadmap directory. Existing data was preserved.', 503)


def open_database(path, identity):
    regular(path)
    for suffix in ('-journal', '-wal', '-shm'):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists() or sidecar.is_symlink():
            regular(sidecar)
    db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=3)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        if (db.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION
                or db.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID):
            raise RoadmapFault('Unsupported roadmap database. Existing data was preserved.', 503)
        if db.execute('PRAGMA quick_check(1)').fetchone()[0] != 'ok':
            raise RoadmapFault('The roadmap database needs maintenance. Existing data was preserved.', 503)
        row = db.execute('SELECT project_id FROM roadmap WHERE singleton=1').fetchone()
        if row is None or row['project_id'] != identity:
            raise RoadmapFault('The roadmap belongs to a different project or is incomplete.', 503)
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise RoadmapFault('The roadmap hierarchy needs maintenance. Existing data was preserved.', 503)
        db.execute('PRAGMA synchronous=FULL')
        return db
    except BaseException:
        db.close()
        raise


def create_database(path, identity):
    """Publish a fully committed database; never initialize an existing file."""
    lock = path.parent / '.initialize.lock'
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
            raise RoadmapFault('Invalid roadmap initialization lock.', 503)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RoadmapFault('Roadmap initialization is in progress. Reload before retrying.') from None
        if path.exists() or path.is_symlink():
            return
        if any((path.parent / (path.name + s)).exists() or (path.parent / (path.name + s)).is_symlink()
               for s in ('-journal', '-wal', '-shm')):
            raise RoadmapFault('Interrupted roadmap storage needs maintenance. All files were preserved.', 503)
        # A crash can leave an unpublished staging file. It is never reused or
        # overwritten, and cannot contain accepted mutations before publication.
        stage = path.parent / ('.initializing-' + str(uuid.uuid4()) + '.sqlite')
        initial = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(initial)
        db = sqlite3.connect(stage)
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA synchronous=FULL')
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA)
            roadmap_id, version_id, now = str(uuid.uuid4()), str(uuid.uuid4()), timestamp()
            db.execute('INSERT INTO roadmap(id,project_id,current_version_id,created_at,updated_at) VALUES(?,?,?,?,?)',
                       (roadmap_id, identity, version_id, now, now))
            db.execute('INSERT INTO versions(id,roadmap_id,major,minor,title,position,created_at,updated_at) VALUES(?,?,0,1,\'New\',0,?,?)',
                       (version_id, roadmap_id, now, now))
            db.execute('PRAGMA application_id=' + str(APPLICATION_ID))
            db.execute('PRAGMA user_version=' + str(SCHEMA_VERSION))
            db.commit()
        finally:
            db.close()
        with stage.open('rb') as stream:
            os.fsync(stream.fileno())
        rename = ctypes.CDLL(None, use_errno=True).renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(stage), -100, os.fsencode(path), 1):
            code = ctypes.get_errno()
            if code != errno.EEXIST:
                raise OSError(code, 'Roadmap publication failed.')
        sync(path.parent)
    finally:
        os.close(fd)


@contextmanager
def connection(projects, identity, initialize=False):
    projects = Path(projects).absolute()
    # Lifetime locks coordinate deletion, not workspace edits or agent runs.
    with acquire(projects, identity):
        project(projects, identity)
        parent = project_directory(projects, identity)
        if not (parent / 'Workspace').exists() and not (parent / 'Workspace').is_symlink():
            raise RoadmapFault('Migrate this project to the Workspace layout before using its roadmap. Existing files were preserved.', 409)
        workspace(projects, identity, require_current=True)
        directory = parent / 'Roadmap'
        if not directory.exists() and not directory.is_symlink():
            if not initialize:
                yield None
                return
            directory.mkdir(mode=0o700, exist_ok=True)
            sync(directory.parent)
        folder(directory)
        path = directory / 'Roadmap.sqlite'
        if not path.exists() and not path.is_symlink():
            if any((directory / (path.name + s)).exists() or (directory / (path.name + s)).is_symlink()
                   for s in ('-journal', '-wal', '-shm')):
                raise RoadmapFault('Interrupted roadmap storage needs maintenance. All files were preserved.', 503)
            if not initialize:
                yield None
                return
            create_database(path, identity)
        db = open_database(path, identity)
        try:
            yield db
        finally:
            db.close()
