"""Human-only local uncertainty review; original remote outcomes never change."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from catalog import CatalogFault, fields, identity, now, regular
from actor import encode, ordinary
import job_store as jobs
from project_use import acquire


def projects_at(projects):
    path = Path(projects) / 'Projects.sqlite'; regular(path)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
        values = db.execute("SELECT id,name FROM projects WHERE state='ready' ORDER BY id LIMIT 1001").fetchall()
    if len(values) > 1000: raise CatalogFault('Remote project inventory exceeds its review limit.', 503)
    return values


def listings(projects, host_id):
    identity(host_id); values = []
    for project_id, name in projects_at(projects):
        with jobs.connection(projects, project_id) as db:
            if db is None: continue
            rows = db.execute('SELECT id,request_id,session_id,run_id,host_id,state,phase,payload,NULL AS result,created_at,updated_at FROM jobs WHERE host_id=? ORDER BY updated_at DESC LIMIT 33', (host_id,)).fetchall()
            for row in rows:
                value = jobs.public(row)
                values.append({**{k: value[k] for k in ('id', 'projectId', 'sessionId', 'hostId', 'hostName', 'requestId', 'operation', 'state', 'phase', 'createdAt', 'updatedAt')},
                               'projectName': name, 'commandPreview': value.get('command', '')[:160], 'action': value.get('transfer', {}).get('action')})
        values.sort(key=lambda value: (value['updatedAt'], value['id']), reverse=True); values = values[:33]
    selected = []; used = 0
    for value in values[:32]:
        size = len(encode(value).encode('ascii', errors='backslashreplace'))
        if used + size > 100000: break
        used += size; selected.append(value)
    return {'jobs': selected, 'truncated': len(values) > len(selected)}


def bound(projects, project_id, host_id, job_id):
    identity(project_id); identity(host_id); value = jobs.read(projects, project_id, job_id)
    if value['hostId'] != host_id: raise CatalogFault('The original job belongs to another saved host.', 403)
    return value


def details(projects, project_id, host_id, job_id):
    value = bound(projects, project_id, host_id, job_id); result = dict(value.get('result') or {})
    for key in ('stdout', 'stderr', 'content', 'message'):
        if isinstance(result.get(key), str) and len(result[key]) > 4096: result[key] = result[key][:4096]; result['displayTruncated'] = True
    if isinstance(result.get('entries'), list) and len(result['entries']) > 16: result['entries'] = result['entries'][:16]; result['displayTruncated'] = True
    if len(json.dumps(result, ensure_ascii=True).encode()) > 100000:
        result = {'displayTruncated': True, 'message': 'The complete original result is retained. Use the original permitted session job read for its full saved output.'}
    return {**value, 'result': result}


def receipt(projects, project_id, host_id, job_id, request_id):
    bound(projects, project_id, host_id, job_id); identity(request_id)
    with jobs.connection(projects, project_id) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='reviews'").fetchone(): raise CatalogFault('The original review receipt was not found.', 404)
        row = db.execute('SELECT job_id,result FROM reviews WHERE request_id=?', (request_id,)).fetchone()
        if row is None: raise CatalogFault('The original review receipt was not found.', 404)
        if row['job_id'] != job_id: raise CatalogFault('This review request belongs to another job.', 403)
        return json.loads(row['result'])


def review(projects, project_id, host_id, job_id, content):
    fields(content, ['requestId', 'expectedUpdatedAt', 'confirmUnknown']); identity(content['requestId']); identity(project_id); identity(host_id); identity(job_id)
    if content['confirmUnknown'] is not True or not isinstance(content['expectedUpdatedAt'], str) or not 1 <= len(content['expectedUpdatedAt']) <= 100:
        raise CatalogFault('Explicitly acknowledge the unchanged original unknown result.', 400)
    fingerprint = hashlib.sha256(encode({'projectId': project_id, 'hostId': host_id, 'jobId': job_id, 'input': content}).encode()).hexdigest()
    with acquire(projects, project_id), jobs.connection(projects, project_id) as db:
        if db is None: raise CatalogFault('The original job was not found.', 404)
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('CREATE TABLE IF NOT EXISTS reviews(request_id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,job_id TEXT NOT NULL,result TEXT NOT NULL)')
            previous = db.execute('SELECT * FROM reviews WHERE request_id=?', (content['requestId'],)).fetchone()
            if previous:
                if previous['fingerprint'] != fingerprint: raise CatalogFault('This review request ID belongs to another acknowledgement.', 409)
                return json.loads(previous['result'])
            if db.execute('SELECT count(*) FROM reviews').fetchone()[0] >= 1000: raise CatalogFault('Review history needs local maintenance.', 503)
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone(); value = jobs.public(row)
            if value['hostId'] != host_id: raise CatalogFault('The original job belongs to another host.', 403)
            if value['state'] != 'unknown' or value['updatedAt'] != content['expectedUpdatedAt']: raise CatalogFault('The original job changed. Reload and inspect its current receipt.', 409)
            session_db = Path(projects) / project_id / 'Sessions/Sessions.sqlite'; ordinary(session_db)
            with closing(sqlite3.connect(session_db.as_uri() + '?mode=ro', uri=True, timeout=2)) as sessions:
                if sessions.execute('SELECT 1 FROM runs WHERE busy=1 LIMIT 1').fetchone(): raise CatalogFault('Finish or stop current project agent runs before acknowledging uncertainty.', 409)
            payload = json.loads(row['payload']); stamp = now()
            payload['review'] = {'requestId': content['requestId'], 'reviewedAt': stamp, 'originalOutcome': 'unknown',
                                 'message': 'User acknowledged uncertainty and allowed new work. This is not command success or confirmed remote termination.'}
            # Keep the original terminal state readable by older v9 workers.
            # They conservatively continue to see unknown after a rollback.
            db.execute("UPDATE jobs SET payload=?,updated_at=? WHERE id=?", (json.dumps(payload), stamp, job_id))
            result = {'requestId': content['requestId'], 'projectId': project_id, 'hostId': host_id, 'jobId': job_id,
                      'state': 'unknown_reviewed', 'originalOutcome': 'unknown', 'reviewedAt': stamp, 'remoteProcessEndConfirmed': False}
            db.execute('INSERT INTO reviews VALUES(?,?,?,?)', (content['requestId'], fingerprint, job_id, json.dumps(result)))
            db.commit(); return result
        finally:
            if db.in_transaction: db.rollback()
