#!/usr/bin/env python3
"""Bounded SQLite operations for the unprivileged Studio process. JSON on stdin/stdout."""
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys


def connect(root):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError('Invalid project storage.')
    path = root / 'Projects.sqlite'
    for candidate in (path, root / 'Projects.sqlite-journal'):
        if candidate.exists() or candidate.is_symlink():
            if not stat.S_ISREG(candidate.lstat().st_mode):
                raise ValueError('Invalid project database.')
    db = sqlite3.connect(path, timeout=5)
    os.chmod(path, 0o600)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA synchronous=FULL')
    db.execute('BEGIN IMMEDIATE')
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version not in (0, 1):
        raise ValueError('Unsupported project database version.')
    with db:
        if version == 0:
            if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                raise ValueError('Unrecognized project database.')
            db.execute('''CREATE TABLE projects (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
                language TEXT NOT NULL, template TEXT NOT NULL, module_name TEXT NOT NULL UNIQUE,
                vm_id TEXT, pins TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 1, state TEXT NOT NULL CHECK(state IN ('pending','ready','failed'))
            )''')
            db.execute('''CREATE TABLE requests (
                request_key TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
                project_id TEXT NOT NULL UNIQUE REFERENCES projects(id),
                phase TEXT NOT NULL, hashes TEXT, error TEXT
            )''')
            db.execute('PRAGMA user_version=1')
    db.commit()
    return db


def operation(db, request):
    if request == {'operation': 'list'}:
        return [dict(row) for row in db.execute("SELECT id,name FROM projects WHERE state='ready'")]
    raise ValueError('Unsupported project operation.')


def main():
    os.umask(0o077)
    data = sys.stdin.buffer.read(131073)
    if len(data) > 131072:
        raise ValueError('Project request is too large.')
    request = json.loads(data)
    with connect(Path(sys.argv[1])) as db:
        result = operation(db, request)
    print(json.dumps({'result': result}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'error': 'Project storage is unavailable.', 'code': 503}))
        sys.exit(1)
