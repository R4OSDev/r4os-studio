#!/usr/bin/env python3
"""Bounded SQLite operations for the unprivileged Studio process. JSON on stdin/stdout."""
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import datetime
import re


class ProjectFault(Exception):
    def __init__(self, message, code=409):
        super().__init__(message)
        self.code = code


def public(row):
    if row is None:
        raise ProjectFault('Project not found.', 404)
    return {'id': row['id'], 'name': row['name'], 'description': row['description'],
            'language': row['language'], 'template': row['template'], 'vmId': row['vm_id'],
            'moduleName': row['module_name'], 'pins': json.loads(row['pins']),
            'revision': row['revision'], 'createdAt': row['created_at'], 'updatedAt': row['updated_at']}


def check_vm(root, identity):
    if identity is None:
        return
    if not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', identity):
        raise ProjectFault('Select an existing virtual machine.', 400)
    path = root / 'Instances' / identity / 'vm.json'
    try:
        if path.resolve(strict=True) != path.absolute() or not path.is_file():
            raise ValueError()
        if json.loads(path.read_text())['id'] != identity:
            raise ValueError()
    except (OSError, ValueError, KeyError):
        raise ProjectFault('The selected virtual machine is unavailable.') from None


def vm_choices(root):
    values = []
    try:
        parent = root / 'Instances'
        for path in parent.iterdir() if parent.exists() else []:
            try:
                check_vm(root, path.name)
                value = json.loads((path / 'vm.json').read_text())
                if isinstance(value.get('name'), str):
                    values.append({'id': value['id'], 'name': value['name']})
            except (OSError, ValueError, KeyError, ProjectFault):
                continue
        return {'vms': sorted(values, key=lambda value: value['name'].lower()), 'vmsAvailable': True}
    except OSError:
        return {'vms': [], 'vmsAvailable': False}


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


def operation(db, request, root):
    if request == {'operation': 'list'}:
        return [dict(row) for row in db.execute("SELECT id,name FROM projects WHERE state='ready'")]
    if request.get('operation') == 'vms' and len(request) == 1:
        return vm_choices(root)
    if request.get('operation') == 'get' and set(request) == {'operation', 'id'}:
        return public(db.execute("SELECT * FROM projects WHERE id=? AND state='ready'", (request['id'],)).fetchone())
    if request.get('operation') == 'update' and set(request) == {'operation', 'id', 'input'}:
        data = request['input']
        if not set(data).issubset({'name', 'description', 'vmId', 'revision'}) or 'revision' not in data:
            raise ProjectFault('Unexpected project fields.', 400)
        db.execute('BEGIN IMMEDIATE')
        old = public(db.execute("SELECT * FROM projects WHERE id=? AND state='ready'", (request['id'],)).fetchone())
        if old['revision'] != data['revision']:
            raise ProjectFault('Project settings changed. Reload before saving.')
        value = {**old, **data}
        if value['vmId'] != old['vmId']:
            check_vm(root, value['vmId'])
        if (value['name'], value['description'], value['vmId']) != (old['name'], old['description'], old['vmId']):
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            db.execute('UPDATE projects SET name=?,description=?,vm_id=?,updated_at=?,revision=revision+1 WHERE id=?',
                       (value['name'], value['description'], value['vmId'], now, request['id']))
        db.commit()
        return public(db.execute('SELECT * FROM projects WHERE id=?', (request['id'],)).fetchone())
    raise ValueError('Unsupported project operation.')


def main():
    os.umask(0o077)
    data = sys.stdin.buffer.read(131073)
    if len(data) > 131072:
        raise ValueError('Project request is too large.')
    request = json.loads(data)
    with connect(Path(sys.argv[1])) as db:
        result = operation(db, request, Path(sys.argv[2]))
    print(json.dumps({'result': result}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except ProjectFault as error:
        print(json.dumps({'error': str(error), 'code': error.code}))
        sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'Project storage is unavailable.', 'code': 503}))
        sys.exit(1)
