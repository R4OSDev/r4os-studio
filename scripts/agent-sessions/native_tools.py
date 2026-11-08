"""Refresh owned Codex tool metadata before resume, preserving every history record.

Codex 0.163.0 loads dynamic tools from the first session_meta record. Its resume
RPC has no dynamicTools field. Only that record's tool list is changed here;
original bytes and byte-cursor values are retained in a durable private journal.
No native process, turn, tool call, Goal or queued input is started by this code.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import resource
import sqlite3
import stat
import uuid
from profile import directory, regular, write_json
from tool_catalog import native_specifications, tool_scope


def digest(path):
    with regular(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def binding(store, sid):
    sessions = regular(store.directory / 'Sessions.sqlite')
    with closing(sqlite3.connect(sessions.as_uri() + '?mode=ro', uri=True)) as db:
        row = db.execute('SELECT thread_id FROM sessions WHERE id=? AND project_id=?', (sid, store.owner_id)).fetchone()
    if not row:
        raise ValueError('The original native session is unavailable.')
    thread = row[0]
    if not thread:
        return None
    root = store.directory / sid / 'Codex'
    path = regular(root / 'state/state_5.sqlite')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        row = db.execute('SELECT rollout_path,model_provider FROM threads WHERE id=?', (thread,)).fetchone()
    if not row:
        raise ValueError('The original native thread metadata is unavailable.')
    virtual = Path(row[0])
    roots = {Path('/codex/sessions'): root / 'native',
             Path('/codex/archived_sessions'): root / 'archived',
             Path('/session/native'): root / 'native', Path('/session/archived'): root / 'archived'}
    target = next((base / virtual.relative_to(prefix) for prefix, base in roots.items()
                   if virtual.is_relative_to(prefix)), None)
    if target is None or '..' in virtual.parts:
        raise ValueError('The original native rollout path is outside this session.')
    return {'threadId': thread, 'root': root, 'path': regular(target), 'provider': row[1]}


def provider(store, sid):
    value = binding(store, sid)
    return value['provider'] if value else __import__('image_provider').PROVIDER


def offsets(root, thread):
    path = root / 'state/thread_history_1.sqlite'
    if not path.exists():
        return None
    with closing(sqlite3.connect(regular(path).as_uri() + '?mode=ro', uri=True)) as db:
        turns = db.execute('SELECT turn_id,rollout_byte_offset,rollout_end_byte_offset FROM thread_turns WHERE thread_id=? ORDER BY turn_id', (thread,)).fetchall()
        projection = db.execute('SELECT next_rollout_byte_offset FROM thread_history_projection_state WHERE thread_id=?', (thread,)).fetchone()
    return {'turns': turns, 'projection': projection}


def rebase(root, thread, saved, width, delta):
    if saved is None or not delta:
        return
    def shifted(value):
        if value is None or value == 0:
            return value
        if type(value) is not int or value < width:
            raise ValueError('A native history cursor falls inside the original metadata record.')
        return value + delta
    with closing(sqlite3.connect(regular(root / 'state/thread_history_1.sqlite'))) as db:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        for ident, start, end in saved['turns']:
            before = (start, end)
            after = tuple(shifted(v) for v in before)
            current = db.execute('SELECT rollout_byte_offset,rollout_end_byte_offset FROM thread_turns WHERE thread_id=? AND turn_id=?', (thread, ident)).fetchone()
            if current not in (before, after):
                raise ValueError('The original native history cursors changed during catalog refresh.')
            db.execute('UPDATE thread_turns SET rollout_byte_offset=?,rollout_end_byte_offset=? WHERE thread_id=? AND turn_id=?', (*after, thread, ident))
        if saved['projection'] is not None:
            before = tuple(saved['projection'])
            after = (shifted(before[0]),)
            current = db.execute('SELECT next_rollout_byte_offset FROM thread_history_projection_state WHERE thread_id=?', (thread,)).fetchone()
            if current not in (before, after):
                raise ValueError('The original native projection cursor changed during catalog refresh.')
            db.execute('UPDATE thread_history_projection_state SET next_rollout_byte_offset=? WHERE thread_id=?', (after[0], thread))
        db.commit()


def finish(value, folder, current):
    """Idempotently finish only the original metadata/cursor update."""
    path, root = current['path'], current['root']
    if value['threadId'] != current['threadId'] or value['rollout'] != str(path.relative_to(root)):
        raise ValueError('The original catalog journal belongs to another native thread.')
    actual = digest(path)
    if actual == value['beforeSha256']:
        temporary = regular(folder / 'replacement.jsonl')
        if digest(temporary) != value['afterSha256']:
            raise ValueError('The prepared native catalog bytes changed.')
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    elif actual != value['afterSha256']:
        raise ValueError('The original native history changed during catalog refresh.')
    rebase(root, current['threadId'], value['offsets'], value['beforeWidth'], value['delta'])
    if value['providerBefore'] != value['providerAfter']:
        with closing(sqlite3.connect(regular(root / 'state/state_5.sqlite'))) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT model_provider FROM threads WHERE id=?', (current['threadId'],)).fetchone()
            if not row or row[0] not in (value['providerBefore'], value['providerAfter']):
                raise ValueError('The original native provider changed during catalog refresh.')
            db.execute('UPDATE threads SET model_provider=? WHERE id=?', (value['providerAfter'], current['threadId']))
            db.commit()
    value['phase'] = 'complete'
    write_json(folder / 'intent.json', value)


def synchronize(store, sid, run_id, config):
    current = binding(store, sid)
    if current is None:
        return {'changed': False, 'newThread': True}
    # The caller already holds this workspace's exclusive run lease. Recheck
    # that only this admitted worker may own the native state before any write.
    with closing(sqlite3.connect(regular(store.directory / 'Sessions.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
        row = db.execute('SELECT session_id,busy,state FROM runs WHERE id=?', (run_id,)).fetchone()
    if not row or row[0] != sid or not row[1] or row[2] not in ('starting', 'running'):
        raise ValueError('Native catalog refresh requires the original active run.')
    root, path = current['root'], current['path']
    journals = directory(root / 'ToolCatalog' / current['threadId'])
    for folder in sorted(journals.iterdir()):
        directory(folder)
        intent = folder / 'intent.json'
        if intent.exists():
            value = json.loads(regular(intent).read_text())
            if value['phase'] != 'complete':
                finish(value, folder, current)
    current = binding(store, sid)
    with path.open('rb') as stream:
        header = stream.readline(8 * 1024**2 + 1)
    if not header.endswith(b'\n') or len(header) > 8 * 1024**2:
        raise ValueError('The original native metadata record is incomplete.')
    record = json.loads(header)
    if record.get('type') != 'session_meta' or record.get('payload', {}).get('id') != current['threadId']:
        raise ValueError('The original native metadata identity changed.')
    if record['payload'].get('model_provider') != current['provider']:
        raise ValueError('The original native provider metadata is inconsistent.')
    desired = [{'type': 'function', **item} for item in native_specifications(config)]
    desired_provider = config.get('nativeModelProvider', current['provider'])
    if record['payload'].get('dynamic_tools') == desired and current['provider'] == desired_provider:
        return {'changed': False, 'threadId': current['threadId']}
    original = path.stat()
    if not stat.S_ISREG(original.st_mode) or original.st_nlink != 1:
        raise ValueError('The original native history is not owned by this worker account.')
    record['payload']['dynamic_tools'] = desired
    if desired_provider != current['provider']:
        from image_provider import PROVIDER
        if current['provider'] != 'openai' or desired_provider != PROVIDER or config['engine'].get('api'):
            raise ValueError('Catalog refresh cannot change this native provider route.')
        record['payload']['model_provider'] = desired_provider
    encoded = json.dumps(record, ensure_ascii=False, separators=(',', ':')).encode()
    replacement = encoded + b' ' * max(0, len(header) - len(encoded) - 1) + b'\n'
    folder = directory(journals / str(uuid.uuid4()))
    before_hash, after_hash, tail_hash = hashlib.sha256(), hashlib.sha256(), hashlib.sha256()
    # Only this owned native-history copy is exempt from the worker's soft
    # source-file bound; every later terminal retains its separate hard quota.
    previous_limit = resource.getrlimit(resource.RLIMIT_FSIZE)
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (previous_limit[1], previous_limit[1]))
        with path.open('rb') as source, (folder / 'original.jsonl').open('xb') as backup, (folder / 'replacement.jsonl').open('xb') as target:
            if source.read(len(header)) != header:
                raise ValueError('The native metadata changed while preparing its catalog.')
            backup.write(header); before_hash.update(header)
            target.write(replacement); after_hash.update(replacement)
            while chunk := source.read(1024**2):
                backup.write(chunk); target.write(chunk)
                before_hash.update(chunk); after_hash.update(chunk); tail_hash.update(chunk)
            for stream in (backup, target):
                stream.flush(); os.fsync(stream.fileno()); os.fchmod(stream.fileno(), stat.S_IMODE(original.st_mode))
    finally:
        resource.setrlimit(resource.RLIMIT_FSIZE, previous_limit)
    latest = path.stat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_uid', 'st_gid', 'st_mode')
    if any(getattr(latest, key) != getattr(original, key) for key in fields) or digest(path) != before_hash.hexdigest():
        raise ValueError('The original native history changed before catalog activation.')
    value = {'phase': 'prepared', 'threadId': current['threadId'], 'runId': run_id,
             'rollout': str(path.relative_to(root)), 'beforeSha256': before_hash.hexdigest(),
             'afterSha256': after_hash.hexdigest(), 'historyTailSha256': tail_hash.hexdigest(),
             'providerBefore': current['provider'], 'providerAfter': desired_provider,
             'beforeWidth': len(header), 'delta': len(replacement) - len(header),
             'offsets': offsets(root, current['threadId'])}
    write_json(folder / 'intent.json', value)
    for parent in (folder, journals, journals.parent, root):
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finish(value, folder, current)
    return {'changed': True, 'threadId': current['threadId'], 'historyTailSha256': tail_hash.hexdigest()}
