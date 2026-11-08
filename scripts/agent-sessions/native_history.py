"""Read original native archives for an explicit import. Never resume or repair."""
from collections import Counter
import hashlib
import json
import os

from profile import regular
from session_store import encode
from store import ProjectFault

MAX_ARCHIVE = 256 * 1024 * 1024
MAX_LINE = 16 * 1024 * 1024


def fail(text):
    raise ProjectFault(text + ' Original history was preserved; no model request was started.', 409)


def decoded(raw):
    def unique(pairs):
        value = {}
        for key, part in pairs:
            if key in value: raise ValueError('duplicate field')
            value[key] = part
        return value
    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        fail('An original native record is unreadable.')


def lines(path):
    size = 0
    with regular(path).open('rb') as stream:
        while raw := stream.readline(MAX_LINE + 1):
            size += len(raw)
            if size > MAX_ARCHIVE or len(raw) > MAX_LINE or not raw.endswith(b'\n'):
                fail('The original native archive is too large or has an incomplete record.')
            value = decoded(raw)
            if not isinstance(value, dict): fail('An original native record is not an object.')
            yield value


def text(parts, *, user=False):
    if isinstance(parts, str): return parts
    if not isinstance(parts, list): fail('Original native message content is unavailable.')
    result = []
    for part in parts:
        if not isinstance(part, dict): fail('An original native content block is invalid.')
        if part.get('type') in ('text', 'input_text', 'output_text') and isinstance(part.get('text'), str):
            result.append(part['text'])
        elif user and part.get('type') in ('input_image', 'image', 'document', 'tool_result', 'tool_reference'):
            continue  # Actual accepted attachment bytes / tool receipts are checked separately.
        else: fail('An original native message has content that cannot be imported.')
    return '\n'.join(result)


def claude_metadata(record):
    """Known archive-only client context and wire/cache observations.

    These remain in the hashed original archive. In particular, embedded API
    message copies and tool summaries never acquire conversation/tool authority.
    Actual accepted attachments and effects are verified separately by Studio.
    """
    kind=record.get('type')
    if kind=='attachment':
        value=record.get('attachment')
        return isinstance(value,dict) and value.get('type') in (
            'environment','model','session_context','date','credential_org','prompt_snapshot','total_tokens_reminder')
    if kind=='atis-latch':return isinstance(record.get('atis'),str)
    if kind=='api-request-shape':return isinstance(record.get('shape'),dict) and isinstance(record.get('shapeHash'),str)
    if kind=='api-request-blob':return isinstance(record.get('message'),dict) and isinstance(record.get('hash'),str)
    if kind=='api-request':return isinstance(record.get('params'),dict) and isinstance(record.get('tail'),list) and isinstance(record.get('id'),str)
    if kind=='tools-used':return isinstance(record.get('tools'),list)
    if kind=='cost-state':return isinstance(record.get('modelUsage'),dict)
    return False


class NativeHistory:
    def __init__(self, store, sid):
        self.store, self.sid = store, sid
        self.archives = []; self.assistants = Counter(); self.by_id = {}
        self.users = []; self.calls = {}; self.results = set(); self.opaque = 0
        self.call_turns = {}; self.outputs = {}; self.turn = None; self.namespaces = {}
        self.observations = {}

    def archive(self, path):
        path = regular(path)
        if path.stat().st_nlink != 1:
            fail('An original native archive has a foreign file identity.')
        with path.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        self.archives.append({'path': str(path.relative_to(self.store.directory / self.sid)) if path.is_relative_to(self.store.directory / self.sid) else str(path),
                              'sha256': digest, 'bytes': path.stat().st_size})

    def call(self, ident, name, arguments):
        if not isinstance(ident, str) or not ident or not isinstance(name, str): fail('A native tool identity is missing.')
        if isinstance(arguments, str): arguments = decoded(arguments)
        if not isinstance(arguments, dict): fail('Original native tool arguments are unavailable.')
        value = {'name': name, 'arguments': arguments}
        if ident in self.calls and self.calls[ident] != value: fail('A native call ID has conflicting originals.')
        self.calls[ident] = value

    def codex(self):
        from native_tools import binding
        try: original = binding(self.store, self.sid)
        except (ValueError, OSError): fail('The original Codex rollout binding is unavailable.')
        if original is None:
            if self.store.db.execute('SELECT 1 FROM runs WHERE session_id=? AND turn_id IS NOT NULL', (self.sid,)).fetchone():
                fail('A previous Codex turn has no original thread binding.')
            return
        self.archive(original['path']); first = True
        for record in lines(original['path']):
            kind = record.get('type'); value = record.get('payload')
            if not isinstance(value, dict): fail('An original Codex payload is unavailable.')
            if first:
                if (kind != 'session_meta' or value.get('id') != original['threadId']
                        or value.get('model_provider') not in (None, original['provider'])):
                    fail('The original Codex archive belongs to another thread or provider.')
                first = False
            if kind == 'turn_context' or kind == 'event_msg' and value.get('turn_id'):
                self.turn = value.get('turn_id')
            if kind == 'response_item':
                item = value.get('type')
                if item == 'message':
                    role = value.get('role')
                    if role == 'assistant': self.assistants[text(value.get('content'))] += 1
                    elif role == 'user': self.users.append(text(value.get('content'), user=True))
                    elif role not in ('developer', 'system'): fail('An original Codex message has an unsupported role.')
                elif item == 'function_call':
                    self.call(value.get('call_id'), value.get('name'), value.get('arguments'))
                    self.call_turns[value['call_id']] = self.turn; self.namespaces[value['call_id']] = value.get('namespace')
                elif item == 'function_call_output':
                    self.results.add(value.get('call_id')); self.outputs[value.get('call_id')] = value.get('output')
                elif item == 'reasoning': self.opaque += 1
                else: fail('A native Codex response item cannot be represented in the common history.')
            elif kind == 'event_msg':
                if value.get('type') == 'item_completed':
                    item = value.get('item', {})
                    if item.get('type') == 'AgentMessage':
                        content = text(item.get('content'))
                        ident = item.get('id')
                        if ident in self.by_id and self.by_id[ident] != content: fail('A native assistant item changed its original content.')
                        self.by_id[ident] = content
                    elif item.get('type') == 'Extension' and item.get('kind') in ('web_search', 'webSearch'):
                        self.observations[item.get('id')] = item
            elif kind not in ('session_meta', 'turn_context', 'token_usage_record', 'compacted', 'world_state'):
                fail('The Codex archive contains an unsupported record format.')
        if first: fail('The original Codex archive is empty.')

    def claude(self):
        from claude_history import ClaudeHistory, inventory
        original = ClaudeHistory(self.store, self.sid).get()
        if original['phase'] not in ('allocated', 'ready'): fail('The original Claude execution is unconfirmed.')
        root = self.store.directory / self.sid / 'Claude/Projects'
        if original['phase'] == 'allocated' and not root.exists(): return
        current = inventory(root)
        if current != original['inventory']: fail('The original Claude archive changed after its confirmed receipt.')
        native_id = original['runtime']['nativeSessionId']; found = False
        for name in sorted(current):
            path = root / name
            self.archive(path)
            if path.suffix != '.jsonl': continue
            seen = set()
            for record in lines(path):
                # Subagent transcripts retain their bytes but do not become the
                # main conversation or acquire the main run's authority.
                if record.get('sessionId') != native_id: continue
                found = True
                if record.get('isSidechain') is True: continue
                kind = record.get('type')
                if kind in ('user', 'assistant'):
                    message = record.get('message', {})
                    if not isinstance(message, dict): fail('An original Claude message is unavailable.')
                    ident = record.get('uuid')
                    if not isinstance(ident, str) or ident in seen: fail('An original Claude message identity is missing or duplicated.')
                    seen.add(ident); parts = message.get('content')
                    if kind == 'user':
                        self.users.append(text(parts, user=True))
                        for part in parts if isinstance(parts, list) else []:
                            if part.get('type') == 'tool_result': self.results.add(part.get('tool_use_id'))
                    else:
                        if not isinstance(parts, list): fail('Original Claude assistant blocks are unavailable.')
                        for part in parts:
                            if part.get('type') == 'text' and isinstance(part.get('text'), str): self.assistants[part['text']] += 1
                            elif part.get('type') == 'tool_use':
                                name = part.get('name', '')
                                if name.startswith('mcp__studio__'): name = 'studio_' + name[len('mcp__studio__'):]
                                arguments = part.get('input')
                                if isinstance(arguments, dict) and set(arguments) == {'request'} and isinstance(arguments['request'], dict): arguments = arguments['request']
                                self.call(part.get('id'), name, arguments)
                            elif part.get('type') in ('thinking', 'redacted_thinking'): self.opaque += 1
                            else: fail('An original Claude assistant block cannot be imported.')
                elif kind not in ('summary', 'system', 'progress', 'file-history-snapshot', 'queue-operation', 'custom-title', 'last-prompt') and not claude_metadata(record):
                    fail('The Claude archive contains an unsupported record format.')
        if original['phase'] == 'ready' and not found: fail('The original Claude transcript is missing.')

    def read(self):
        row = self.store.row(self.sid)
        if json.loads(row['engine']).get('kind') == 'claude-code': self.claude(); self.kind = 'claude-code'
        else: self.codex(); self.kind = 'codex'
        if self.calls.keys() - self.results: fail('An original native tool call has no confirmed result.')
        if self.results - self.calls.keys(): fail('An original native tool result has no matching call.')
        self.verify()
        return self

    def verify(self):
        for entry in self.archives:
            path = regular(self.store.directory/self.sid/entry['path'])
            with path.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != entry['sha256']:
                    fail('The original native archive changed while it was being read.')

    def assistant(self, ident, value, truncated=False):
        if not self.archives: fail('An assistant message is missing its original native archive.')
        original = self.by_id.get(ident)
        if truncated:
            if original is None or not original.startswith(value): fail('A truncated assistant item has no complete matching native original.')
            value = original
        elif original is not None and original != value: fail('Studio and native assistant originals disagree.')
        if self.archives and self.assistants[value] <= 0: fail('A Studio assistant item has no matching complete native message.')
        if self.archives: self.assistants[value] -= 1
        return value

    def confirmed_call(self, ident, name, arguments):
        if self.calls.get(ident) != {'name': name, 'arguments': arguments} or ident not in self.results:
            fail('A Studio tool receipt has no matching native call and result.')

    def source(self):
        return {'kind': self.kind, 'archives': self.archives, 'opaqueRecordsRetained': self.opaque}
