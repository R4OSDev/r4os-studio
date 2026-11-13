"""Shared project roadmap storage. Initialization is explicit and atomic."""
from contextlib import contextmanager
import ctypes
import datetime
import errno
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import stat
import uuid

from schema import APPLICATION_ID, SCHEMA, SCHEMA_VERSION, completion_triggers
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


def ensure_completion_dates(db, project_id):
    def installed():
        return any(column['name'] == 'completed_at' for column in db.execute('PRAGMA table_info(versions)'))

    if installed():
        return
    db.execute('BEGIN IMMEDIATE')
    with db:
        if installed():
            return
        for table in ('versions', 'subversions'):
            db.execute(f'ALTER TABLE {table} ADD COLUMN completed_at TEXT')
            completion_triggers(db, table)
        backfill_completion_dates(db, project_id)


def backfill_completion_dates(db, project_id):
    completed = {row['id']: (table, row) for table in ('versions', 'subversions')
                 for row in db.execute(f"SELECT * FROM {table} WHERE status='complete'")}
    if not completed:
        return
    statuses = {ident: {} for ident in completed}
    for (raw,) in db.execute('SELECT result FROM receipts'):
        result = json.loads(raw)
        initial = result.get('entity')
        initial_id = result.get('currentVersionId')
        if initial_id in completed and isinstance(initial, dict) and initial.get('projectId') == project_id:
            table, version = completed[initial_id]
            if table == 'versions' and initial.get('createdAt') == version['created_at']:
                # Initialization inserts its first version as open in the same transaction.
                statuses[initial_id].setdefault(1, ('open', version['created_at']))
        entries = [initial, *(op.get('entity') for op in result.get('operations', []))]
        for entity in entries:
            if not isinstance(entity, dict) or entity.get('id') not in completed:
                continue
            ident = entity['id']
            table, version = completed[ident]
            revision = entity.get('revision')
            if (type(revision) is int and 1 <= revision <= version['revision']
                    and entity.get('createdAt') == version['created_at']
                    and entity.get('status') in ('open', 'complete', 'discarded')
                    and isinstance(entity.get('updatedAt'), str)
                    and entity.get('versionId') == (version['version_id'] if table == 'subversions' else None)):
                statuses[ident][revision] = (entity['status'], entity['updatedAt'])

    workflows = {}
    for row in db.execute("SELECT version_id,payload FROM workflows WHERE kind='cleanup' AND phase='complete'"):
        payload = json.loads(row['payload'])
        final = payload.get('finalResult', {})
        stamp = final.get('completedAt')
        if (payload.get('schema') == 1 and payload.get('projectId') == project_id
                and payload.get('versionId') == payload.get('currentVersionId') == row['version_id']
                and final.get('phase') == 'complete' and isinstance(stamp, str)):
            workflows.setdefault(row['version_id'], set()).add(stamp)

    for ident, (table, row) in completed.items():
        stamp = row['updated_at']
        previous = statuses[ident]
        workflow_stamps = workflows.get(ident, ())
        # A missing revision could have reopened the version. Only follow a
        # continuous chain of completed revisions back to an explicit receipt.
        for revision in range(row['revision'], 0, -1):
            if stamp in workflow_stamps:
                break
            if previous.get(revision) != ('complete', stamp):
                stamp = None
                break
            before = previous.get(revision - 1)
            if (revision == 1 and stamp == row['created_at']) or (before and before[0] != 'complete'):
                break
            stamp = before[1] if before else None
            if stamp is None:
                break
        if stamp is not None:
            db.execute(f'UPDATE {table} SET completed_at=? WHERE id=?', (stamp, ident))


def open_database(path, identity, verify_integrity=True):
    regular(path)
    for suffix in ('-journal', '-wal', '-shm'):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists() or sidecar.is_symlink():
            regular(sidecar)
    db = sqlite3.connect(path.as_uri() + ('?mode=rw' if verify_integrity else '?mode=ro'), uri=True, timeout=3)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        if (db.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION
                or db.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID):
            raise RoadmapFault('Unsupported roadmap database. Existing data was preserved.', 503)
        if verify_integrity and db.execute('PRAGMA quick_check(1)').fetchone()[0] != 'ok':
            raise RoadmapFault('The roadmap database needs maintenance. Existing data was preserved.', 503)
        row = db.execute('SELECT project_id FROM roadmap WHERE singleton=1').fetchone()
        if row is None or row['project_id'] != identity:
            raise RoadmapFault('The roadmap belongs to a different project or is incomplete.', 503)
        if verify_integrity and db.execute('PRAGMA foreign_key_check').fetchone():
            raise RoadmapFault('The roadmap hierarchy needs maintenance. Existing data was preserved.', 503)
        db.execute('PRAGMA synchronous=FULL')
        if verify_integrity:
            ensure_completion_dates(db, identity)
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
            for table in ('versions', 'subversions'):
                completion_triggers(db, table)
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
def connection(projects, identity, initialize=False, verify_integrity=True):
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
        db = open_database(path, identity, verify_integrity=verify_integrity)
        try:
            yield db
        finally:
            db.close()
