#!/usr/bin/env python3
"""Read-only diagnostics for a new isolated, offline Projects restore."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys

sys.path.insert(1, str(Path(__file__).resolve().parents[1] / 'projects'))
sys.path.insert(1, str(Path(__file__).resolve().parents[1] / 'agent-sessions'))
from cleanup_files import directory, file_hash, document, signature
from cleanup import TRIGGER
from schema import APPLICATION_ID, SCHEMA_VERSION
from validation import identity, number
from store import ProjectFault


@contextmanager
def database(path, maximum=64 * 1024 * 1024, check=True):
    path = Path(path).absolute()
    if path.resolve(strict=True) != path: raise ProjectFault('Restore database paths must not contain links.', 409)
    for suffix in ('-wal', '-shm', '-journal'):
        if path.with_name(path.name + suffix).exists() or path.with_name(path.name + suffix).is_symlink():
            raise ProjectFault('Inspect only an isolated offline restore without live database sidecars.', 409)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    db = None
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > maximum:
            raise ProjectFault('Restore needs ordinary database files within its limits.', 409)
        db = sqlite3.connect((Path('/proc/self/fd') / str(fd)).as_uri() + '?mode=ro&immutable=1', uri=True)
        db.row_factory = sqlite3.Row
        if db.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise ProjectFault('The restore schema requires a matching Studio release.', 409)
        if check and db.execute('PRAGMA quick_check(1)').fetchone()[0] != 'ok': raise ProjectFault('Restore database integrity check failed.', 409)
        yield db
        observed = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if observed(before) != observed(os.fstat(fd)) or observed(before) != observed(path.stat()):
            raise ProjectFault('Restore files changed during inspection. Keep this restore offline.', 409)
        for suffix in ('-wal', '-shm', '-journal'):
            if path.with_name(path.name + suffix).exists(): raise ProjectFault('A writer appeared during offline inspection.', 409)
    finally:
        if db: db.close()
        os.close(fd)


def origin_matches(project, project_id, origin):
    try:
        identity(origin['runId']); identity(origin['sessionId'])
        with database(project / 'Sessions/Sessions.sqlite', maximum=32 * 1024**3, check=False) as db:
            from human_context import text as human_text
            text=human_text(db,origin['sessionId'],origin['runId'],{'type':'project','id':project_id})
            return isinstance(text,str) and TRIGGER.search(text) is not None and hashlib.sha256(text.encode()).hexdigest()==origin['sha256']
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ProjectFault, sqlite3.Error): return False


def inspect(projects, project_id):
    projects = Path(projects).absolute(); identity(project_id)
    if projects.resolve(strict=True) != projects: raise ProjectFault('Select a real isolated Projects directory.', 409)
    with database(projects / 'Projects.sqlite') as catalog:
        row = catalog.execute("SELECT id FROM projects WHERE id=? AND state='ready'", (project_id,)).fetchone()
        if row is None or catalog.execute('SELECT 1 FROM project_deletions WHERE project_id=?', (project_id,)).fetchone():
            raise ProjectFault('The restored project is absent or needs its original maintenance reconciliation.', 409)
    project = projects / project_id; workspace = project / 'Workspace'
    if workspace.resolve(strict=True) != workspace or not workspace.is_dir(): raise ProjectFault('The restored workspace must be a real directory.', 409)
    path = project / 'Roadmap/Roadmap.sqlite'
    if not path.exists() and not path.is_symlink(): return {'projectId': project_id, 'roadmapExists': False, 'readOnly': True}
    with database(path) as db:
        if db.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID or SCHEMA_VERSION != 1 or db.execute('PRAGMA foreign_key_check').fetchone():
            raise ProjectFault('The restored Roadmap schema or hierarchy requires maintenance.', 409)
        roadmap = db.execute('SELECT * FROM roadmap WHERE singleton=1').fetchone()
        if roadmap is None or roadmap['project_id'] != project_id: raise ProjectFault('The restored Roadmap has another project binding.', 409)
        version = db.execute('SELECT * FROM versions WHERE id=?', (roadmap['current_version_id'],)).fetchone()
        if version is None: raise ProjectFault('The restored current version is missing.', 409)
        fd = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        workflows = []
        try:
            for row in db.execute("SELECT * FROM workflows WHERE kind='cleanup' ORDER BY created_at,id"):
                value = json.loads(row['payload']); pending = row['phase'] not in ('complete', 'cancelled', 'aborted')
                if value.get('schema') != 1 or value.get('projectId') != project_id or value.get('versionId') != row['version_id']:
                    raise ProjectFault('A restored workflow has an invalid original binding.', 409)
                number(value['number'])
                archive_match = None
                if value.get('archive'):
                    try:
                        docs = directory(fd, 'Docs')
                        try: logs = directory(docs, 'Changelogs')
                        finally: os.close(docs)
                        try: actual = file_hash(logs, value['number'] + '.txt', 96 * 1024**2)
                        finally: os.close(logs)
                        archive_match = actual['sha256'] == value['archive']['sha256'] and actual['byteLength'] == value['archive']['byteLength']
                    except (OSError, ProjectFault): archive_match = False
                documents_match = True
                for entry in value.get('documents', []):
                    try:
                        actual = document(fd, entry['path'])
                        documents_match &= actual['sha256'] == entry['sha256'] and actual['byteLength'] == entry['byteLength']
                    except (OSError, ProjectFault): documents_match = False
                workflows.append({'workflowId': row['id'], 'phase': row['phase'], 'number': value['number'], 'pending': pending,
                                  'archiveMatchesReceipt': archive_match, 'documentsMatchReceipts': documents_match,
                                  'originalUserEvidenceMatches': origin_matches(project, project_id, value.get('origin', {})),
                                  'workspaceIdentityMatches': signature(os.fstat(fd)) == value.get('workspace'),
                                  'currentBindingMatches': roadmap['revision'] == value['revision'] and roadmap['current_version_id'] == row['version_id']})
        finally: os.close(fd)
        return {'projectId': project_id, 'roadmapExists': True, 'roadmapId': roadmap['id'], 'revision': roadmap['revision'],
                'currentVersionId': version['id'], 'currentNumber': f'{version["major"]}.{version["minor"]}.X',
                'workflows': workflows, 'pendingReconciliationRequired': any(w['pending'] for w in workflows),
                'readOnly': True, 'activated': False, 'filesOrBindingsModified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--projects', type=Path, required=True); parser.add_argument('--project', required=True)
    parser.add_argument('--offline', action='store_true', required=True, help='Confirm this is a new isolated restore without live writers.')
    args = parser.parse_args()
    try: print(json.dumps(inspect(args.projects, args.project), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ProjectFault, sqlite3.Error): raise SystemExit('Restore inspection failed. Existing data was not changed; preserve and review the original restore.') from None
