from skill_lifecycle import guarded
"""Private user-message intents. Creating an intent never invokes a model."""
import hashlib
import json

from session_store import encode, identity, now
from store import ProjectFault

OPEN = ('pending', 'queued', 'dispatching', 'unknown')
MAX_PENDING = 32
MAX_BYTES = 2 * 1024 * 1024


def exists(store):
    return bool(store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='session_messages'").fetchone())


def pending_queue(store, sid, authorized=False):
    if not exists(store): return False
    query = "SELECT 1 FROM session_messages m JOIN session_inboxes q ON q.session_id=m.session_id WHERE m.session_id=? AND m.mode='queue' AND m.state IN ('queued','dispatching')"
    if authorized: query += ' AND q.held=0'
    return bool(store.db.execute(query, (sid,)).fetchone())


def observe_run(store, sid, run_id, state, turn_id=None):
    if not exists(store): return
    if state == 'running' and turn_id:
        changed = store.db.execute("UPDATE session_messages SET state='accepted',updated_at=? WHERE run_id=? AND state='dispatching'", (now(), run_id)).rowcount
        if changed: store.db.execute('UPDATE session_inboxes SET revision=revision+1 WHERE session_id=?',(sid,))
    if state in ('failed', 'interrupted', 'unknown'):
        store.db.execute('UPDATE session_inboxes SET held=1,reason=?,revision=revision+1 WHERE session_id=?',
                         ('The preceding run ended without a confirmed natural completion. Continue explicitly.', sid))
        store.db.execute("UPDATE session_messages SET state=?,error=?,updated_at=? WHERE run_id=? AND state='dispatching'",
                         ('unknown' if state == 'unknown' else 'rejected', 'The original run did not confirm message acceptance.', now(), run_id))


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

    def snapshot(self, sid, before=None, view='all'):
        self.store.row(sid)
        if view not in ('all','pending'): raise ProjectFault('Invalid message view.',400)
        if before is not None and (type(before) is not int or not 1 <= before <= 9007199254740991):
            raise ProjectFault('Invalid message cursor.', 400)
        selection = " AND state IN ('pending','queued','dispatching','unknown')" if view=='pending' else ''
        rows = self.store.db.execute('SELECT * FROM session_messages WHERE session_id=? AND seq<?'+selection+' ORDER BY seq DESC LIMIT 51',
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

    @guarded
    def accept(self, sid, data, provider_dir, capabilities=None, image_capability=None):
        if (not isinstance(data, dict) or not {'requestId', 'revision', 'mode', 'text'} <= set(data)
                or set(data) - {'requestId', 'revision', 'mode', 'text', 'attachments', 'target'}
                or data['mode'] not in ('queue', 'steer') or type(data['revision']) is not int or data['revision'] < 1):
            raise ProjectFault('Invalid message fields.', 400)
        key = identity(data['requestId'])
        text = data['text']
        if (not isinstance(text, str) or any(0xd800 <= ord(c) <= 0xdfff for c in text)
                or '\x00' in text or len(text.encode()) > 65536 or not text.strip() and not data.get('attachments')):
            raise ProjectFault('Enter a message of at most64 KiB or select Ready attachments.', 400)
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
                if json.loads(run['worker'] or '{}').get('messageProtocol') != 1:
                    raise ProjectFault('The original worker does not support direct messages. Queue this input or wait for its next run.', 503)
                if not json.loads(run['worker']).get('messageTurnActive'):
                    raise ProjectFault('The expected native turn has ended. Your input was preserved.', 409)
                if data.get('attachments'):
                    raise ProjectFault('Direct messages currently support text only. Queue the full input to keep its attachments.', 409)
                if self.store.db.execute("SELECT 1 FROM session_messages WHERE run_id=? AND mode='steer' AND state IN ('pending','dispatching')", (run['id'],)).fetchone():
                    raise ProjectFault('Another direct message is being confirmed. Your input was preserved.', 429)
            count, size = self.store.db.execute("SELECT COUNT(*),COALESCE(SUM(length(CAST(input AS BLOB))+length(CAST(frozen AS BLOB))),0) FROM session_messages WHERE session_id=? AND state IN ('pending','queued','dispatching','unknown')", (sid,)).fetchone()
            raw = encode(data)
            if count >= MAX_PENDING or size + len(raw.encode()) > MAX_BYTES:
                raise ProjectFault('The session message queue is full. Your input was preserved.', 429)
            total = self.store.db.execute('SELECT COALESCE(SUM(length(CAST(input AS BLOB))+length(CAST(frozen AS BLOB))),0) FROM session_messages WHERE session_id=?', (sid,)).fetchone()[0]
            from run_store import capture_input
            run_input = {k: v for k, v in data.items() if k not in ('mode', 'target')}
            run_input.update(capabilities or {})
            if data['mode'] == 'steer': config, attachments = json.loads(run['config']), []
            else: config, attachments, _ = capture_input(self.store, sid, run_input, provider_dir, image_capability)
            frozen = {'config': config, 'runInput': run_input, 'attachments': attachments}
            frozen_raw = encode(frozen)
            charge = len(raw.encode()) + len(frozen_raw.encode())
            if size + charge > MAX_BYTES: raise ProjectFault('The frozen message queue reached its storage limit. Your input was preserved.', 429)
            if total + charge > 96 * 1024 * 1024: raise ProjectFault('The session message journal reached its storage limit.', 429)
            stamp = now()
            self.store.db.execute('''INSERT INTO session_messages(request_id,session_id,mode,state,input,input_hash,frozen,run_id,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)''', (key, sid, data['mode'], 'pending' if data['mode']=='steer' else 'queued', raw, hashed, frozen_raw, target['runId'] if target else None, stamp, stamp))
            if data['mode'] == 'queue':
                self.store.db.execute('INSERT INTO session_inboxes VALUES (?,0,NULL,1) ON CONFLICT(session_id) DO UPDATE SET revision=revision+1', (sid,))
            value = self.receipt(sid, key)
            from run_store import event
            event(self.store, sid, None, 'message', value, False)
            self.store.db.commit()
            return value, True
        finally:
            if self.store.db.in_transaction: self.store.db.rollback()

    def hold(self, sid, reason):
        self.store.row(sid)
        with self.store.db:
            self.store.db.execute('INSERT INTO session_inboxes VALUES (?,1,?,1) ON CONFLICT(session_id) DO UPDATE SET held=1,reason=excluded.reason,revision=revision+1', (sid, reason))

    def finish(self, sid, request_id, state, error=None):
        with self.store.db:
            row = self.row(sid, request_id)
            if row['state'] == 'accepted': return self.present(row)
            self.store.db.execute('UPDATE session_messages SET state=?,error=?,updated_at=? WHERE request_id=?', (state, error, now(), request_id))
            self.store.db.execute('INSERT INTO session_inboxes VALUES (?,0,NULL,1) ON CONFLICT(session_id) DO UPDATE SET revision=revision+1', (sid,))
            value = self.receipt(sid, request_id)
            from run_store import event, item
            event(self.store, sid, row['run_id'], 'message', value, False)
            if state == 'accepted' and row['mode'] == 'steer':
                item(self.store, sid, row['run_id'], {'id':'user-'+request_id, 'runId':row['run_id'], 'turnId':value['target']['turnId'], 'type':'user', 'text':value['text'], 'status':'completed', 'messageRequestId':request_id}, False)
            return value

    def control(self, sid, data):
        self.store.row(sid)
        if (set(data) - {'requestId', 'revision', 'action', 'messageId'} or not {'requestId','revision','action'} <= set(data)
                or data['action'] not in ('resume', 'cancel') or type(data['revision']) is not int):
            raise ProjectFault('Invalid queue control.', 400)
        key = identity(data['requestId']); raw = encode(data)
        with self.store.db:
            self.store.db.execute('BEGIN IMMEDIATE')
            previous = self.store.db.execute('SELECT * FROM requests WHERE request_id=?', (key,)).fetchone()
            hashed = hashlib.sha256(encode({'sessionId': sid, **data}).encode()).hexdigest()
            if previous:
                if previous['kind'] != 'message_control' or previous['payload_hash'] != hashed or previous['session_id'] != sid:
                    raise ProjectFault('This request ID belongs to another queue action.', 409)
                return json.loads(previous['response'])
            queue = self.store.db.execute('SELECT * FROM session_inboxes WHERE session_id=?', (sid,)).fetchone()
            if not queue or queue['revision'] != data['revision']: raise ProjectFault('The queue changed. Reload before continuing.', 409)
            if data['action'] == 'cancel':
                row = self.row(sid, data.get('messageId'))
                if row['mode'] != 'queue' or row['state'] != 'queued': raise ProjectFault('Only an unsent queued message can be removed.', 409)
                self.store.db.execute("UPDATE session_messages SET state='cancelled',updated_at=? WHERE request_id=?", (now(), row['request_id']))
                self.store.db.execute('UPDATE session_inboxes SET revision=revision+1 WHERE session_id=?', (sid,))
            else:
                if 'messageId' in data: raise ProjectFault('Resume does not select another message.', 400)
                self.store.db.execute('UPDATE session_inboxes SET held=0,reason=NULL,revision=revision+1 WHERE session_id=?', (sid,))
            result = self.snapshot(sid)
            self.store.db.execute('INSERT INTO requests VALUES (?,?,?,?,?)', (key, 'message_control', hashed, sid, encode(result)))
            return result

    def recover(self):
        for row in self.store.db.execute("SELECT session_id,request_id FROM session_messages WHERE mode='steer' AND state IN ('pending','dispatching')").fetchall():
            self.finish(row['session_id'], row['request_id'], 'unknown', 'The coordinator restarted before the direct receipt was confirmed. It was not sent again.')
        # A coordinator restart revokes unattended dispatch, even for live workers.
        for row in self.store.db.execute("SELECT DISTINCT session_id FROM session_messages WHERE mode='queue' AND state IN ('queued','dispatching','unknown')").fetchall():
            self.hold(row['session_id'], 'The coordinator restarted. Continue the saved queue explicitly.')

    def first(self, sid):
        if not pending_queue(self.store, sid, authorized=True): return None
        return self.store.db.execute("SELECT * FROM session_messages WHERE session_id=? AND mode='queue' AND state='queued' ORDER BY seq LIMIT 1", (sid,)).fetchone()
