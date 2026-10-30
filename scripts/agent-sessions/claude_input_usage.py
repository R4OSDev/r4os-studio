"""Message-scoped main-loop input/cache receipts; output remains unknown.

Only a completed native response qualifies its assistant usage snapshot. Shared
provider message IDs are counted once, also after explicit same-session resume.
The result's cumulative/model counters and assistant output placeholders never
enter this projection. Public model/account admission is unchanged.
"""
import json

from claude_runtime import profile
from session_store import encode, identity, now
from stats_store import Source, MAX_NUMBER
from store import ProjectFault

FIELDS = ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')
LIMIT = 1024


def counter(value):
    if value is not None and (type(value) is not int or not 0 <= value <= MAX_NUMBER):
        raise ProjectFault('Native input usage contains an invalid counter. Its totals were not guessed.', 409)
    return value


def record(worker, message, usage):
    """Called only for the original stream's completed main-loop response."""
    frozen = worker.config['engine'].get('claude', {}); expected = profile()
    if (worker.config['engine'].get('kind') != 'claude-code'
            or frozen.get('runtimeProfileId') != expected['id']
            or frozen.get('sha256') != expected['native']['files']['claude']['sha256']
            or frozen.get('sdkArchiveSha256') != expected['sdk']['archiveSha256']
            or frozen.get('studioSessionId') != worker.session_id
            or frozen.get('providerId') != worker.config['providerId']):
        raise ProjectFault('Native input usage is outside its original runtime/session binding.', 409)
    ident = (message.get('message') or {}).get('id')
    if (message.get('type') != 'assistant' or message.get('session_id') != frozen.get('nativeSessionId')
            or message.get('parent_tool_use_id') is not None or message.get('error') is not None
            or not isinstance(ident, str) or not 1 <= len(ident.encode()) <= 256
            or any(ord(c) <= 32 or ord(c) == 127 for c in ident)):
        raise ProjectFault('Native input usage has no confirmed main-loop message identity.', 409)
    identity(message['uuid'])
    if not isinstance(usage, dict):
        raise ProjectFault('Native input usage was not reported.', 409)
    counts = {key: counter(usage.get(key)) for key in FIELDS}
    values = {}
    if all(value is not None for value in counts.values()):
        values['input'] = counter(sum(counts.values()))
    if counts['cache_creation_input_tokens'] is not None: values['cacheWrite'] = counts['cache_creation_input_tokens']
    if counts['cache_read_input_tokens'] is not None: values['cachedInput'] = counts['cache_read_input_tokens']
    source_identity = {'source': 'claude-main-loop-input-v1',
        'owner': {'type': worker.store.owner_type, 'id': worker.store.owner_id}, 'session': worker.session_id,
        'nativeSessionId': frozen['nativeSessionId'], 'providerMessageId': ident,
        'runtime': frozen['sha256'], 'sdk': frozen['sdkArchiveSha256']}
    # The common durable numeric outbox is written first. A crash before the
    # optional private audit link cannot lose or double the lifetime receipt.
    receipt = Source(worker.store).put(worker.session_id, 'tokens', source_identity, values)
    payload = {'schema': 1, 'source': source_identity, 'counts': counts, 'values': values,
        'semantics': 'completed main-loop response input/cache; output and total unqualified',
        'numericReceiptKey': receipt['key']}
    db = worker.store.db
    with db:
        db.execute('''CREATE TABLE IF NOT EXISTS claude_input_usage(
            message_key TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),
            run_id TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL)''')
        old = db.execute('SELECT payload FROM claude_input_usage WHERE message_key=?', (receipt['key'],)).fetchone()
        if old:
            if json.loads(old[0]) != payload:
                raise ProjectFault('Conflicting native message usage was preserved. Its original totals were not changed.', 409)
        else:
            db.execute('INSERT INTO claude_input_usage VALUES (?,?,?,?,?)',
                (receipt['key'], worker.session_id, worker.run_id, encode(payload), now()))
    return receipt


class InputUsage:
    def __init__(self, worker):
        self.w = worker; self.pending = {}; self.completed = set(); self.active = None; self.warned = False

    def gap(self):
        try:
            Source(self.w.store).put(self.w.session_id, 'gap',
                {'source': 'claude-input-coverage-v1', 'run': self.w.run_id}, {'missing': 1})
        except Exception: pass  # Never repair a source or replay model work for statistics.
        if not self.warned:
            self.warned = True
            from run_store import event
            event(self.w.store, self.w.session_id, self.w.run_id, 'notice',
                {'text': 'Some Claude input usage is unconfirmed. Output and total token counts remain unknown.'})

    def notify(self, frame):
        if frame.get('parent_tool_use_id') is not None: return
        try:
            if frame['type'] == 'stream_event':
                part = frame.get('event') or {}
                if part.get('type') == 'message_start':
                    self.active = (part.get('message') or {}).get('id')
                elif part.get('type') == 'message_stop' and self.active:
                    if len(self.completed) >= LIMIT: raise ValueError('Input usage response limit')
                    self.completed.add(self.active)
                    self.publish(self.active)
                    self.active = None
            elif frame['type'] == 'assistant' and frame.get('error') is None:
                message = frame.get('message') or {}; ident = message.get('id')
                if not isinstance(ident, str) or not ident: raise ValueError('Missing usage response identity')
                usage = message.get('usage')
                if not isinstance(usage, dict): raise ValueError('Missing input usage')
                counts = {key: counter(usage.get(key)) for key in FIELDS}
                old = self.pending.get(ident)
                if old and old[1] != counts: raise ValueError('Conflicting response input usage')
                if len(self.pending) >= LIMIT and ident not in self.pending: raise ValueError('Input usage response limit')
                # Retain identity and numbers only, never duplicate response
                # text, tool arguments or image content in this accounting map.
                safe = {key: frame.get(key) for key in ('type', 'session_id', 'parent_tool_use_id', 'uuid')}
                safe['message'] = {'id': ident}
                self.pending[ident] = (safe, counts)
                if ident in self.completed: self.publish(ident)
        except (KeyError, TypeError, ValueError, ProjectFault):
            self.gap()

    def publish(self, ident):
        if ident in self.pending:
            frame, counts = self.pending[ident]
            record(self.w, frame, counts)

    def finish(self):
        if any(ident not in self.completed for ident in self.pending): self.gap()
        # Source receipts are independently retained by the existing deletion
        # outbox even if the global statistics file is temporarily unavailable.
        try: Source(self.w.store).flush()
        except Exception: self.gap()
