"""Typed session owners. Skills never enter the project catalog or SDK layout."""
from contextlib import closing
import os
from pathlib import Path
import re
import sqlite3
import stat
from store import ProjectFault
from profile import directory


def owner_type(value):
    if value not in ('project', 'skill'): raise ProjectFault('Unknown session owner type.', 400)
    return value


def binding(value):
    kind = owner_type(value.get('ownerType', 'project'))
    ident = value.get('ownerId') if 'ownerType' in value else value.get('projectId')
    if not isinstance(ident, str) or not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', ident):
        raise ProjectFault('Invalid session owner.', 400)
    if kind == 'skill' and 'projectId' in value: raise ProjectFault('A skill session cannot use a project binding.', 400)
    if kind == 'project' and 'projectId' in value and value['projectId'] != ident:
        raise ProjectFault('Session owner binding changed.', 400)
    return kind, ident


def skills_root(projects): return Path(projects).absolute().parent / 'Skills'


def skill_workspace(projects, ident):
    root = skills_root(projects); path = root / 'Skills.sqlite'
    try:
        if path.resolve(strict=True) != path or not stat.S_ISREG(path.stat().st_mode): raise ValueError()
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
            if db.execute('PRAGMA user_version').fetchone()[0] != 1: raise ValueError()
            row = db.execute("SELECT id FROM skills WHERE id=? AND state='ready'", (ident,)).fetchone()
    except (OSError, ValueError, sqlite3.Error):
        raise ProjectFault('The skill catalog is unavailable. Existing data was preserved.', 503) from None
    if not row: raise ProjectFault('Skill not found.', 404)
    workspace = root / ident / 'Workspace'
    if workspace.resolve(strict=True) != workspace or not stat.S_ISDIR(workspace.stat().st_mode):
        raise ProjectFault('The skill workspace is unavailable.', 503)
    return workspace


def owners(projects):
    """Existing registered catalogs only; recovery never creates a skill."""
    root = skills_root(projects); path = root / 'Skills.sqlite'
    if not path.exists(): return []
    if path.resolve(strict=True) != path: raise ProjectFault('Invalid skill catalog.', 503)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        return [('skill', r[0]) for r in db.execute("SELECT id FROM skills WHERE state='ready'")]


def lock_path(projects, kind, ident):
    if kind == 'skill': return directory(skills_root(projects) / '.locks') / ident
    return directory(Path(projects) / '.studio') / ('workspace-' + ident + '.lock')


def open_lock(projects, kind, ident):
    path = lock_path(projects, kind, ident)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    if not stat.S_ISREG(os.fstat(fd).st_mode): os.close(fd); raise ProjectFault('Invalid workspace lock.', 503)
    return os.fdopen(fd, 'a+b')
