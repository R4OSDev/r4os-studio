"""Fixed project identity and read-only busy checks for exclusive maintenance."""
from contextlib import closing
from pathlib import Path
import sqlite3
import stat
from store import ProjectFault, public
from project_use import project_id
from layout import project_directory


def database(path):
    if path.resolve(strict=True) != path or not stat.S_ISREG(path.lstat().st_mode):
        raise ProjectFault('Invalid project state. Existing data was preserved.', 503)
    return sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)


def project(projects, identity):
    project_id(identity); projects = Path(projects).absolute()
    project_directory(projects, identity)
    with closing(database(projects / 'Projects.sqlite')) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM projects WHERE id=? AND state='ready'", (identity,)).fetchone()
        if row is None: raise ProjectFault('Project not found.', 404)
        if db.execute('SELECT 1 FROM project_deletions WHERE project_id=?', (identity,)).fetchone():
            raise ProjectFault('This project is being deleted.', 409)
        return public(row)


def busy(projects, identity):
    directory = project_directory(projects, project_id(identity))
    for relative, table in (('Sessions/Sessions.sqlite', 'runs'), ('Development/Development.sqlite', 'jobs')):
        path = directory / relative
        if not path.exists() and not path.is_symlink(): continue
        with closing(database(path)) as db:
            if db.execute('SELECT 1 FROM ' + table + ' WHERE busy=1 LIMIT 1').fetchone(): return True
    return False


def require_idle(projects, identity):
    if busy(projects, identity):
        raise ProjectFault('Wait for active agent runs and development jobs to finish.', 409)
