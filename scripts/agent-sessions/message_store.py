"""Private user-message intents. Creating an intent never invokes a model."""
import hashlib
import json

from session_store import encode, identity, now
from store import ProjectFault

OPEN = ('pending', 'queued', 'dispatching', 'unknown')
MAX_PENDING = 32
MAX_BYTES = 2 * 1024 * 1024


class Messages:
    def __init__(self, store):
        self.store = store
        with store.db:
            store.db.execute('''CREATE TABLE IF NOT EXISTS session_messages(
                seq INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL UNIQUE,
                session_id TEXT NOT NULL REFERENCES sessions(id), mode TEXT NOT NULL,
                state TEXT NOT NULL, input TEXT NOT NULL, input_hash TEXT NOT NULL,
                frozen TEXT NOT NULL, run_id TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
            store.db.execute('CREATE INDEX IF NOT EXISTS message_session_order ON session_messages(session_id,seq)')
            store.db.execute('''CREATE TABLE IF NOT EXISTS session_inboxes(
                session_id TEXT PRIMARY KEY REFERENCES sessions(id), held INTEGER NOT NULL,
                reason TEXT, revision INTEGER NOT NULL DEFAULT 1)''')

    def row(self, sid, request_id):
        self.store.row(sid)
        row = self.store.db.execute('SELECT * FROM session_messages WHERE session_id=? AND request_id=?',
                                    (sid, identity(request_id))).fetchone()
        if row is None: raise ProjectFault('Message receipt not found.', 404)
        return row

    def present(self, row):
        data = json.loads(row['input']); frozen = json.loads(row['frozen'])
        return {'requestId': row['request_id'], 'sessionId': row['session_id'], 'sequence': row['seq'],
                'mode': row['mode'], 'state': row['state'], 'text': data['text'],
                'attachments': frozen.get('attachments', []), 'target': data.get('target'),
                'runId': row['run_id'], 'error': row['error'], 'createdAt': row['created_at'], 'updatedAt': row['updated_at']}

    def receipt(self, sid, request_id): return self.present(self.row(sid, request_id))

    def snapshot(self, sid, before=None):
        self.store.row(sid)
        if before is not None and (type(before) is not int or not 1 <= before <= 9007199254740991):
            raise ProjectFault('Invalid message cursor.', 400)
        rows = self.store.db.execute('SELECT * FROM session_messages WHERE session_id=? AND seq<? ORDER BY seq DESC LIMIT 51',
                                     (sid, before or 9007199254740991)).fetchall()
        selected = []; size = 0
        for row in rows[:50]:
            size += len(row['input'].encode()) + len(row['frozen'].encode()) + 1024
            if selected and size > 524288: break
            selected.append(row)
        queue = self.store.db.execute('SELECT * FROM session_inboxes WHERE session_id=?', (sid,)).fetchone()
        return {'messages': [self.present(r) for r in reversed(selected)],
                'nextBefore': selected[-1]['seq'] if len(rows) > len(selected) else None,
                'held': bool(queue['held']) if queue else False, 'reason': queue['reason'] if queue else None,
                'revision': queue['revision'] if queue else 0}

    def accept(self, sid, data):
        if (not isinstance(data, dict) or not {'requestId', 'revision', 'mode', 'text'} <= set(data)
                or set(data) - {'requestId', 'revision', 'mode', 'text', 'attachments', 'target'}
                or data['mode'] not in ('queue', 'steer') or type(data['revision']) is not int or data['revision'] < 1):
            raise ProjectFault('Invalid message fields.', 400)
        key = identity(data['requestId'])
        text = data['text']
        if (not isinstance(text, str) or any(0xd800 <= ord(c) <= 0xdfff for c in text)
                or '\x00' in text or len(text.encode()) > 65536 or not text.strip() and not data.get('attachments')):
            raise ProjectFault('Enter a message of at most64 KiB or select Ready attachments.', 400)
        if data.get('attachments'):
            # The next dispatch release qualifies attachment lifetime/frozen mounts.
            raise ProjectFault('This coordinator cannot yet queue attachments. Your input was preserved.', 503)
        target = data.get('target')
        if data['mode'] == 'steer':
            if (not isinstance(target, dict) or set(target) != {'runId', 'threadId', 'turnId'}
                    or any(not isinstance(v, str) or not v or len(v.encode()) > 256 or '\x00' in v for v in target.values())):
                raise ProjectFault('A direct message needs its original run, thread and turn.', 400)
            identity(target['runId'])
        elif target is not None: raise ProjectFault('Queued messages cannot specify a live target.', 400)
        hashed = hashlib.sha256(encode({'sessionId': sid, **data}).encode()).hexdigest()
        self.store.db.execute('BEGIN IMMEDIATE')
        try:
            self.store.row(sid)
            previous = self.store.db.execute('SELECT * FROM session_messages WHERE request_id=?', (key,)).fetchone()
            if previous:
                if previous['session_id'] != sid or previous['input_hash'] != hashed:
                    raise ProjectFault('This request ID belongs to a different message.', 409)
                return self.present(previous), False
            session = self.store.get(sid)
            if session['revision'] != data['revision']: raise ProjectFault('Session settings changed. Reload before sending.', 409)
            if data['mode'] == 'steer':
                run = self.store.db.execute('SELECT * FROM runs WHERE id=? AND session_id=? AND busy=1', (target['runId'], sid)).fetchone()
                if not run or run['state'] != 'running' or run['turn_id'] != target['turnId'] or self.store.row(sid)['thread_id'] != target['threadId']:
                    raise ProjectFault('The expected native turn is no longer active. Your message was preserved.', 409)
                raise ProjectFault('The original worker does not support direct messages yet. Your message was preserved.', 503)
            count, size = self.store.db.execute("SELECT COUNT(*),COALESCE(SUM(length(CAST(input AS BLOB))),0) FROM session_messages WHERE session_id=? AND state IN ('pending','queued','dispatching','unknown')", (sid,)).fetchone()
            raw = encode(data)
            if count >= MAX_PENDING or size + len(raw.encode()) > MAX_BYTES:
                raise ProjectFault('The session message queue is full. Your input was preserved.', 429)
            total = self.store.db.execute('SELECT COALESCE(SUM(length(CAST(input AS BLOB))),0) FROM session_messages WHERE session_id=?', (sid,)).fetchone()[0]
            if total + len(raw.encode()) > 96 * 1024 * 1024: raise ProjectFault('The session message journal reached its storage limit.', 429)
            stamp = now()
            self.store.db.execute('''INSERT INTO session_messages(request_id,session_id,mode,state,input,input_hash,frozen,created_at,updated_at)
                VALUES (?,?,?,'queued',?,?,?,?,?)''', (key, sid, data['mode'], raw, hashed, encode({'sessionRevision': session['revision']}), stamp, stamp))
            self.store.db.execute("INSERT INTO session_inboxes VALUES (?,1,'Queue dispatch is not available in this release.',1) ON CONFLICT(session_id) DO UPDATE SET revision=revision+1", (sid,))
            value = self.receipt(sid, key)
            from run_store import event
            event(self.store, sid, None, 'message', value, False)
            self.store.db.commit()
            return value, True
        finally:
            if self.store.db.in_transaction: self.store.db.rollback()
