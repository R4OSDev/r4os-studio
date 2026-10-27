"""Additive UUID binding. Reads of legacy projects do not create/migrate rows."""
from contextlib import contextmanager, closing
import importlib.util
import fcntl
import os
from pathlib import Path
import re
import sqlite3
import stat
from store import ProjectFault

TABLE = 'project_remote_hosts'
REMOTE_JOBS_APPLICATION_ID = 0x5234524A


def exists(db): return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone() is not None


def get(db, project_id):
    if db is None or not exists(db): return None
    row = db.execute('SELECT host_id FROM project_remote_hosts WHERE project_id=?', (project_id,)).fetchone()
    if row is None: return None
    valid_id(row[0]); return row[0]


def valid_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', value): raise ProjectFault('Select an existing Remote Host.', 400)
    return value


@contextmanager
def hold(projects, host_id):
    if host_id is None: yield; return
    valid_id(host_id)
    spec = importlib.util.spec_from_file_location('studio_binding_remote_catalog', Path(__file__).resolve().parents[1] / 'remote-hosts/catalog.py')
    catalog = importlib.util.module_from_spec(spec); spec.loader.exec_module(catalog)
    lock = None
    try:
        # A shared read-only descriptor works in the existing development host's
        # read-only data namespace. Catalog writers hold its exclusive peer.
        directory = Path(projects).parent / 'RemoteHosts'; path = directory / 'RemoteHosts.sqlite'
        if directory.resolve(strict=True) != directory or path.resolve(strict=True) != path: raise ProjectFault('Remote Host inventory needs local maintenance.', 503)
        catalog.regular(path); catalog.regular(directory / '.catalog.lock')
        lock = os.open(directory / '.catalog.lock', os.O_RDONLY | os.O_NOFOLLOW)
        try: fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError: raise ProjectFault('Remote Host inventory is busy. Retry this project change.', 409) from None
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            if db.execute('PRAGMA user_version').fetchone()[0] != 1 or db.execute('PRAGMA application_id').fetchone()[0] != catalog.APPLICATION_ID: raise ProjectFault('The Remote Host inventory schema needs maintenance.', 503)
            if not db.execute('SELECT 1 FROM hosts WHERE id=?', (host_id,)).fetchone(): raise ProjectFault('The selected Remote Host is missing. Refresh its choices.', 409)
            yield
    except catalog.CatalogFault as error: raise ProjectFault(str(error), error.code) from None
    except (OSError, sqlite3.Error): raise ProjectFault('The Remote Host inventory is unavailable. Refresh its choices.', 409) from None
    finally:
        if lock is not None: os.close(lock)


def set_binding(db, project_id, host_id):
    if host_id is None:
        if exists(db): db.execute('DELETE FROM project_remote_hosts WHERE project_id=?', (project_id,))
        return
    valid_id(host_id)
    db.execute('''CREATE TABLE IF NOT EXISTS project_remote_hosts(
        project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,host_id TEXT NOT NULL)''')
    db.execute('INSERT INTO project_remote_hosts VALUES (?,?) ON CONFLICT(project_id) DO UPDATE SET host_id=excluded.host_id', (project_id, host_id))


def assert_change_safe(projects, project_id):
    path = Path(projects) / project_id / 'RemoteHosts/Jobs.sqlite'
    if not path.exists() and not path.is_symlink(): return
    if path.resolve(strict=True) != path or not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size > 64 * 1024**2:
        raise ProjectFault('The original remote jobs need maintenance before changing this target.', 503)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
        if db.execute('PRAGMA application_id').fetchone()[0] != REMOTE_JOBS_APPLICATION_ID or db.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise ProjectFault('The original remote job schema needs maintenance.', 503)
        if db.execute("SELECT 1 FROM jobs WHERE state IN ('queued','starting','running','stopping','unknown') LIMIT 1").fetchone():
            raise ProjectFault('Finish or reconcile this project’s original remote jobs before changing its assigned host.', 409)
