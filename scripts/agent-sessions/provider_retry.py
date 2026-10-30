"""Original-worker continuations after confirmed pre-response HTTP failures.

Only the pinned zero-retry native provider is eligible. A continuation carries
no user input. This ledger is observation/recovery evidence, never permission
for a replacement worker, process or browser to submit inference.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from attachment_store import birth
from codex_rpc import RPCRejected
from goal_clock import boot
from run_store import event, get_run
from session_store import encode, now

DELAY_NS = 60_000_000_000
MAX_ATTEMPTS = 5
OPEN = ('waiting', 'submitting', 'continuing')


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def snapshot(store, run):
    if not store.db.execute("SELECT 1 FROM sqlite_master WHERE name='provider_retries' AND type='table'").fetchone():
        return None
    row = store.db.execute('SELECT * FROM provider_retries WHERE run_id=? AND session_id=?', (run['id'], run['session_id'])).fetchone()
    if row is None:
        return None
    value = json.loads(row['payload']); state = row['state']; remaining = 0
    if state in OPEN:
        try:
            worker = json.loads(run['worker'] or '{}'); original = value['binding']
            if (not run['busy'] or original['boot'] != boot() or worker.get('pid') != original['pid']
                    or worker.get('birth') != original['birth'] or birth(original['pid']) != original['birth']):
                state = 'unknown'
            elif state == 'waiting':
                remaining = max(0, (value['deadlineNs'] - time.monotonic_ns()) // 1_000_000)
        except (OSError, ValueError, TypeError, KeyError):
            state = 'unknown'
    return {'state': state, 'sequence': row['sequence'], 'attempt': row['attempt'], 'maxAttempts': MAX_ATTEMPTS,
            'nextAttempt': min(MAX_ATTEMPTS, row['attempt'] + 1), 'remainingMs': remaining,
            'error': value['error'], 'httpStatusCode': value['httpStatusCode'], 'sampledAt': now()}


class ProviderRetry:
    def __init__(self, worker):
        self.w = worker; self.original = None; self.account = None; self.task = None
        self.pending = None; self.state = None; self.attempt = 0; self.sequence = 1
        self.failed_turn = None; self.retry_turn = None; self.deadline = None
        self.progress = False; self.native_retry = False; self.failure = None; self.receipts = None
        self.saved_live_open = False; self.closed = False
        self.held_turns = set()
        from goal_retry import GoalRetry
        self.goal = GoalRetry(self)
        self.goal_mode = False

    def eligible(self):
        from image_provider import selection
        from profile import CODEX_VERSION, CODEX_SHA256
        w = self.w; engine = w.config['engine']
        return (engine.get('version') == CODEX_VERSION and engine.get('sha256') == CODEX_SHA256
                and bool(w.config.get('apiProvider') or selection(engine.get('profile'))))

    def identity(self):
        w = self.w; row = get_run(w.store, w.run_id)
        worker_birth = birth(os.getpid()); native_birth = birth(w.client.child.pid)
        if not worker_birth or not native_birth: raise ValueError('Original process identity unavailable')
        return {'owner': {'type': w.store.owner_type, 'id': w.store.owner_id}, 'sessionId': w.session_id,
                'runId': w.run_id, 'requestId': row['request_id'], 'inputSha256': row['payload_hash'],
                'configSha256': digest(json.loads(row['config'])), 'threadId': w.thread_id,
                'release': w.manifest['release'], 'pid': os.getpid(), 'birth': worker_birth, 'boot': boot(),
                'nativePid': w.client.child.pid, 'nativeBirth': native_birth}

    async def bind(self):
        if not self.eligible():
            return
        try:
            self.original = self.identity()
            if not self.w.config.get('apiProvider'):
                account = await self.w.client.request('account/read', {'refreshToken': False}, timeout=5)
                if not isinstance(account, dict) or not isinstance(account.get('account'), dict):
                    raise ValueError('No original native account')
                self.account = digest(account['account'])
        except Exception:
            # Failure to qualify retries cannot prevent the original user run.
            self.original = None

    def local_gate(self):
        w = self.w; db = w.store.db; row = get_run(w.store, w.run_id)
        owner = json.loads(row['worker'] or '{}')
        session = w.store.row(w.session_id); settings = json.loads(session['settings'])
        if (self.closed or w.stopping or w.done.is_set() or w.uncertain_effect or not self.eligible()
                or not row['busy'] or row['state'] != 'running' or row['turn_id'] != self.failed_turn
                or self.identity() != self.original or digest(w.config) != self.original['configSha256']
                or session['thread_id'] != w.thread_id or session['revision'] != w.config['revision']
                or json.loads(session['engine']) != w.config['engine']
                or any(settings.get(k) != w.config[k] for k in ('providerId', 'model', 'effort', 'permissions'))
                or any(owner.get(k) != self.original[k] for k in ('pid', 'birth', 'release'))
                or w.client.child.returncode is not None or any(not t.done() for t in w.client.requests)):
            raise ValueError('Original retry binding changed')
        if any(w.items.get(ident, {}).get('status') != 'completed' for ident in w.generated_started):
            raise ValueError('Native image outcome is unconfirmed')
        from message_store import exists, pending_queue
        if exists(w.store) and (pending_queue(w.store, w.session_id) or db.execute(
                "SELECT 1 FROM session_messages WHERE session_id=? AND run_id=? AND state IN ('pending','dispatching','unknown')",
                (w.session_id, w.run_id)).fetchone()):
            raise ValueError('User input takes priority')
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='goal_commands'").fetchone():
            if db.execute("SELECT 1 FROM goal_commands WHERE session_id=? AND state='pending'", (w.session_id,)).fetchone():
                raise ValueError('Goal control takes priority')
        if w.goal_worker and w.goal_worker.native and w.goal_worker.native['status'] == 'active':
            raise ValueError('Native Goal is active')
        if self.goal_mode:
            self.goal.local_gate()
        if w.store.owner_type == 'project':
            with sqlite3.connect((Path(w.store.projects) / 'Projects.sqlite').as_uri() + '?mode=ro', uri=True) as projects:
                current = projects.execute("SELECT pins FROM projects WHERE id=? AND state='ready'", (w.store.owner_id,)).fetchone()
                if not current or json.loads(current[0]) != w.config['projectPins']:
                    raise ValueError('Project pins changed')
        hashed = hashlib.sha256()
        for receipt in db.execute('SELECT call_id,tool,arguments_hash,state,result FROM tools WHERE run_id=? ORDER BY call_id', (w.run_id,)):
            result = json.loads(receipt['result']) if receipt['result'] else None
            if (receipt['state'] not in ('completed', 'failed') or not isinstance(result, dict)
                    or type(result.get('success')) is not bool or result.get('error') == 'unknown'
                    or result.get('partialChangesPossible') is True):
                raise ValueError('Tool outcome is unconfirmed')
            hashed.update(encode(dict(receipt)).encode())
        return hashed.hexdigest()

    def write(self, state):
        w = self.w; db = w.store.db; self.state = state
        payload = {'binding': self.original, 'failedTurnId': self.failed_turn, 'retryTurnId': self.retry_turn,
                   'toolReceiptsSha256': self.receipts, 'deadlineNs': self.deadline,
                   'error': self.failure['text'], 'httpStatusCode': self.failure['httpStatusCode']}
        if self.goal_mode:
            payload['goal'] = self.goal.public_evidence()
        db.execute('''CREATE TABLE IF NOT EXISTS provider_retries(
            run_id TEXT PRIMARY KEY REFERENCES runs(id),session_id TEXT NOT NULL REFERENCES sessions(id),
            sequence INTEGER NOT NULL,attempt INTEGER NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL)''')
        db.execute('INSERT INTO provider_retries VALUES (?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET sequence=excluded.sequence,attempt=excluded.attempt,state=excluded.state,payload=excluded.payload',
                   (w.run_id, w.session_id, self.sequence, self.attempt, state, encode(payload)))
        event(w.store, w.session_id, w.run_id, 'run', w.store.run_present(get_run(w.store, w.run_id)), False)

    def observe(self, method, params):
        w = self.w
        if not self.original or params.get('threadId') != w.thread_id:
            return False
        self.goal.observe(method, params)
        if method == 'turn/started':
            self.native_retry = False
            if self.state == 'waiting':
                # No client is allowed to turn a timer into parallel inference.
                w.uncertain_effect = True; w.outcome = 'unknown'; w.defer_stop()
            elif self.state == 'submitting':
                self.retry_turn = params['turn']['id']
                if self.retry_turn == self.failed_turn:
                    self.unknown_start()
                    return True
                if self.goal_mode:
                    try: self.goal.resumed(self.retry_turn)
                    except Exception:
                        self.unknown_start()
                        # The native turn ID is nevertheless observed. Let the
                        # normal stopping path adopt and interrupt that turn.
                        return False
                with w.store.db:
                    meta = json.loads(get_run(w.store, w.run_id)['worker'] or '{}')
                    if self.saved_live_open: meta['liveGoalOpen'] = True
                    w.store.db.execute('UPDATE runs SET worker=? WHERE id=?', (encode(meta), w.run_id))
                    self.write('continuing')
        elif method == 'error' and params.get('willRetry') is True:
            self.native_retry = True
        elif method == 'item/agentMessage/delta' and params.get('turnId') == self.retry_turn and params.get('delta'):
            self.progress = True
        elif method == 'item/started' and params.get('turnId') == self.retry_turn and (params.get('item') or {}).get('type') in ('dynamicToolCall', 'webSearch', 'imageGeneration'):
            self.progress = True
        elif (method == 'turn/completed' and self.goal_mode and self.state == 'continuing'
                and params.get('turn', {}).get('status') == 'completed'
                and params['turn'].get('id') == w.turn_id):
            self.progress = True
            with w.store.db: self.write('completed')
        elif method == 'turn/completed' and params.get('turn', {}).get('status') == 'failed':
            from provider_errors import describe
            turn = params['turn']; failure = describe(turn.get('error'), api=bool(w.config.get('apiProvider')))
            if turn.get('id') != w.turn_id: return False
            error = turn.get('error')
            info = error.get('codexErrorInfo') if isinstance(error, dict) else None
            code = next(iter(info)) if isinstance(info, dict) and len(info) == 1 else None
            if (not self.eligible() or self.native_retry or code != 'httpConnectionFailed'
                    or failure['httpStatusCode'] not in (502, 503, 504) or not failure['transientCandidate']):
                return False
            self.failed_turn = turn['id']; self.failure = failure
            self.goal_mode = bool(w.config.get('goalExecution') or self.goal.active_execution())
            if self.goal_mode and (type(w.config.get('goalRetryProtocol')) is not int or w.config['goalRetryProtocol'] != 1):
                # New original-Goal recovery remains disabled until its native
                # runtime qualification. Ordinary released retries are intact.
                self.goal_mode = False
                return False
            if self.goal_mode:
                try: evidence = self.goal.qualify(self.failed_turn, failure['httpStatusCode'])
                except Exception:
                    w.error = failure['text'] + ' Automatic Goal continuation was held because its original failure evidence could not be confirmed.'
                    return False
                # Native Goal read tools do not necessarily emit Studio dynamic
                # tool events. Their complete original call/result is still
                # confirmed model progress within this new failed turn.
                if self.attempt and evidence['native']['functionCallsChecked']:
                    self.progress = True
            if self.progress:
                self.attempt = 0; self.sequence += 1; self.progress = False
            if self.attempt >= MAX_ATTEMPTS:
                w.error = failure['text'] + ' Automatic continuation stopped after five attempts. Send or Play explicitly to continue.'
                with w.store.db: self.write('exhausted')
                return False
            # Establish the failed native turn before checking the frozen run.
            with w.store.db:
                w.store.db.execute('UPDATE runs SET turn_id=? WHERE id=?', (self.failed_turn, w.run_id))
                try: self.receipts = self.local_gate()
                except Exception: return False
                meta = json.loads(get_run(w.store, w.run_id)['worker'] or '{}')
                self.saved_live_open = meta.get('liveGoalOpen') is True
                meta['liveGoalOpen'] = False; meta['messageTurnActive'] = False
                w.store.db.execute('UPDATE runs SET worker=? WHERE id=?', (encode(meta), w.run_id))
                self.deadline = time.monotonic_ns() + DELAY_NS
                self.write('waiting')
            self.held_turns.add(self.failed_turn)
            self.pending = True
            if self.task is None or self.task.done(): self.task = asyncio.create_task(self.run())
            return True
        return False

    async def gate(self):
        w = self.w
        if self.local_gate() != self.receipts:
            raise ValueError('Original receipts changed')
        if w.config.get('apiProvider'):
            from api_provider_store import ApiProviders
            ApiProviders(w.manifest['providers']).validate_active(w.run_id, w.store.owner_type, w.store.owner_id,
                w.session_id, w.row['request_id'], w.config, w.api_worker)
        else:
            account = await w.client.request('account/read', {'refreshToken': False}, timeout=5)
            if digest(account.get('account')) != self.account: raise ValueError('Native account changed')
        thread = await w.client.request('thread/read', {'threadId': w.thread_id, 'includeTurns': False}, timeout=5)
        # In the pinned runtime systemError is also an idle thread: a recorded
        # error flag remains until its next turn. Running/waiting threads use
        # active instead. The precise final failure above is still mandatory.
        if thread.get('thread', {}).get('status', {}).get('type') not in ('idle', 'systemError'):
            raise ValueError('Native idle state not confirmed')
        if self.goal_mode:
            await self.goal.gate()
        if self.local_gate() != self.receipts:
            raise ValueError('Original receipts changed during readback')

    async def run(self):
        w = self.w
        try:
            while self.pending and not w.done.is_set():
                self.pending = None
                remaining = max(0, (self.deadline - time.monotonic_ns()) / 1_000_000_000)
                try:
                    await asyncio.wait_for(w.done.wait(), remaining)
                    return
                except asyncio.TimeoutError: pass
                # These are the same locks used for human native mutations.
                async with w.message_worker.lock:
                    if w.goal_worker:
                        async with w.goal_worker.lock: await self.submit()
                    else: await self.submit()
                if not self.pending and not w.done.is_set():
                    # The one original reader will either finish this run or
                    # report another final failure. No second timer owns it.
                    while not self.pending and not w.done.is_set():
                        await asyncio.sleep(.1)
        except asyncio.CancelledError:
            raise
        except Exception:
            if not w.stopping and not w.done.is_set():
                w.outcome = 'failed'; w.error = self.failure['text'] + ' Automatic continuation was held because its original admission could not be confirmed.'
                w.done.set()

    async def submit(self):
        w = self.w
        await self.gate()
        w.store.db.execute('BEGIN IMMEDIATE')
        try:
            if self.local_gate() != self.receipts: raise ValueError('Original retry admission changed')
            if self.goal_mode: self.goal.local_gate(read_native=True)
            self.attempt += 1; self.retry_turn = None
            self.write('submitting'); w.store.db.commit()
        finally:
            if w.store.db.in_transaction: w.store.db.rollback()
        w.error = None
        try:
            if self.goal_mode:
                await self.goal.submit()
                return
            result = await w.client.request('turn/start', {'threadId': w.thread_id, 'input': [],
                'model': w.config['model'], 'effort': w.config['effort'],
                'serviceTier': 'priority' if w.config.get('fastMode') else 'default'})
            ident = result.get('turn', {}).get('id')
            if not isinstance(ident, str) or not ident or len(ident.encode()) > 256 or ident == self.failed_turn:
                raise ValueError('Invalid original continuation receipt')
            if self.retry_turn is None:
                # RPC responses and notifications need not arrive in one
                # prescribed order. Either original receipt confirms the ID.
                self.retry_turn = ident; w.turn_id = ident
                with w.store.db:
                    meta = json.loads(get_run(w.store, w.run_id)['worker'] or '{}')
                    meta['messageTurnActive'] = not w.stopping
                    if self.saved_live_open: meta['liveGoalOpen'] = True
                    w.store.db.execute('UPDATE runs SET worker=? WHERE id=?', (encode(meta), w.run_id))
                    self.write('continuing')
                from run_store import transition
                if not w.done.is_set(): transition(w.store, w.run_id, 'running', turn_id=ident)
                if w.goal_worker: w.goal_worker.idle.clear()
            elif self.retry_turn != ident:
                raise ValueError('Contradictory original continuation receipts')
        except RPCRejected:
            if self.retry_turn is not None:
                self.unknown_start(); return
            if self.goal_mode:
                # A mutation error alone does not prove absence of an effect.
                # Retain a known refusal only while the original blocked Goal,
                # idle native process and complete failed section still match.
                try: await self.gate()
                except Exception:
                    self.unknown_start(); return
                if self.retry_turn is not None:
                    self.unknown_start(); return
            continuation = 'original Goal continuation' if self.goal_mode else 'empty continuation'
            w.outcome = 'failed'; w.error = self.failure['text'] + ' The native client rejected the ' + continuation + '.'; w.done.set()
        except asyncio.TimeoutError:
            # Observe a confirmed start, but never submit an unconfirmed start
            # again. Its eventual native completion remains authoritative.
            if self.retry_turn is None:
                self.unknown_start()
        except Exception:
            self.unknown_start()

    def unknown_start(self):
        w = self.w; w.uncertain_effect = True; w.outcome = 'unknown'
        w.error = 'The original continuation start is unconfirmed. It was not submitted again.'
        if self.goal_mode: self.goal.uncertain()
        w.defer_stop()

    async def cancel_for_control(self):
        """A human Goal control/Stop supersedes this one original timer."""
        if self.state not in OPEN or self.w.uncertain_effect:
            return
        unconfirmed = self.state == 'submitting' and self.retry_turn is None
        if unconfirmed:
            self.w.uncertain_effect = True
            self.w.outcome = 'unknown'
            self.w.error = 'The original continuation start is unconfirmed. It was not submitted again.'
            if self.goal_mode: self.goal.uncertain()
        self.closed = True
        self.pending = None
        if self.task and self.task is not asyncio.current_task():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        with self.w.store.db:
            self.write('unknown' if unconfirmed else 'cancelled')

    async def close(self):
        self.closed = True
        if self.task:
            self.task.cancel(); await asyncio.gather(self.task, return_exceptions=True)
        if self.state in OPEN:
            state = ('unknown' if self.w.uncertain_effect or self.w.outcome == 'unknown'
                     else 'completed' if self.w.outcome == 'completed' else 'cancelled')
            with self.w.store.db: self.write(state)
