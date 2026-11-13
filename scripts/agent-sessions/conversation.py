"""Studio-owned model context in the existing private session database.

Reads never create or migrate a conversation. Only explicit initialization and
appends write; original messages and checkpoints remain immutable.
"""
import json
from contextlib import nullcontext

from session_store import identity, now
from store import ProjectFault

CONTEXT_INDEXES = {
    'conversation_checkpoint': "conversation_records(session_id,through_seq DESC,seq DESC) WHERE kind='checkpoint'",
    'conversation_last_human': "conversation_records(session_id,seq DESC) WHERE kind='message' AND role='user' AND (json_extract(origin,'$.kind') IS NULL OR json_extract(origin,'$.kind') NOT IN ('goalContinuation','quotaContinuation'))",
    'conversation_last_assistant': "conversation_records(session_id,seq DESC) WHERE kind='message' AND role='assistant' AND json_type(origin,'$.providerResponseId') IS NOT NULL",
}
FORMAT = 1
MAX_RECORD = 16 * 1024 * 1024


def encoded(value):
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if len(raw.encode()) > MAX_RECORD:
            raise ValueError()
        return raw
    except (ValueError, TypeError, UnicodeError):
        raise ProjectFault('Conversation content is invalid or exceeds its storage limit.', 400) from None


def identifier(value):
    try:
        valid = (isinstance(value, str) and 1 <= len(value.encode()) <= 512
                 and not any(ord(c) < 33 or ord(c) == 127 for c in value))
    except UnicodeError:
        valid = False
    if not valid:
        raise ProjectFault('Invalid conversation record identity.', 400)
    return value


def parts(value):
    if not isinstance(value, list) or not value or len(value) > 8192:
        raise ProjectFault('Conversation content must contain ordered content parts.', 400)
    for part in value:
        if not isinstance(part, dict):
            raise ProjectFault('Invalid conversation content part.', 400)
        kind = part.get('type')
        if kind == 'text':
            valid = isinstance(part.get('text'), str)
        elif kind == 'tool_call':
            identifier(part.get('callId')); identifier(part.get('name'))
            valid = isinstance(part.get('arguments'), dict)
        elif kind == 'tool_result':
            identifier(part.get('callId'))
            valid = isinstance(part.get('result'), dict)
        elif kind in ('image', 'document'):
            valid = isinstance(part.get('reference'), str) and bool(part['reference'])
        elif kind == 'provider':
            # Opaque original content remains a string, never re-serialized as
            # purportedly portable reasoning by the common context store.
            valid = isinstance(part.get('value'), str) and isinstance(part.get('protocol'), str)
        else:
            valid = False
        if not valid:
            raise ProjectFault('Invalid or unsupported conversation content part.', 400)
    return encoded(value)


class Conversation:
    def __init__(self, store, session_id):
        self.store = store
        self.session_id = identity(session_id)
        self.store.row(self.session_id)

    def metadata(self):
        self.store.row(self.session_id)
        if not self.store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversation_sessions'").fetchone():
            return None
        row = self.store.db.execute('SELECT * FROM conversation_sessions WHERE session_id=?', (self.session_id,)).fetchone()
        if row is None:
            return None
        if row['format'] not in (FORMAT, 2):
            raise ProjectFault('This conversation format is unavailable. Its original history was preserved.', 409)
        return {'format': row['format'], 'source': json.loads(row['source']), 'createdAt': row['created_at']}

    def initialize(self, source, commit=True):
        """Called only by new common-session creation or an explicit import."""
        if not isinstance(source, dict):
            raise ProjectFault('The conversation source is missing.', 400)
        raw = encoded(source)
        with self.store.db if commit else nullcontext():
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS conversation_sessions(
                session_id TEXT PRIMARY KEY REFERENCES sessions(id), format INTEGER NOT NULL,
                source TEXT NOT NULL, created_at TEXT NOT NULL)''')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS conversation_records(
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES conversation_sessions(session_id),
                run_id TEXT NOT NULL REFERENCES runs(id), record_id TEXT NOT NULL,
                kind TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
                origin TEXT NOT NULL, through_seq INTEGER, created_at TEXT NOT NULL,
                UNIQUE(session_id, record_id))''')
            self.store.db.execute('CREATE INDEX IF NOT EXISTS conversation_cursor ON conversation_records(session_id,seq)')
            for name, target in CONTEXT_INDEXES.items():
                self.store.db.execute('CREATE INDEX IF NOT EXISTS ' + name + ' ON ' + target)
            current = self.metadata()
            if current is not None:
                if encoded(current['source']) != raw:
                    raise ProjectFault('The conversation already has another original source.', 409)
            else:
                self.store.db.execute('INSERT INTO conversation_sessions VALUES (?,?,?,?)',
                                      (self.session_id, FORMAT, raw, now()))
        return self.metadata()

    def append(self, run_id, record_id, role, content, origin, commit=True):
        if role not in ('user', 'assistant', 'tool'):
            raise ProjectFault('Invalid conversation role.', 400)
        return self._append(run_id, record_id, 'message', role, content, origin, commit=commit)

    def head(self):
        return self.store.db.execute('SELECT COALESCE(MAX(seq),0) FROM conversation_records WHERE session_id=?',
                                     (self.session_id,)).fetchone()[0]

    def checkpoint(self, run_id, record_id, through_seq, text, origin, *, expected_head=None):
        if type(through_seq) is not int or through_seq < 1 or not isinstance(text, str) or not text.strip():
            raise ProjectFault('A conversation checkpoint requires confirmed source content and a summary.', 400)
        return self._append(run_id, record_id, 'checkpoint', 'assistant', [{'type': 'text', 'text': text}], origin,
                            through_seq, expected_head=expected_head)

    def _append(self, run_id, record_id, kind, role, content, origin, through_seq=None, commit=True, *, expected_head=None):
        from run_store import event, get_run
        if self.metadata() is None:
            raise ProjectFault('This session has not been explicitly initialized for the Studio runtime.', 409)
        run_id = identity(run_id); record_id = identifier(record_id)
        run = get_run(self.store, run_id)
        if run['session_id'] != self.session_id:
            raise ProjectFault('This conversation record belongs to another session.', 409)
        if not isinstance(origin, dict):
            raise ProjectFault('Conversation origin must be retained.', 400)
        config = json.loads(run['config'])
        selection = {key: config[key] for key in ('providerId', 'model', 'effort', 'revision') if key in config}
        connection = config.get('apiProvider') or config.get('engine', {}).get('api')
        if connection:
            selection['connection'] = {key: connection[key] for key in ('id', 'protocol', 'revision', 'credentialRevision') if key in connection}
        if 'selection' in origin and origin['selection'] != selection:
            raise ProjectFault('The conversation selection differs from its accepted run.', 409)
        origin = {**origin, 'selection': selection}
        content_raw = parts(content); origin_raw = encoded(origin)
        expected = (run_id, kind, role, content_raw, origin_raw, through_seq)
        with self.store.db if commit else nullcontext():
            # Serialize the lookup and append using SQLite's existing writer
            # transaction, including concurrent retries of the same record.
            self.store.db.execute('UPDATE conversation_sessions SET format=format WHERE session_id=?', (self.session_id,))
            old = self.store.db.execute('SELECT * FROM conversation_records WHERE session_id=? AND record_id=?',
                                         (self.session_id, record_id)).fetchone()
            if old is not None:
                if tuple(old[k] for k in ('run_id', 'kind', 'role', 'content', 'origin', 'through_seq')) != expected:
                    raise ProjectFault('This conversation record identity has different original content.', 409)
                return self.present(old)
            if expected_head is not None and self.head()!=expected_head:
                raise ProjectFault('The conversation changed during context summarization. The prior checkpoint was kept.',409)
            if through_seq is not None:
                source = self.store.db.execute("SELECT 1 FROM conversation_records WHERE session_id=? AND seq=? AND kind='message'",
                                               (self.session_id, through_seq)).fetchone()
                if source is None:
                    raise ProjectFault('The checkpoint source is not an original message in this conversation.', 409)
            if kind == 'checkpoint' and origin.get('retainedContextRecords'):
                # Older readers must refuse this view instead of silently
                # omitting the exact observations retained below through_seq.
                self.store.db.execute('UPDATE conversation_sessions SET format=2 WHERE session_id=?', (self.session_id,))
            cursor = self.store.db.execute('''INSERT INTO conversation_records
                (session_id,run_id,record_id,kind,role,content,origin,through_seq,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (self.session_id, run_id, record_id, kind, role, content_raw, origin_raw, through_seq, now())).lastrowid
            # Public events expose a cursor, never private provider payloads.
            event(self.store, self.session_id, run_id, 'conversation',
                  {'recordId': record_id, 'sequence': cursor, 'kind': kind}, commit=False)
            row = self.store.db.execute('SELECT * FROM conversation_records WHERE seq=?', (cursor,)).fetchone()
        return self.present(row)

    @staticmethod
    def present(row):
        return {'sequence': row['seq'], 'id': row['record_id'], 'runId': row['run_id'],
                'kind': row['kind'], 'role': row['role'], 'content': json.loads(row['content']),
                'origin': json.loads(row['origin']), 'throughSequence': row['through_seq'], 'createdAt': row['created_at']}

    def records(self, after=0, limit=200, include_checkpoints=False):
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 8192:
            raise ProjectFault('Invalid conversation cursor.', 400)
        if self.metadata() is None:
            return []
        rows = self.store.db.execute('''SELECT * FROM conversation_records
            WHERE session_id=? AND seq>? AND (? OR kind='message') ORDER BY seq LIMIT ?''',
            (self.session_id, after, bool(include_checkpoints), limit))
        return [self.present(row) for row in rows]

    def latest_checkpoint(self):
        if self.metadata() is None:
            return None
        row = self.store.db.execute("SELECT * FROM conversation_records WHERE session_id=? AND kind='checkpoint' ORDER BY through_seq DESC,seq DESC LIMIT 1",
                                    (self.session_id,)).fetchone()
        return self.present(row) if row is not None else None
