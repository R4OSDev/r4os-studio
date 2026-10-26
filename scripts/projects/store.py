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


def public(row, db=None):
    if row is None:
        raise ProjectFault('Project not found.', 404)
    module_name = row['module_name']
    if db is not None and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_imports'").fetchone():
        imported = db.execute('SELECT source_module_name FROM project_imports WHERE project_id=?', (row['id'],)).fetchone()
        if imported: module_name = imported[0]
    return {'id': row['id'], 'name': row['name'], 'description': row['description'],
            'language': row['language'], 'template': row['template'], 'vmId': row['vm_id'],
            'moduleName': module_name, 'pins': json.loads(row['pins']),
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
    with db:
        db.execute('CREATE TABLE IF NOT EXISTS project_deletions(project_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS retired_project_requests(request_key TEXT PRIMARY KEY, request_hash TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS project_imports(project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE, source_module_name TEXT NOT NULL, request_hash TEXT NOT NULL)')
    return db


def operation(db, request, root):
    if request == {'operation': 'list'}:
        return [{'id': row['id'], 'name': row['name'], **({'deleting': True} if row['deleting'] else {})}
                for row in db.execute("SELECT p.id,p.name,d.project_id AS deleting FROM projects p LEFT JOIN project_deletions d ON d.project_id=p.id WHERE p.state='ready' OR d.project_id IS NOT NULL")]
    if request.get('operation') == 'vms' and len(request) == 1:
        return vm_choices(root)
    if request.get('operation') == 'get' and set(request) == {'operation', 'id'}:
        return public(db.execute("SELECT * FROM projects WHERE id=? AND state='ready'", (request['id'],)).fetchone(), db)
    if request.get('operation') == 'get_settings' and set(request) == {'operation', 'id'}:
        row = db.execute('SELECT * FROM projects WHERE id=?', (request['id'],)).fetchone()
        deleting = db.execute('SELECT 1 FROM project_deletions WHERE project_id=?', (request['id'],)).fetchone()
        if row is None or (row['state'] != 'ready' and not deleting): raise ProjectFault('Project not found.', 404)
        return {**public(row, db), **({'deleting': True} if deleting else {})}
    if request.get('operation') == 'update' and set(request) == {'operation', 'id', 'input'}:
        data = request['input']
        if not set(data).issubset({'name', 'description', 'vmId', 'revision'}) or 'revision' not in data:
            raise ProjectFault('Unexpected project fields.', 400)
        from project_maintenance import pending_update
        catalog_path = Path(db.execute('PRAGMA database_list').fetchone()[2]).parent
        if pending_update(catalog_path,request['id']):
            raise ProjectFault('Resolve this project\'s owned native update before changing its settings.')
        db.execute('BEGIN IMMEDIATE')
        old = public(db.execute("SELECT * FROM projects WHERE id=? AND state='ready'", (request['id'],)).fetchone(), db)
        if old['revision'] != data['revision']:
            raise ProjectFault('Project settings changed. Reload before saving.')
        value = {**old, **data}
        if value['vmId'] != old['vmId']:
            # Build receipts survive assignment changes. Active guest work keeps
            # its target until explicitly stopped; do not retarget a live job.
            catalog_path = Path(db.execute('PRAGMA database_list').fetchone()[2]).parent
            development = catalog_path / old['id'] / 'Development/Development.sqlite'
            if development.exists():
                if development.resolve(strict=True) != development: raise ProjectFault('Invalid development storage.', 503)
                from urllib.parse import quote
                jobs = sqlite3.connect('file:' + quote(str(development)) + '?mode=ro', uri=True, timeout=5)
                try:
                    if jobs.execute("SELECT id FROM jobs WHERE busy=1 AND kind IN ('deploy','execution','vm_start','update_probe','update_transfer','update_install','update_commit','update_verify','update_recovery') LIMIT 1").fetchone():
                        raise ProjectFault('Stop this project\'s VM development job before changing its assigned VM.')
                finally: jobs.close()
            check_vm(root, value['vmId'])
        if (value['name'], value['description'], value['vmId']) != (old['name'], old['description'], old['vmId']):
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            db.execute('UPDATE projects SET name=?,description=?,vm_id=?,updated_at=?,revision=revision+1 WHERE id=?',
                       (value['name'], value['description'], value['vmId'], now, request['id']))
        db.commit()
        return public(db.execute('SELECT * FROM projects WHERE id=?', (request['id'],)).fetchone(), db)
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
