"""Immutable, bounded archive cache. Roadmap content/revision are never changed."""
from contextlib import contextmanager
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
import uuid

from export_format import archive_text
from reads import root_row
from storage import APPLICATION_ID, SCHEMA_VERSION, RoadmapFault, folder, timestamp
from layout import sync
from validation import fields, identity, integer

MAX_ARCHIVE_BYTES = 96 * 1024 * 1024
MAX_CACHE_BYTES = 512 * 1024 * 1024
PUBLIC = ('id', 'projectId', 'roadmapId', 'versionId', 'number', 'filename', 'revision',
          'currentVersionId', 'encoding', 'byteLength', 'sha256', 'createdAt')


def cache_directory(projects, project_id, create=False):
    directory = Path(projects).absolute() / project_id / 'Roadmap/Exports'
    if create:
        directory.mkdir(mode=0o700, exist_ok=True)
        sync(directory.parent)
    if not directory.exists() and not directory.is_symlink():
        raise RoadmapFault('The saved export is unavailable.', 410)
    folder(directory)
    return directory


def regular(path, maximum):
    info = path.lstat()
    if (path.resolve(strict=True) != path or not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1 or info.st_size > maximum):
        raise RoadmapFault('Invalid saved export. Existing files were preserved.', 503)
    return info


def manifest(directory, project_id, export_id):
    identity(export_id)
    path = directory / export_id
    if not path.exists() and not path.is_symlink():
        raise RoadmapFault('The saved export is unavailable. Prepare a new export.', 410)
    folder(path)
    info_file = path / 'export.json'; regular(info_file, 8192)
    value = json.loads(info_file.read_text(encoding='utf-8'))
    fields(value, [*PUBLIC, 'schema', 'requestHash'])
    if (value['schema'] != 1 or value['id'] != export_id or value['projectId'] != project_id
            or value['encoding'] != 'utf-8' or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.X', value['number'])
            or value['filename'] != value['number'] + '.txt'
            or not re.fullmatch(r'[a-f0-9]{64}', value['sha256']) or not re.fullmatch(r'[a-f0-9]{64}', value['requestHash'])):
        raise RoadmapFault('Invalid saved export metadata. Existing files were preserved.', 503)
    for key in ('roadmapId', 'versionId', 'currentVersionId'):
        identity(value[key])
    integer(value['revision'], 1, 9007199254740991)
    integer(value['byteLength'], 1, MAX_ARCHIVE_BYTES)
    return value


def public(value):
    return {key: value[key] for key in PUBLIC}


@contextmanager
def open_archive(projects, project_id, export_id):
    directory = cache_directory(projects, project_id)
    value = manifest(directory, project_id, export_id)
    path = directory / export_id / 'archive.txt'
    info = regular(path, MAX_ARCHIVE_BYTES)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if (before.st_ino, before.st_dev, before.st_size) != (info.st_ino, info.st_dev, value['byteLength']):
            raise RoadmapFault('The saved export changed. Existing files were preserved.', 503)
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = os.fstat(stream.fileno())
        if digest != value['sha256'] or (before.st_mtime_ns, before.st_ctime_ns, before.st_size) != (after.st_mtime_ns, after.st_ctime_ns, after.st_size):
            raise RoadmapFault('The saved export failed its integrity check. Existing files were preserved.', 503)
        stream.seek(0)
        yield public(value), stream


def quota(directory):
    total = 0
    entries = list(directory.iterdir())
    if len(entries) >= 1024:
        raise RoadmapFault('Saved export storage has reached its entry limit. Roadmap data was preserved.', 413)
    for entry in entries:
        if entry.name == '.write.lock':
            regular(entry, 0)
            continue
        folder(entry)
        children = list(entry.iterdir())
        if len(children) > 8:
            raise RoadmapFault('Saved export storage needs maintenance. Existing files were preserved.', 503)
        for child in children:
            total += regular(child, MAX_ARCHIVE_BYTES).st_size
    if total > MAX_CACHE_BYTES - MAX_ARCHIVE_BYTES - 64 * 1024 * 1024 - 8192:
        raise RoadmapFault('Saved export storage has reached its size limit. Roadmap data was preserved.', 413)


def record_receipt(db, request_id, fingerprint, result):
    db.execute('BEGIN IMMEDIATE')
    try:
        previous = db.execute('SELECT request_hash,result FROM receipts WHERE request_id=?', (request_id,)).fetchone()
        if previous:
            if previous['request_hash'] != fingerprint or json.loads(previous['result']) != result:
                raise RoadmapFault('This request ID belongs to a different roadmap operation.', 409)
        else:
            if db.execute('SELECT count(*) FROM receipts').fetchone()[0] >= 50000:
                raise RoadmapFault('Roadmap receipt storage needs maintenance. Existing data was preserved.', 503)
            db.execute('INSERT INTO receipts(request_id,request_hash,revision,result,created_at) VALUES(?,?,?,?,?)',
                       (request_id, fingerprint, result['revision'], json.dumps(result, ensure_ascii=False), timestamp()))
        db.commit()
    finally:
        db.rollback()


def prepare(db, projects, project_id, body):
    fields(body, ['requestId', 'versionId', 'expectedRevision', 'currentVersionId'])
    for key in ('requestId', 'versionId', 'currentVersionId'):
        identity(body[key])
    integer(body['expectedRevision'], 1, 9007199254740991)
    fingerprint = hashlib.sha256(json.dumps({'operation': 'export', 'projectId': project_id, **body},
                                           sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    original = db.execute('SELECT request_hash,result FROM receipts WHERE request_id=?', (body['requestId'],)).fetchone()
    if original and original['request_hash'] != fingerprint:
        raise RoadmapFault('This request ID belongs to a different roadmap operation.', 409)
    directory = cache_directory(projects, project_id, create=True)
    lock = os.open(directory / '.write.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode) or os.fstat(lock).st_nlink != 1:
            raise RoadmapFault('Invalid export lock.', 503)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RoadmapFault('Another export is being prepared. Retry the original request.', 409) from None
        destination = directory / body['requestId']
        if destination.exists() or destination.is_symlink():
            old = manifest(directory, project_id, body['requestId'])
            if old['requestHash'] != fingerprint:
                raise RoadmapFault('This export request ID was already used for different input.', 409)
            with open_archive(projects, project_id, body['requestId']) as (result, _):
                record_receipt(db, body['requestId'], fingerprint, result)
                return result
        if original:
            raise RoadmapFault('The original saved export is unavailable. Prepare a new request.', 410)
        root = root_row(db)
        if root['revision'] != body['expectedRevision'] or root['current_version_id'] != body['currentVersionId']:
            raise RoadmapFault('The roadmap changed. Reload before preparing an export.', 409)
        quota(directory)
        stage = directory / ('.stage-' + str(uuid.uuid4()))
        stage.mkdir(mode=0o700)
        snapshot = stage / 'Snapshot.sqlite'
        deadline = time.monotonic() + 18
        copied = sqlite3.connect(snapshot)
        try:
            copied.row_factory = sqlite3.Row
            page_size = db.execute('PRAGMA page_size').fetchone()[0]
            def progress(_status, _remaining, total):
                if total * page_size > 64 * 1024 * 1024 or time.monotonic() > deadline - 10:
                    raise RoadmapFault('The export snapshot exceeded its bounds. Roadmap data was preserved.', 413)
            db.backup(copied, pages=256, progress=progress, sleep=0.01)
            if (copied.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION
                    or copied.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID
                    or copied.execute('PRAGMA quick_check(1)').fetchone()[0] != 'ok'
                    or copied.execute('PRAGMA foreign_key_check').fetchone()):
                raise RoadmapFault('The export snapshot could not be verified. Existing data was preserved.', 503)
            frozen = root_row(copied)
            if frozen['project_id'] != project_id or frozen['revision'] != body['expectedRevision'] or frozen['current_version_id'] != body['currentVersionId']:
                raise RoadmapFault('The roadmap changed during snapshot preparation. Retry after reloading.', 409)
            version = copied.execute('SELECT * FROM versions WHERE id=?', (body['versionId'],)).fetchone()
            if version is None:
                raise RoadmapFault('Main version not found in this project.', 404)
            digest, size = hashlib.sha256(), 0
            fd = os.open(stage / 'archive.txt', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as output:
                for part in archive_text(copied, version):
                    raw = part.encode('utf-8'); size += len(raw)
                    if size > MAX_ARCHIVE_BYTES or time.monotonic() > deadline:
                        raise RoadmapFault('The complete archive exceeds the export limit. No partial archive was published.', 413)
                    output.write(raw); digest.update(raw)
                output.flush(); os.fchmod(output.fileno(), 0o400); os.fsync(output.fileno())
            number = f'{version["major"]}.{version["minor"]}.X'
            value = {'schema': 1, 'id': body['requestId'], 'projectId': project_id, 'roadmapId': frozen['id'],
                     'versionId': version['id'], 'number': number, 'filename': number + '.txt',
                     'revision': frozen['revision'], 'currentVersionId': frozen['current_version_id'],
                     'encoding': 'utf-8', 'byteLength': size, 'sha256': digest.hexdigest(),
                     'createdAt': timestamp(), 'requestHash': fingerprint}
        finally:
            copied.close()
        # The sealed archive is the stable snapshot. Discard only our temporary
        # database copy; published exports never contain the full project DB.
        snapshot.unlink()
        meta_fd = os.open(stage / 'export.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
        with os.fdopen(meta_fd, 'w', encoding='utf-8') as output:
            json.dump(value, output, ensure_ascii=False); output.flush(); os.fsync(output.fileno())
        sync(stage)
        rename = ctypes.CDLL(None, use_errno=True).renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(stage), -100, os.fsencode(destination), 1):
            raise OSError(ctypes.get_errno(), 'Export publication failed.')
        sync(directory)
        result = public(value)
        record_receipt(db, body['requestId'], fingerprint, result)
        return result
    finally:
        os.close(lock)


def chunk(projects, project_id, request):
    fields(request, ['operation', 'projectId', 'exportId'], ['offset', 'limit'])
    offset = integer(request.get('offset', 0), 0, MAX_ARCHIVE_BYTES)
    amount = integer(request.get('limit', 32768), 4, 65536)
    with open_archive(projects, project_id, identity(request['exportId'])) as (info, stream):
        if offset > info['byteLength']:
            raise RoadmapFault('Invalid archive offset.', 400)
        stream.seek(offset)
        raw = stream.read(amount)
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError as error:
            if error.reason != 'unexpected end of data' or error.end != len(raw):
                raise RoadmapFault('Use the next archive offset returned by the server.', 400) from None
            raw = raw[:error.start]; text = raw.decode('utf-8')
        next_offset = offset + len(raw)
        return {'export': info, 'text': text, 'offset': offset,
                'nextOffset': next_offset if next_offset < info['byteLength'] else None}
