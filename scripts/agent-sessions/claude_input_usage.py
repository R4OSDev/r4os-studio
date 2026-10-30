"""Completed main-loop input/cache and final stream output receipts.

Only a completed native response qualifies its assistant usage snapshot. Shared
provider message IDs are counted once, also after explicit same-session resume.
The result's cumulative/model counters and assistant output placeholders never
enter this projection. Output needs a bound message_delta and message_stop.
Public model/account admission is unchanged.
"""
import json

from claude_runtime import profile
from session_store import encode, identity, now
from stats_store import Source, MAX_NUMBER
from store import ProjectFault

FIELDS = ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')
LIMIT = 1024
TERMINAL_REASONS={'end_turn','tool_use','max_tokens','stop_sequence','pause_turn','refusal','model_context_window_exceeded'}


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


def record_output(worker, input_receipt, output):
    """Add final response output without rewriting or counting input twice."""
    output=counter(output)
    if output is None:return None
    db=worker.store.db
    original=db.execute('SELECT payload FROM claude_input_usage WHERE message_key=? AND session_id=?',
        (input_receipt['key'],worker.session_id)).fetchone()
    if not original or json.loads(original[0])['values']!=input_receipt['values']:
        raise ProjectFault('Final native output has no original input receipt.',409)
    values={'output':output}
    if input_receipt['values'].get('input') is not None:values['total']=counter(input_receipt['values']['input']+output)
    source={'source':'claude-main-loop-output-v1','inputReceiptKey':input_receipt['key']}
    receipt=Source(worker.store).put(worker.session_id,'tokens',source,values)
    payload={'schema':1,'source':source,'outputTokens':output,'values':values,
        'semantics':'completed main-loop message_delta output; no assistant placeholders or cumulative session totals',
        'numericReceiptKey':receipt['key']}
    with db:
        db.execute('''CREATE TABLE IF NOT EXISTS claude_output_usage(
            message_key TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),
            run_id TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL)''')
        old=db.execute('SELECT payload FROM claude_output_usage WHERE message_key=?',(receipt['key'],)).fetchone()
        if old:
            if json.loads(old[0])!=payload:raise ProjectFault('Conflicting final native output was preserved. Its original totals were not changed.',409)
        else:db.execute('INSERT INTO claude_output_usage VALUES (?,?,?,?,?)',
            (receipt['key'],worker.session_id,worker.run_id,encode(payload),now()))
    return receipt


class InputUsage:
    def __init__(self, worker):
        self.w = worker; self.pending = {}; self.completed = set(); self.active = None; self.warned = False
        self.outputs={};self.invalid_outputs=set();self.output_disabled=False

    def output(self,ident):
        value=self.outputs.get(ident)
        return value[1] if value and value[2] and ident not in self.invalid_outputs and not self.output_disabled else None

    def gap(self):
        try:
            Source(self.w.store).put(self.w.session_id, 'gap',
                {'source': 'claude-input-coverage-v1', 'run': self.w.run_id}, {'missing': 1})
        except Exception: pass  # Never repair a source or replay model work for statistics.
        if not self.warned:
            self.warned = True
            from run_store import event
            event(self.w.store, self.w.session_id, self.w.run_id, 'notice',
                {'text': 'Some Claude token usage is unconfirmed. Statistics include only confirmed counters.'})

    def notify(self, frame):
        if frame.get('parent_tool_use_id') is not None: return
        try:
            if frame['type'] == 'stream_event':
                part = frame.get('event') or {}
                if part.get('type') == 'message_start':
                    self.active=None
                    ident=(part.get('message') or {}).get('id')
                    if not isinstance(ident,str) or not 1<=len(ident.encode())<=256 or any(ord(c)<=32 or ord(c)==127 for c in ident):
                        raise ValueError('Invalid native response identity')
                    self.active=ident
                elif part.get('type')=='message_delta' and self.active and not self.output_disabled:
                    ident=self.active;native=self.w.config['engine']['claude']['nativeSessionId']
                    if frame.get('session_id')!=native:raise ValueError('Foreign native output stream')
                    output=counter((part.get('usage') or {}).get('output_tokens'))
                    if len(self.outputs)>=LIMIT and ident not in self.outputs:
                        self.output_disabled=True;raise ValueError('Output usage response limit')
                    previous=self.outputs.get(ident,(None,None))[0]
                    if ident in self.completed or output is not None and previous is not None and output<previous:
                        raise ValueError('Conflicting final output counter')
                    # Retain the high-water mark separately from the latest
                    # observation: a missing final counter is not an earlier
                    # positive count, and a later smaller count is a conflict.
                    terminal=(part.get('delta') or {}).get('stop_reason') in TERMINAL_REASONS
                    self.outputs[ident]=(output if output is not None else previous,output,terminal)
                elif part.get('type') == 'message_stop' and self.active:
                    if len(self.completed) >= LIMIT: raise ValueError('Input usage response limit')
                    if self.active in self.outputs and frame.get('session_id')!=self.w.config['engine']['claude']['nativeSessionId']:
                        self.invalid_outputs.add(self.active);raise ValueError('Foreign native output closure')
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
            if frame.get('type')=='stream_event' and (frame.get('event') or {}).get('type')=='message_delta' and self.active and not self.output_disabled:
                if len(self.invalid_outputs)>=LIMIT:self.output_disabled=True
                else:self.invalid_outputs.add(self.active)
            self.gap()

    def publish(self, ident):
        if ident in self.pending:
            frame, counts = self.pending[ident]
            original=record(self.w, frame, counts)
            output=self.output(ident)
            if output is not None:record_output(self.w,original,output)

    def finish(self):
        if any(ident not in self.completed for ident in self.pending): self.gap()
        if any(self.output(ident) is None for ident in self.pending if ident in self.completed):self.gap()
        # Source receipts are independently retained by the existing deletion
        # outbox even if the global statistics file is temporarily unavailable.
        try: Source(self.w.store).flush()
        except Exception: self.gap()
