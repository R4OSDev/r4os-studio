"""Effect receipts: duplicates return the original result, never another input."""
import json
from contracts import DevelopmentFault, UnconfirmedGuestEffect, encode, hash_value, identity
from jobs import now


def setup(store):
    with store.db: store.db.execute('CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY, job_id TEXT NOT NULL, fingerprint TEXT NOT NULL, state TEXT NOT NULL, result TEXT)')


def admit(store, job_id, value):
    setup(store); request_id = identity(value.get('requestId')); fingerprint = hash_value(value)
    store.db.execute('BEGIN IMMEDIATE')
    try:
        previous = store.db.execute('SELECT * FROM actions WHERE id=?', (request_id,)).fetchone()
        if previous:
            if previous['job_id'] != job_id or previous['fingerprint'] != fingerprint: raise DevelopmentFault('This action ID belongs to different input.')
            if previous['state'] != 'completed': raise DevelopmentFault('The previous action result is unconfirmed. It was not replayed.')
            store.db.commit(); return json.loads(previous['result'])
        store.db.execute('INSERT INTO actions VALUES(?,?,?, ?,NULL)', (request_id, job_id, fingerprint, 'intent'))
        store.db.commit(); return None
    except BaseException: store.db.rollback(); raise


def finish(store, request_id, result):
    with store.db: store.db.execute('UPDATE actions SET state=\'completed\',result=? WHERE id=?', (encode(result), identity(request_id)))
    return result


def previous(store, job_id, value):
    setup(store); request_id = identity(value.get('requestId')); fingerprint = hash_value(value)
    row = store.db.execute('SELECT * FROM actions WHERE id=?', (request_id,)).fetchone()
    if row is None: return None
    if row['job_id'] != job_id or row['fingerprint'] != fingerprint: raise DevelopmentFault('This action ID belongs to different input.')
    if row['state'] != 'completed':
        if value.get('operation') == 'complete_check': raise UnconfirmedGuestEffect('The original check completion is unconfirmed. No close was replayed.')
        raise DevelopmentFault('The previous action is unconfirmed. No effect was replayed.')
    return json.loads(row['result'])
