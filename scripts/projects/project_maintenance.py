"""Fixed project identity and read-only busy checks for exclusive maintenance."""
from contextlib import closing
from pathlib import Path
import sqlite3
import json
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
        return public(row, db)


def pending_update(projects,identity):
    root=Path(projects)/'.studio/development/UpdateOwners'
    if not root.exists():return False
    for path in root.glob('*.json'):
        try:
            info=path.lstat()
            if path.resolve(strict=True)!=path or not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>2097152:raise ValueError()
            value=json.loads(path.read_text())
            if not isinstance(value,dict) or value.get('schema')!=1:raise ValueError()
        except (OSError,ValueError):raise ProjectFault('Update ownership needs maintenance. Existing project data was preserved.',503) from None
        if value.get('projectId')==identity and value.get('phase') not in ('installed','live_installed','aborted','rolled_back','rejected'):
            return True
    return False


def pending_git(projects, identity):
    path = Path(projects) / identity / '.studio/git/pull-journal.json'
    if not path.exists() and not path.is_symlink(): return False
    if path.resolve(strict=True) != path or not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size > 65536: raise ProjectFault('Git recovery metadata needs review.', 503)
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get('schema') != 1: raise ProjectFault('Git recovery metadata needs review.', 503)
    return value.get('phase') in ('prepared', 'exchanged', 'ref_updated')


def busy(projects, identity, ignore_git=False):
    if not ignore_git and pending_git(projects, identity): return True
    if pending_update(projects,identity):return True
    directory = project_directory(projects, project_id(identity))
    for relative, table in (('Sessions/Sessions.sqlite', 'runs'), ('Development/Development.sqlite', 'jobs')):
        path = directory / relative
        if not path.exists() and not path.is_symlink(): continue
        with closing(database(path)) as db:
            if db.execute('SELECT 1 FROM ' + table + ' WHERE busy=1 LIMIT 1').fetchone(): return True
    return False


def require_idle(projects, identity, ignore_git=False):
    if busy(projects, identity, ignore_git):
        raise ProjectFault('Wait for active agent runs and development jobs to finish.', 409)
