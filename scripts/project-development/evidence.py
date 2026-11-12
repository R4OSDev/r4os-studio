"""Opaque private evidence receipts. Guest-provided names never select a host path."""
import base64
import hashlib
import io
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


def write_bytes(file, data):
    temporary = file.with_name(file.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.rename(temporary, file)
    finally:
        temporary.unlink(missing_ok=True)


def publish(store, job, kind, data, *, webp=None, **fields):
    setup(store); evidence_id = str(uuid.uuid4()); root = store.evidence(job['id'])
    if store.db.execute('SELECT COUNT(*) FROM evidence WHERE job_id=?', (job['id'],)).fetchone()[0] >= 128:
        raise DevelopmentFault('This job reached its evidence limit. Existing evidence is preserved.')
    extension = '.png' if kind == 'screenshot' else '.bin'
    file = root / (evidence_id + extension)
    metadata = root / (evidence_id + '.json')
    preview = root / (evidence_id + '.webp')
    value = {'id': evidence_id, 'jobId': job['id'], 'projectId': store.id, 'kind': kind,
        'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'createdAt': now(),
        'bootId': (job.get('target') or {}).get('bootId'), 'process': job.get('process'), **fields}
    if webp is not None:
        limit = LIMITS['screenshotBytes']
        value['preview'] = {'mediaType':'image/webp','bytes':len(webp),'sha256':hashlib.sha256(webp).hexdigest()}
        if not webp:
            value['preview']['error'] = f'The WebP preview could not be encoded. The {len(data)}-byte PNG was archived.'
        elif len(webp) > limit:
            value['preview']['error'] = (f'The WebP preview is {len(webp)} bytes and exceeds the {limit}-byte transfer limit. '
                                         f'The {len(data)}-byte PNG was archived.')
    written = []
    try:
        write_bytes(file, data); written.append(file)
        if webp is not None and 'error' not in value['preview']:
            write_bytes(preview, webp); written.append(preview)
        save(metadata, value); written.append(metadata)
        sync(root)
        with store.db: store.db.execute('INSERT INTO evidence VALUES(?,?,?)', (evidence_id, job['id'], encode(value)))
    except Exception:
        for path in written: path.unlink(missing_ok=True)
        raise
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


def read(store, job_id, evidence_id, *, mode='original'):
    setup(store); store.get(job_id)
    row = store.db.execute('SELECT payload FROM evidence WHERE id=? AND job_id=?', (identity(evidence_id), identity(job_id))).fetchone()
    if not row: raise DevelopmentFault('Development evidence not found.', 404)
    value = json.loads(row[0]); screenshot = value['kind'] == 'screenshot'
    extension = '.png' if screenshot else '.bin'
    limit = LIMITS['screenshotOriginalBytes'] if screenshot else LIMITS['fileBytes']
    media = value
    if mode == 'download' and not screenshot:
        raise DevelopmentFault('Only a saved screenshot has an original PNG.', 400)
    if mode in ('preview', 'legacy') and screenshot:
        limit = LIMITS['screenshotBytes']
        if mode == 'preview' and 'preview' in value:
            media = value['preview']; extension = '.webp'
            if media.get('error'):
                return {'metadata':value,'previewError':media['error']}
        elif type(value['bytes']) is int and value['bytes'] > limit:
            return {'metadata':value,'previewError':'The original PNG exceeds the legacy screenshot transfer limit. It was archived.'}
    path = store.evidence(job_id) / (evidence_id + extension)
    expected = media['bytes']
    if type(expected) is not int or not 0 <= expected <= limit:
        raise DevelopmentFault('The evidence file exceeds its byte limit.')
    try:
        if path.resolve(strict=True) != path: raise DevelopmentFault('Invalid evidence file path.')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != expected:
                raise DevelopmentFault('The evidence file is missing or its checksum changed.')
            if mode == 'download': return {'metadata':value,'path':str(path)}
            data = stream.read(expected + 1)
    except OSError: raise DevelopmentFault('The evidence file is missing or unavailable.') from None
    if len(data) != expected or hashlib.sha256(data).hexdigest() != media['sha256']:
        raise DevelopmentFault('The evidence file is missing or its checksum changed.')
    return preview_response(value,data) if extension=='.webp' else response(value, data)


def response(value, data):
    return {'metadata': value, 'base64': base64.b64encode(data).decode()}


def preview_response(value, data):
    error = value['preview'].get('error')
    if error: return {'metadata':value,'previewError':error}
    return {**response(value,data),'mediaType':'image/webp'}


def png(value):
    try: data = value if isinstance(value,bytes) else base64.b64decode(value['base64'], validate=True)
    except (ValueError, KeyError): raise DevelopmentFault('The VM returned an invalid PNG response.') from None
    if len(data) > LIMITS['screenshotOriginalBytes'] or len(data) < 33 or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        raise DevelopmentFault('The VM image exceeds the screenshot budget or has an invalid format.')
    width, height = struct.unpack('>II', data[16:24])
    if not 0 < width <= LIMITS['screenshotMaxWidth'] or not 0 < height <= LIMITS['screenshotMaxHeight']:
        raise DevelopmentFault('The guest display exceeds the qualified screenshot dimensions.')
    return data, width, height


def lossless_webp(data):
    try: from PIL import Image
    except ImportError: return b''
    try:
        with Image.open(io.BytesIO(data), formats=['PNG']) as original:
            frame = original.convert('RGBA')
    except (OSError, ValueError):
        raise DevelopmentFault('The VM returned an invalid PNG response.') from None
    output = io.BytesIO()
    try: frame.save(output,'WEBP',lossless=True,exact=True)
    except (OSError, KeyError, ValueError): return b''
    return output.getvalue()
