"""Short, persistent addresses for complete original result references."""
import base64
from contextlib import nullcontext
import hashlib
import json
import re

from session_store import encode
from store import ProjectFault


def enabled(config):
    return config.get('toolCatalog', {}).get('resultIds') == 1


def identifier(ref):
    identity = [ref[key] for key in ('owner','sessionId','runId','recordId','partIndex')]
    digest = hashlib.sha256(encode(identity).encode()).digest()
    return base64.b32encode(digest[:10]).decode('ascii').lower()


def address(worker, ref):
    if not enabled(worker.config):
        return {'reference':ref}
    result_id = identifier(ref)
    db = worker.store.db
    value = encode(ref)
    with nullcontext() if db.in_transaction else db:
        db.execute('''CREATE TABLE IF NOT EXISTS context_result_ids(
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
            sequence INTEGER NOT NULL REFERENCES conversation_records(seq) ON DELETE CASCADE,
            reference TEXT NOT NULL)''')
        db.execute('CREATE INDEX IF NOT EXISTS context_result_id_records ON context_result_ids(sequence)')
        old = db.execute('SELECT session_id,reference FROM context_result_ids WHERE id=?',(result_id,)).fetchone()
        if old is None:
            db.execute('INSERT INTO context_result_ids VALUES (?,?,?,?) ON CONFLICT(id) DO NOTHING',
                       (result_id,worker.session_id,ref['sequence'],value))
            old = db.execute('SELECT session_id,reference FROM context_result_ids WHERE id=?',(result_id,)).fetchone()
        if tuple(old) != (worker.session_id,value):
            raise ProjectFault('The saved original result reference changed.',409)
    return {'resultId':result_id}


def resolve(worker, args):
    if 'resultId' not in args:
        return args.get('reference')
    result_id = args['resultId']
    if not isinstance(result_id,str) or re.fullmatch('[a-z2-7]{16}',result_id) is None:
        raise ProjectFault('Use the resultId from the saved result preview or checkpoint index.',400)
    db = worker.store.db
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='context_result_ids'").fetchone():
        row = db.execute('SELECT reference FROM context_result_ids WHERE id=? AND session_id=?',
                         (result_id,worker.session_id)).fetchone()
        if row:
            try:
                ref = json.loads(row[0])
                if identifier(ref) == result_id:
                    return ref
            except (ValueError,KeyError,TypeError):
                pass
            raise ProjectFault('The saved original result reference changed.',409)
    raise ProjectFault('The original result ID is unavailable in this session.',404)
