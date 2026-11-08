"""Private, bounded originals of final provider bodies. No credentials or replay.

Bodies are compressed once and content addressed within a session. Expiring an
old body keeps its request identity/hash and an explicit unavailable state.
"""
import hashlib
import json
import sqlite3
import zlib

from session_store import encode, now
from store import ProjectFault

MAX_BODY = 8 * 1024 * 1024
BODY_BUDGET = 96 * 1024 * 1024
MAX_REQUESTS = 10000


def exists(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='studio_requests'").fetchone() is not None


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS studio_request_bodies(
        session_id TEXT NOT NULL REFERENCES sessions(id),sha256 TEXT NOT NULL,
        bytes INTEGER NOT NULL,compressed BLOB NOT NULL,PRIMARY KEY(session_id,sha256))''')
    db.execute('''CREATE TABLE IF NOT EXISTS studio_requests(
        seq INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL REFERENCES sessions(id),
        run_id TEXT NOT NULL REFERENCES runs(id),request_id TEXT NOT NULL UNIQUE,
        sha256 TEXT NOT NULL,metadata TEXT NOT NULL,dispatch_at TEXT)''')
    db.execute('CREATE INDEX IF NOT EXISTS studio_requests_session ON studio_requests(session_id,seq)')
    db.execute('CREATE INDEX IF NOT EXISTS studio_requests_sent ON studio_requests(session_id,seq) WHERE dispatch_at IS NOT NULL')
    db.execute('CREATE INDEX IF NOT EXISTS studio_requests_body ON studio_requests(session_id,sha256,seq)')
    db.execute('''CREATE TABLE IF NOT EXISTS studio_request_retention(
        session_id TEXT PRIMARY KEY REFERENCES sessions(id),dropped INTEGER NOT NULL DEFAULT 0)''')


def capture(store, operation, raw, binding, policy):
    data = raw.encode('utf-8')
    if not 0 < len(data) <= MAX_BODY:
        raise ProjectFault('The complete model request could not be recorded. No request was sent.', 503)
    digest = hashlib.sha256(data).hexdigest()
    # Only explicit non-secret model facts. Do not archive transport binding,
    # headers, credential grants, account tokens or the HTTP bootstrap.
    facts = {key: binding.get(key) for key in ('protocol','model','contextWindow','maxOutputTokens','imageAction')}
    body = json.loads(raw)
    for key in ('max_output_tokens','max_completion_tokens','max_tokens'):
        if type(body.get(key)) is int and body[key] > 0:
            facts['maxOutputTokens'] = body[key]; break
    metadata = {'schema':1,'capturedAt':now(),'purpose':operation.get('purpose','conversation'),
        'owner':operation['owner'],'providerId':operation['selection']['providerId'],
        'model':binding['model'],'protocol':binding['protocol'],'bytes':len(data),
        'facts':facts,'contextPolicy':policy,'dispatchAt':None,'responseAt':None,'httpStatus':None}
    packed = zlib.compress(data, 3)
    try:
        with store.db:
            schema(store.db)
            from session_budgets import total
            used = total(store.db, operation['sessionId'], 'requests')
            duplicate = store.db.execute('SELECT 1 FROM studio_request_bodies WHERE session_id=? AND sha256=?',
                                         (operation['sessionId'],digest)).fetchone()
            if not duplicate:
                # Indexed request order, bounded archive. Preserve original call
                # receipts; only the optional historical body expires.
                while used + len(packed) > BODY_BUDGET:
                    oldest = store.db.execute('''SELECT b.sha256,length(b.compressed) AS size
                        FROM studio_requests r JOIN studio_request_bodies b
                        ON b.session_id=r.session_id AND b.sha256=r.sha256
                        WHERE r.session_id=? ORDER BY r.seq LIMIT 1''', (operation['sessionId'],)).fetchone()
                    if oldest is None: raise ProjectFault('The model request archive is full. No request was sent.',503)
                    store.db.execute('DELETE FROM studio_request_bodies WHERE session_id=? AND sha256=?',
                                     (operation['sessionId'],oldest['sha256']))
                    used -= oldest['size']
                store.db.execute('INSERT INTO studio_request_bodies VALUES (?,?,?,?)',
                                 (operation['sessionId'],digest,len(data),packed))
            store.db.execute('INSERT INTO studio_requests(session_id,run_id,request_id,sha256,metadata) VALUES (?,?,?,?,?)',
                             (operation['sessionId'],operation['runId'],operation['requestId'],digest,encode(metadata)))
            # Keep at most 10k small metadata rows, independently of compression.
            cutoff = store.db.execute('SELECT seq FROM studio_requests WHERE session_id=? ORDER BY seq DESC LIMIT 1 OFFSET ?',
                                      (operation['sessionId'],MAX_REQUESTS-1)).fetchone()
            if cutoff:
                removed = store.db.execute('DELETE FROM studio_requests WHERE session_id=? AND seq<?',
                                           (operation['sessionId'],cutoff['seq'])).rowcount
                if removed:
                    store.db.execute('INSERT INTO studio_request_retention VALUES (?,?) ON CONFLICT(session_id) DO UPDATE SET dropped=dropped+excluded.dropped',
                                     (operation['sessionId'],removed))
                    store.db.execute('''DELETE FROM studio_request_bodies WHERE session_id=? AND NOT EXISTS
                        (SELECT 1 FROM studio_requests r WHERE r.session_id=studio_request_bodies.session_id AND r.sha256=studio_request_bodies.sha256)''',
                        (operation['sessionId'],))
    except (sqlite3.Error, OSError) as error:
        raise ProjectFault('The complete model request could not be saved. No request was sent.',503) from error
    return digest


def transport(store, rid, stage, status=None):
    if stage not in ('dispatch','response'): raise ValueError('Invalid request observation')
    with store.db:
        row=store.db.execute('SELECT metadata FROM studio_requests WHERE request_id=?',(rid,)).fetchone()
        if not row: raise ProjectFault('The original model request is unavailable.',503)
        meta=json.loads(row['metadata'])
        if stage=='dispatch':
            meta['dispatchAt']=meta['dispatchAt'] or now()
            store.db.execute('UPDATE studio_requests SET dispatch_at=? WHERE request_id=?',(meta['dispatchAt'],rid))
        else: meta.update(responseAt=now(),httpStatus=status)
        store.db.execute('UPDATE studio_requests SET metadata=? WHERE request_id=?',(encode(meta),rid))


def body(store, sid, rid):
    # Check exact session membership before reading any payload.
    store.row(sid)
    row=store.db.execute('''SELECT r.sha256,b.bytes,b.compressed FROM studio_requests r
        LEFT JOIN studio_request_bodies b ON b.session_id=r.session_id AND b.sha256=r.sha256
        WHERE r.session_id=? AND r.request_id=?''',(sid,rid)).fetchone() if exists(store.db) else None
    if not row: raise ProjectFault('Original model request not found.',404)
    if row['compressed'] is None: raise ProjectFault('This original request body is no longer retained.',410)
    try:
        decoder=zlib.decompressobj();raw=decoder.decompress(row['compressed'],MAX_BODY+1)
        if (not decoder.eof or decoder.unused_data or len(raw)!=row['bytes'] or len(raw)>MAX_BODY
                or hashlib.sha256(raw).hexdigest()!=row['sha256']): raise ValueError()
        raw.decode('utf-8')
    except (zlib.error,ValueError,UnicodeError) as error:
        raise ProjectFault('The original request body failed its integrity check.',503) from error
    return raw
