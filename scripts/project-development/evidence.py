"""Opaque private evidence receipts. Guest-provided names never select a host path."""
import base64
import hashlib
import json
import os
import stat
import struct
import uuid
from contracts import DevelopmentFault, LIMITS, encode, identity
from jobs import now
from layout import save, sync


def setup(store):
    with store.db: store.db.execute('CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY, job_id TEXT NOT NULL, payload TEXT NOT NULL)')


def publish(store, job, kind, data, **fields):
    setup(store); evidence_id = str(uuid.uuid4()); root = store.evidence(job['id'])
    if store.db.execute('SELECT COUNT(*) FROM evidence WHERE job_id=?', (job['id'],)).fetchone()[0] >= 128:
        raise DevelopmentFault('This job reached its evidence limit. Existing evidence is preserved.')
    extension = '.png' if kind == 'screenshot' else '.bin'
    file = root / (evidence_id + extension); temporary = file.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
    os.rename(temporary, file); sync(root)
    value = {'id': evidence_id, 'jobId': job['id'], 'projectId': store.id, 'kind': kind,
        'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'createdAt': now(),
        'bootId': (job.get('target') or {}).get('bootId'), 'process': job.get('process'), **fields}
    save(root / (evidence_id + '.json'), value)
    with store.db: store.db.execute('INSERT INTO evidence VALUES(?,?,?)', (evidence_id, job['id'], encode(value)))
    return value


def list_for(store, job_id):
    setup(store); store.get(job_id)
    return [json.loads(r[0]) for r in store.db.execute('SELECT payload FROM evidence WHERE job_id=? ORDER BY rowid DESC LIMIT 32', (job_id,))]


def history(store, job_id, before=None):
    setup(store); store.get(job_id)
    if before is not None and (type(before) is not int or before < 1): raise DevelopmentFault('Invalid evidence cursor.', 400)
    rows = store.db.execute('SELECT rowid,payload FROM evidence WHERE job_id=? AND (? IS NULL OR rowid<?) ORDER BY rowid DESC LIMIT 33',
        (job_id, before, before)).fetchall()
    return {'items': [json.loads(r[1]) for r in rows[:32]], 'before': rows[31][0] if len(rows) > 32 else None}


def read(store, job_id, evidence_id):
    setup(store); store.get(job_id)
    row = store.db.execute('SELECT payload FROM evidence WHERE id=? AND job_id=?', (identity(evidence_id), identity(job_id))).fetchone()
    if not row: raise DevelopmentFault('Development evidence not found.', 404)
    value = json.loads(row[0]); extension = '.png' if value['kind'] == 'screenshot' else '.bin'
    path = store.evidence(job_id) / (evidence_id + extension)
    maximum = LIMITS['screenshotBytes'] if value['kind'] == 'screenshot' else LIMITS['fileBytes']
    expected = value['bytes']
    if type(expected) is not int or not 0 <= expected <= maximum:
        raise DevelopmentFault('The evidence file exceeds its byte limit.')
    try:
        if path.resolve(strict=True) != path: raise DevelopmentFault('Invalid evidence file path.')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != expected:
                raise DevelopmentFault('The evidence file is missing or its checksum changed.')
            data = stream.read(expected + 1)
    except OSError: raise DevelopmentFault('The evidence file is missing or unavailable.') from None
    if len(data) != expected or hashlib.sha256(data).hexdigest() != value['sha256']:
        raise DevelopmentFault('The evidence file is missing or its checksum changed.')
    return response(value, data)


def response(value, data):
    return {'metadata': value, 'base64': base64.b64encode(data).decode()}


def png(value):
    try: data = base64.b64decode(value['base64'], validate=True)
    except (ValueError, KeyError): raise DevelopmentFault('The VM returned an invalid PNG response.') from None
    if len(data) > LIMITS['screenshotBytes'] or len(data) < 33 or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        raise DevelopmentFault('The VM image exceeds the screenshot budget or has an invalid format.')
    width, height = struct.unpack('>II', data[16:24])
    if not 0 < width <= LIMITS['screenshotMaxWidth'] or not 0 < height <= LIMITS['screenshotMaxHeight']:
        raise DevelopmentFault('The guest display exceeds the qualified screenshot dimensions.')
    return data, width, height
