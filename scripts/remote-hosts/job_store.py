"""Project-private secret-free durable remote job receipts, including unknown effects."""
from contextlib import contextmanager, closing
import ctypes
import json
import os
from pathlib import Path
import sqlite3
import uuid
from catalog import CatalogFault, identity, now, regular, sync
from transport import private_directory

APPLICATION_ID = 0x5234524A
ACTIVE = ('queued', 'starting', 'running', 'stopping')
SCHEMA = f'''
CREATE TABLE jobs(id TEXT PRIMARY KEY,request_id TEXT NOT NULL UNIQUE,fingerprint TEXT NOT NULL,
 session_id TEXT NOT NULL,run_id TEXT NOT NULL,host_id TEXT NOT NULL,state TEXT NOT NULL,
 phase TEXT NOT NULL,payload TEXT NOT NULL,result TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
PRAGMA user_version=1;
PRAGMA application_id={APPLICATION_ID};
'''


@contextmanager
def connection(projects, project_id, create=False):
    identity(project_id); project = Path(projects) / project_id
    if not create and not (project / 'RemoteHosts').exists() and not (project / 'RemoteHosts').is_symlink(): yield None; return
    if project.resolve(strict=True) != project: raise CatalogFault('Invalid remote project storage.', 503)
    directory = project / 'RemoteHosts'; path = directory / 'Jobs.sqlite'
    if not directory.exists() and not create: yield None; return
    directory = private_directory(directory)
    if not path.exists() and not path.is_symlink():
        if not create: yield None; return
        temporary = directory / ('.initial-' + str(uuid.uuid4()) + '.sqlite')
        if len(list(directory.glob('.initial-*.sqlite'))) >= 8: raise CatalogFault('Interrupted remote job initialization needs maintenance.', 503)
        with closing(sqlite3.connect(temporary)) as fresh: fresh.executescript(SCHEMA)
        temporary.chmod(0o600)
        with temporary.open('rb') as stream: os.fsync(stream.fileno())
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.renameat2(-100, os.fsencode(temporary), -100, os.fsencode(path), 1) != 0: raise CatalogFault('Remote job initialization needs reconciliation.', 503)
        sync(directory)
    regular(path)
    db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=2); db.row_factory = sqlite3.Row
    try:
        if db.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID or db.execute('PRAGMA user_version').fetchone()[0] != 1 or db.execute('PRAGMA quick_check(1)').fetchone()[0] != 'ok':
            raise CatalogFault('Remote job schema or integrity needs maintenance. Original data was preserved.', 503)
        db.execute('PRAGMA synchronous=FULL'); yield db
    finally: db.close()


def public(row):
    if row is None: raise CatalogFault('The original remote job was not found.', 404)
    value = json.loads(row['payload'])
    return {'id': row['id'], 'requestId': row['request_id'], 'projectId': value['actor']['projectId'],
            'sessionId': row['session_id'], 'runId': row['run_id'], 'hostId': row['host_id'],
            'hostName': value['host']['name'], 'operation': value['operation'],
            'state': 'unknown_reviewed' if row['state'] == 'unknown' and value.get('review') else row['state'], 'phase': row['phase'],
            'deadlineAt': value.get('deadlineAt'),
            **({'endpointIdentity': value['endpointIdentity']} if value.get('endpointIdentity') else {}),
            **({'review': value['review']} if value.get('review') else {}),
            **({'transfer': value['files']} if value.get('files') else {'command': value.get('command')}),
            'binding': {k: value['host'][k] for k in ('id', 'endpointRevision', 'credentialRevision', 'trustRevision')},
            'createdAt': row['created_at'], 'updatedAt': row['updated_at'], 'result': json.loads(row['result']) if row['result'] else None}


def read(projects, project_id, job_id, session_id=None):
    identity(job_id)
    with connection(projects, project_id) as db:
        row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone() if db else None
        if row is not None and session_id is not None and row['session_id'] != session_id: raise CatalogFault('This remote job belongs to another session.', 403)
        return public(row)


def update(projects, project_id, job_id, state, phase, result=None):
    with connection(projects, project_id) as db, db:
        if state not in (*ACTIVE, 'completed', 'failed', 'unknown', 'unknown_reviewed'): raise CatalogFault('Invalid remote job transition.', 503)
        if result is not None and len(json.dumps(result, ensure_ascii=True).encode()) > 220000: raise CatalogFault('Remote result exceeds its quota.', 503)
        db.execute('UPDATE jobs SET state=?,phase=?,result=?,updated_at=? WHERE id=?', (state, phase, json.dumps(result) if result is not None else None, now(), job_id))


def bind_endpoint(projects, project_id, job_id, value):
    with connection(projects, project_id) as db, db:
        row = db.execute('SELECT payload FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row is None: raise CatalogFault('The accepted remote job disappeared.', 503)
        payload = json.loads(row['payload']); payload['endpointIdentity'] = value
        db.execute("UPDATE jobs SET payload=?,phase='endpoint_bound',updated_at=? WHERE id=?", (json.dumps(payload), now(), job_id))
        return payload


def recover(projects):
    from store import connect
    with closing(connect(Path(projects))) as db: ids = [row[0] for row in db.execute("SELECT id FROM projects WHERE state='ready'")]
    for project_id in ids:
        with connection(projects, project_id) as db:
            if db is None: continue
            with db:
                for row in db.execute("SELECT id,result,phase FROM jobs WHERE state IN ('queued','starting','running','stopping')").fetchall():
                    previous = json.loads(row['result']) if row['result'] else {}
                    safe_phase = row['phase'] in ('accepted', 'endpoint_bound', 'client_preparation', 'remote_read')
                    value = {**previous, 'localClientEndConfirmed': False, 'remoteProcessEndConfirmed': False, 'effectConfirmed': False,
                             'message': 'The original worker was interrupted before effect dispatch. Nothing was replayed.' if safe_phase else 'The original worker was interrupted. No remote operation was replayed.'}
                    db.execute("UPDATE jobs SET state=?,phase='worker_interrupted',result=?,updated_at=? WHERE id=?", ('failed' if safe_phase else 'unknown', json.dumps(value), now(), row['id']))


def host_busy(projects, host_id):
    path = Path(projects) / 'Projects.sqlite'
    if not path.exists(): return False
    regular(path)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as db: ids = [row[0] for row in db.execute('SELECT id FROM projects')]
    for project_id in ids:
        with connection(projects, project_id) as db:
            if db:
                for row in db.execute("SELECT state,payload FROM jobs WHERE host_id=? AND state IN ('queued','starting','running','stopping','unknown')", (host_id,)):
                    if row['state'] != 'unknown' or not json.loads(row['payload']).get('review'): return True
    return False
