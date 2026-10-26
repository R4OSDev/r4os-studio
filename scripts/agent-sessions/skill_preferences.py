"""Additive per-session exceptions, separate from legacy session/catalog schemas."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import stat
from owner import skills_root
from store import ProjectFault

MAX_SKILLS = 256


def normalize(value):
    from session_store import identity
    if not isinstance(value, dict) or len(value) > MAX_SKILLS or any(type(v) is not bool for v in value.values()):
        raise ProjectFault('Invalid session skill choices.', 400)
    for key in value: identity(key)
    return {key: False for key in sorted(value) if value[key] is False}


def location(projects):
    path = skills_root(projects) / 'SessionSettings.sqlite'
    for candidate in (path, *[path.with_name(path.name + suffix) for suffix in ('-journal', '-wal', '-shm')]):
        if candidate.exists() or candidate.is_symlink():
            if candidate.resolve(strict=True) != candidate or not stat.S_ISREG(candidate.lstat().st_mode):
                raise ProjectFault('Session skill settings are unavailable. Existing data was preserved.', 503)
    return path


def read(projects, kind, owner_id, session_id):
    path = location(projects)
    if not path.exists(): return {}
    try:
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
            if db.execute('PRAGMA user_version').fetchone()[0] != 1: raise ValueError()
            row = db.execute('SELECT choices FROM overrides WHERE owner_type=? AND owner_id=? AND session_id=?',
                             (kind, owner_id, session_id)).fetchone()
        if row is None: return {}
        if len(row[0].encode()) > 32768: raise ValueError()
        return normalize(json.loads(row[0]))
    except (sqlite3.Error, ValueError, TypeError):
        raise ProjectFault('Session skill settings are unavailable. Existing data was preserved.', 503) from None
    except ProjectFault as error:
        if error.code == 400: raise ProjectFault('Session skill settings are invalid. Existing data was preserved.', 503) from None
        raise


def write(store, session_id, value):
    """Called inside the main settings transaction; ATTACH commits both atomically."""
    from skill_application import catalog
    from session_store import encode
    choices = normalize(value)
    if store.db.execute('PRAGMA main.journal_mode').fetchone()[0].lower() != 'delete':
        raise ProjectFault('Session skill choices require the supported rollback-journal storage. Existing data was preserved.', 503)
    previous = read(store.projects, store.owner_type, store.owner_id, session_id)
    known = {entry['id'] for entry in catalog(store.projects)}
    if set(choices) - known - set(previous): raise ProjectFault('A selected global skill is unavailable. Reload settings.', 409)
    path = location(store.projects)
    if path.parent.resolve(strict=True) != path.parent: raise ProjectFault('Invalid skill settings directory.', 503)
    # Initialize only this new auxiliary store on an explicit settings Save.
    # A failed main transaction then leaves a valid empty auxiliary database.
    attached = next((row for row in store.db.execute('PRAGMA database_list') if row[1] == 'skill_preferences'), None)
    if attached:
        if Path(attached[2]) != path: raise ProjectFault('Session skill settings binding changed.', 503)
    else:
        with closing(sqlite3.connect(path, timeout=5)) as auxiliary:
            os.chmod(path, 0o600); auxiliary.execute('PRAGMA synchronous=FULL'); auxiliary.execute('BEGIN IMMEDIATE')
            if auxiliary.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
                raise ProjectFault('Unsupported session skill settings journal. Existing data was preserved.', 503)
            version = auxiliary.execute('PRAGMA user_version').fetchone()[0]
            if version == 0:
                if auxiliary.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise ProjectFault('Unrecognized session skill settings. Existing data was preserved.', 503)
                auxiliary.execute('''CREATE TABLE overrides(owner_type TEXT NOT NULL,owner_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,choices TEXT NOT NULL,PRIMARY KEY(owner_type,owner_id,session_id))''')
                auxiliary.execute('PRAGMA user_version=1')
            elif version != 1: raise ProjectFault('Unsupported session skill settings version.', 503)
            auxiliary.commit()
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
        store.db.execute('ATTACH DATABASE ? AS skill_preferences', (str(path),))
    if (store.db.execute('PRAGMA skill_preferences.journal_mode').fetchone()[0].lower() != 'delete'
            or store.db.execute('PRAGMA skill_preferences.synchronous').fetchone()[0] < 2):
        raise ProjectFault('Unsupported session skill settings durability. Existing data was preserved.', 503)
    store.db.execute('''INSERT INTO skill_preferences.overrides VALUES(?,?,?,?)
        ON CONFLICT(owner_type,owner_id,session_id) DO UPDATE SET choices=excluded.choices''',
        (store.owner_type, store.owner_id, session_id, encode(choices)))
