"""Living original-query retry authority. A persisted row never starts a worker.

The qualified frozen protocol is captured before credential-lease admission.
No original prompt, upload or acknowledged tool result is submitted here.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

from attachment_store import birth
from claude_history import ClaudeHistory
from claude_provider_errors import describe
from claude_runtime import profile
from goal_clock import boot
from run_store import event, get_run
from session_store import encode, identity
from store import ProjectFault

DELAY_NS = 60_000_000_000
MAX_ATTEMPTS = 5


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def valid_claim(value):
    if (not isinstance(value, dict) or set(value) != {'ordinal', 'holdId', 'stepInputId', 'failedResultId', 'inputRequestId'}
            or type(value.get('ordinal')) is not int or not 1 <= value['ordinal'] <= 2**53 - 1):
        raise ProjectFault('The original Claude retry claim is invalid.', 409)
    for key in ('holdId', 'stepInputId', 'failedResultId', 'inputRequestId'):
        identity(value[key])
    return value


class ClaudeRetry:
    def __init__(self, worker):
        self.w = worker; pin = profile(); runtime = worker.config['engine'].get('claude', {})
        self.enabled = (type(worker.config.get('claudeRetryProtocol')) is int and worker.config['claudeRetryProtocol'] == 1
            and runtime.get('runtimeProfileId') == pin['id'] and runtime.get('sha256') == pin['native']['files']['claude']['sha256']
            and runtime.get('sdkVersion') == pin['sdk']['version'] and runtime.get('sdkArchiveSha256') == pin['sdk']['archiveSha256'])
        self.original = None; self.state = None; self.sequence = 1; self.attempt = 0; self.ordinal = 0
        self.claim = None; self.failed = None; self.failed_input = None; self.logical_step = None
        self.failure = None; self.receipts = None; self.deadline = None; self.task = None
        self.echo = asyncio.Event(); self.receipt = None; self.admission_id = None; self.progress = False
        self.closed = False; self.uncertain_start = False; self.results = set()
        self.original_goal = None; self.goal_execution = None
        self.native_process = None
        self.broker_confirmed = False

    @property
    def holding(self):
        return self.state in ('waiting', 'submitting')

    def goal(self):
        value = self.w.claude_goal
        return value if value and value.begun and value.started else None

    def process_binding(self, *, observing_stop=False):
        w = self.w
        ended_original = (observing_stop and w.native is self.native_process and w.native is not None
                          and w.native.returncode is not None and self.original is not None)
        if not w.native or w.native.returncode is not None and not ended_original:
            raise ProjectFault('The original Claude query process is unavailable.', 409)
        return {'owner': {'type': w.store.owner_type, 'id': w.store.owner_id}, 'sessionId': w.session_id,
            'runId': w.run_id, 'requestId': w.row['request_id'], 'configSha256': digest(w.config),
            'pid': os.getpid(), 'birth': birth(os.getpid()), 'boot': boot(), 'release': w.manifest['release'],
            'nativePid': w.native.pid, 'nativeBirth': self.original['nativeBirth'] if ended_original else birth(w.native.pid),
            'nativeSessionId': w.config['engine']['claude']['nativeSessionId'], 'credentialSha256': digest(w.credential_lease)}

    def bind(self):
        if not self.enabled:
            return
        db = self.w.store.db
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='provider_retries'").fetchone() and db.execute(
                'SELECT 1 FROM provider_retries WHERE run_id=?', (self.w.run_id,)).fetchone():
            raise ProjectFault('Preserve the original retry worker and ledger. They were not restored or replayed.', 409)
        self.native_process = self.w.native; self.original = self.process_binding()
        if not self.original['birth'] or not self.original['nativeBirth']:
            raise ProjectFault('The original Claude process identity is unconfirmed.', 409)

    def gate(self, *, stopping=False, controls=True, with_receipts=True):
        w = self.w; row = get_run(w.store, w.run_id); session = w.store.row(w.session_id)
        settings = json.loads(session['settings'])
        if (not self.enabled or not self.original or self.closed or self.uncertain_start
                or not row['busy'] or row['state'] not in ('starting', 'running', 'stopping')
                or not stopping and (w.stopping or w.done.is_set() or row['state'] == 'stopping')
                or w.uncertain_effect or not stopping and (w.admission_denial or w.quota_blocked)
                or self.process_binding(observing_stop=stopping) != self.original or json.loads(row['config']) != w.config
                or json.loads(row['worker'] or '{}') != w.credential_worker
                or session['revision'] != w.config['revision'] or json.loads(session['engine']) != w.config['engine']
                or any(settings.get(key) != w.config[key] for key in ('providerId', 'model', 'effort', 'permissions'))):
            raise ProjectFault('The original Claude retry binding or admission changed.', 409)
        from claude_run_leases import ClaudeRunLeases
        if not ClaudeRunLeases(w.manifest['providers']).current_lease(w.credential_lease, w.credential_worker):
            raise ProjectFault('The original Claude credential lease changed.', 409)
        history = ClaudeHistory(w.store, w.session_id).get()
        if (history['phase'] not in ('opening', 'active') or history['activeRunId'] != w.run_id
                or history['runtime'] != w.config['engine']['claude']):
            raise ProjectFault('The original Claude conversation is no longer bound.', 409)
        if (not stopping and self.failed and self.state in ('waiting','submitting') and not self.receipt
                and w.native_result != self.failed):
            raise ProjectFault('The current original native failure changed.', 409)
        runtime = self.goal()
        if runtime:
            value = runtime.journal.read()
            if (not stopping and (value['state'] != 'running' or runtime.journal.expired(value))
                    or self.original_goal and self.original_goal != digest(value['contract'])):
                raise ProjectFault('The original Play or its active-time budget changed.', 409)
            if value['steps'][-1]['report'] and value['steps'][-1]['report']['status'] in ('complete', 'blocked'):
                raise ProjectFault('The original Goal report ended this step.', 409)
        elif self.original_goal is not None:
            raise ProjectFault('The original retry Play is no longer available.', 409)
        if controls:
            from message_store import pending_queue
            pending = []
            if w.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='goal_commands'").fetchone():
                for command in w.store.db.execute("SELECT payload FROM goal_commands WHERE session_id=? AND state='pending'", (w.session_id,)):
                    data = json.loads(command[0])
                    if any((data.get(key) or {}).get('runId') == w.run_id for key in ('_claudeTarget','_claudeLiveTarget')):
                        pending.append(data)
            if pending_queue(w.store, w.session_id) or pending:
                raise ProjectFault('Human controls or queued input take priority over this retry.', 409)
        if w.store.owner_type == 'project':
            with sqlite3.connect((Path(w.store.projects) / 'Projects.sqlite').as_uri() + '?mode=ro', uri=True) as db:
                pins = db.execute("SELECT pins FROM projects WHERE id=? AND state='ready'", (w.store.owner_id,)).fetchone()
                if not pins or json.loads(pins[0]) != w.config['projectPins']:
                    raise ProjectFault('The original project pins changed.', 409)
        if any(not task.done() for task in w.broker.calls.values()):
            raise ProjectFault('An original tool is still running.', 409)
        if not with_receipts:
            return None
        hashed = hashlib.sha256()
        for receipt in w.store.db.execute('SELECT call_id,tool,arguments_hash,state,result FROM tools WHERE run_id=? ORDER BY call_id', (w.run_id,)):
            result = json.loads(receipt['result']) if receipt['result'] else None
            if (receipt['state'] not in ('completed', 'failed') or not isinstance(result, dict)
                    or type(result.get('success')) is not bool or result.get('error') == 'unknown'
                    or result.get('partialChangesPossible') is True):
                raise ProjectFault('An original tool outcome is unconfirmed.', 409)
            hashed.update(encode(dict(receipt)).encode())
        return hashed.hexdigest()

    def write(self, state, receipt=None):
        w = self.w; db = w.store.db; self.state = state
        value = {'binding': self.original, 'deadlineNs': self.deadline, 'toolReceiptsSha256': self.receipts,
            'error': self.failure['text'], 'httpStatusCode': self.failure['httpStatusCode'],
            'engine': 'claude-code', 'ordinal': self.ordinal, 'claim': self.claim,
            'failedResultId': self.failed['uuid'], 'failedInputId': self.failed_input, 'stepInputId': self.logical_step,
            'admissionId': self.admission_id, 'inputReceipt': self.receipt, 'uncertainStart': self.uncertain_start,
            'brokerConfirmed': self.broker_confirmed}
        if self.goal_execution:
            value['goal'] = {'executionId': self.goal_execution, 'contractSha256': self.original_goal}
        db.execute('''CREATE TABLE IF NOT EXISTS provider_retries(
            run_id TEXT PRIMARY KEY REFERENCES runs(id),session_id TEXT NOT NULL REFERENCES sessions(id),
            sequence INTEGER NOT NULL,attempt INTEGER NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL)''')
        db.execute('INSERT INTO provider_retries VALUES (?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET sequence=excluded.sequence,attempt=excluded.attempt,state=excluded.state,payload=excluded.payload',
            (w.run_id, w.session_id, self.sequence, self.attempt, state, encode(value)))
        if receipt:
            event(w.store, w.session_id, w.run_id, 'claudeRetryReceipt',
                {'schema': 1, 'bindingSha256': digest(self.original), 'stepInputId': self.logical_step,
                 'goalExecutionId': self.goal_execution, 'goalContractSha256': self.original_goal,
                 'sequence': self.sequence, 'attempt': self.attempt, 'ordinal': self.ordinal, **receipt}, False)
        event(w.store, w.session_id, w.run_id, 'run', w.store.run_present(get_run(w.store, w.run_id)), False)

    def budget_claim(self):
        value = self.goal().journal.read(); timing = value.get('retryTime') or {}
        held = timing.get('hold')
        if held and held['claim']['holdId'] == self.claim['holdId']:
            return dict(held['claim'])
        return {'ordinal': timing.get('ordinal', 0) + 1,
                **{key: self.claim[key] for key in ('holdId', 'stepInputId', 'failedResultId')}}

    async def frame(self, frame):
        native = frame['native']; reported = frame['identity']; retry = reported.get('nativeRetry')
        if retry:
            if (not self.enabled or not isinstance(retry, dict) or retry.get('schema') != 1
                    or not self.claim or retry.get('claim') != self.claim):
                raise ProjectFault('The native retry receipt belongs to another original claim.', 409)
            ids = reported.get('nativeInputRequestIds', [])
            if (reported.get('studioRequestId') != self.w.row['request_id']
                    or reported.get('nativeSessionId') != self.original['nativeSessionId']
                    or native.get('session_id') != self.original['nativeSessionId']
                    or ids and ids != [self.claim['inputRequestId']]
                    or self.goal() and reported.get('studioGoalStepId') != self.claim['stepInputId']):
                raise ProjectFault('The original retry input/session binding changed.', 409)
            if native['type'] == 'user' and native.get('isReplay') is True:
                if (native.get('uuid') != self.claim['inputRequestId'] or ids != [self.claim['inputRequestId']]
                        or reported.get('nativeMessageId') != self.claim['inputRequestId']
                        or reported.get('nativeInputReceiptKind') != 'stdinEmptyBlocksEcho'
                        or reported.get('nativeInputTextSha256') != hashlib.sha256(b'').hexdigest()
                        or not self.admission_id or self.state not in ('submitting', 'continuing')):
                    raise ProjectFault('The exact native empty-block input was not confirmed.', 409)
                if not self.receipt:
                    self.gate(stopping=self.w.stopping, controls=not self.w.stopping)
                    self.receipt = {'inputId': self.claim['inputRequestId'], 'messageId': native['uuid'], 'kind': 'stdinEmptyBlocksEcho'}
                    runtime = self.goal()
                    if runtime:
                        runtime.journal.record_retry_echo(self.claim, self.receipt, stopping=self.w.stopping)
                        if not self.w.stopping:
                            runtime.clock.resume(runtime.journal.spec['executionId'])
                        else:
                            runtime.clock.mark_unknown(runtime.journal.spec['executionId'])
                    with self.w.store.db: self.write('continuing', self.receipt)
                    self.w.native_result = None; self.w.input_receipt.set(); self.echo.set()
            elif native['type'] in ('assistant', 'stream_event', 'result') and not self.receipt:
                raise ProjectFault('A retry response arrived without its original input echo.', 409)
            self.model_progress(native)
            return True
        if self.enabled:
            self.model_progress(native)
        return False

    def model_progress(self, native):
        if native['type'] == 'assistant' and native.get('error') is None:
            if any(part.get('type') == 'tool_use' or part.get('type') == 'text' and part.get('text')
                   for part in (native.get('message') or {}).get('content', [])):
                self.progress = True
        elif native['type'] == 'stream_event' and (native.get('event') or {}).get('delta', {}).get('type') == 'text_delta':
            if native['event']['delta'].get('text'): self.progress = True

    async def result(self, frame):
        if not self.enabled or not self.original:
            return False
        native = frame['native']; reported = frame['identity']; identifier = identity(native['uuid'])
        if identifier in self.results or len(self.results) >= 4096:
            raise ProjectFault('The original native result was duplicated or exceeded its bound.', 409)
        self.results.add(identifier)
        if not native.get('is_error'):
            if self.state == 'continuing':
                with self.w.store.db: self.write('completed', {'kind': 'result', 'resultId': identifier, 'inputId': self.claim['inputRequestId']})
                if (not self.w.stopping and not self.w.uncertain_effect and not self.w.quota_blocked
                        and not self.w.admission_denial and self.w.error == self.failure['text']):
                    self.w.error = None
            return False
        boundary = reported.get('nativeRetryBoundary')
        failure = describe(native.get('providerError'), self.w.native_error_code, self.w.native_retry_observed)
        if (not failure['transientCandidate'] or failure['nativeRetryObserved'] or not isinstance(boundary, dict)
                or boundary.get('schema') != 1 or boundary.get('source') != 'claude-2.1.312-response-boundary-v1'
                or boundary.get('structuralCandidate') is not True or boundary.get('resultId') != identifier
                or boundary.get('inputId') != (self.claim['inputRequestId'] if reported.get('nativeRetry') else boundary.get('stepInputId'))
                or not self.w.input_receipt.is_set()):
            return False
        identity(boundary['inputId']); identity(boundary['stepInputId'])
        if self.progress:
            self.attempt = 0; self.sequence += 1; self.progress = False
        self.failed = native; self.failed_input = boundary['inputId']; self.logical_step = boundary['stepInputId']; self.failure = failure
        if self.attempt >= MAX_ATTEMPTS:
            self.w.error = failure['text'] + ' Automatic continuation stopped after five attempts. Send or Play explicitly to continue.'
            with self.w.store.db: self.write('exhausted')
            return False
        try:
            self.receipts = self.gate()
            runtime = self.goal()
            if runtime:
                value = runtime.journal.read(); self.original_goal = digest(value['contract'])
                self.goal_execution = identity(value['contract']['executionId'])
                if value['steps'][-1]['inputId'] != self.logical_step:
                    raise ProjectFault('The original retry belongs to another logical Goal step.', 409)
            elif self.logical_step != self.w.row['request_id']:
                raise ProjectFault('The ordinary retry has a foreign input identity.', 409)
        except ProjectFault:
            return False
        if self.task and not self.task.done():
            self.task.cancel(); await asyncio.gather(self.task, return_exceptions=True)
        self.ordinal += 1
        self.claim = {'ordinal': self.ordinal, 'holdId': str(uuid.uuid4()), 'stepInputId': self.logical_step,
                      'failedResultId': identifier, 'inputRequestId': str(uuid.uuid4())}
        self.receipt = None; self.admission_id = None; self.echo = asyncio.Event(); self.broker_confirmed = False
        self.deadline = time.monotonic_ns() + DELAY_NS
        if runtime:
            runtime.journal.begin_retry_wait(native, self.budget_claim())
            runtime.clock.end()
        self.w.broker.suspend_admission()
        with self.w.store.db: self.write('waiting', {'kind': 'failure', 'resultId': identifier, 'inputId': self.failed_input})
        self.task = asyncio.create_task(self.wait_and_submit(dict(self.claim)))
        return True

    async def wait_and_submit(self, claim):
        try:
            while not self.w.done.is_set() and not self.closed and self.claim == claim:
                # Poll control/identity only. Large tool outputs are hashed at
                # the failure, claim and admission boundaries, not twice/sec.
                self.gate(with_receipts=False)
                remaining = (self.deadline - time.monotonic_ns()) / 1_000_000_000
                if remaining <= 0: break
                try:
                    await asyncio.wait_for(self.w.done.wait(), min(remaining, .5)); return
                except asyncio.TimeoutError: pass
            if self.w.done.is_set() or self.closed or self.claim != claim:
                return
            runtime = self.goal()
            if runtime and runtime.control:
                async with runtime.control.lock: await self.submit(claim)
            else:
                await self.submit(claim)
            echo = self.echo
            if not echo.is_set():
                waits = [asyncio.create_task(echo.wait()), asyncio.create_task(self.w.done.wait())]
                try:
                    done, _ = await asyncio.wait(waits, timeout=40, return_when=asyncio.FIRST_COMPLETED)
                    if not done and not self.w.done.is_set(): self.unknown()
                finally:
                    for task in waits: task.cancel()
                    await asyncio.gather(*waits, return_exceptions=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            if not self.w.done.is_set():
                if self.state in ('submitting', 'continuing'): self.unknown()
                else: await self.finish_failed('The original retry admission could not be retained.')

    async def submit(self, claim):
        db = self.w.store.db; db.execute('BEGIN IMMEDIATE')
        try:
            if self.state != 'waiting' or self.claim != claim or self.gate() != self.receipts:
                raise ProjectFault('This original retry is no longer waiting.', 409)
            self.attempt += 1; runtime = self.goal()
            if runtime: runtime.journal.record_retry_claim(claim, self.failed_input)
            self.write('submitting', {'kind': 'claim', 'claim': claim})
            db.commit()
        finally:
            if db.in_transaction: db.rollback()
        self.w.admission_started_at = time.time(); self.w.admission_denial = None
        # The original human/logical-step receipt remains confirmed. This
        # physical input has its own echo event and closed broker admission.
        await self.w.command('retry', claim=claim)

    async def admit(self, retry, account, usage):
        valid_claim(retry)
        if self.state != 'submitting' or retry != self.claim or self.gate() != self.receipts:
            return {'allowed': False}
        result = await self.w.admit_native(self.w.broker.binding, account, usage, retry=retry)
        if result.get('allowed') is not True:
            return result
        db = self.w.store.db; db.execute('BEGIN IMMEDIATE')
        try:
            if self.state != 'submitting' or self.claim != retry or self.gate() != self.receipts:
                return {'allowed': False}
            self.admission_id = identity(result['admissionId']); runtime = self.goal()
            if runtime: runtime.journal.record_retry_admission(retry, self.admission_id)
            self.write('submitting', {'kind': 'admission', 'claim': retry, 'admissionId': self.admission_id})
            db.commit()
        finally:
            if db.in_transaction: db.rollback()
        return {**result, 'retry': retry}

    async def confirm_receipt(self, retry):
        valid_claim(retry)
        if retry != self.claim:
            return {'allowed': False}
        try:
            await asyncio.wait_for(self.echo.wait(), 2)
            if self.state != 'continuing' or not self.receipt or not await self.w.current(self.w.broker.binding):
                return {'allowed': False}
            self.gate()
            with self.w.store.db:
                self.broker_confirmed = True
                self.write('continuing', {'kind': 'brokerReady', 'inputId': self.claim['inputRequestId']})
            return {'allowed': True}
        except (asyncio.TimeoutError, ProjectFault):
            return {'allowed': False}

    def submitted(self, frame):
        if (frame.get('requestId') != self.w.row['request_id'] or frame.get('claim') != self.claim
                or frame.get('inputRequestId') != self.claim['inputRequestId']):
            raise ProjectFault('The original retry submission receipt changed.', 409)
        # This is deliberately not a native input receipt, nor a counter reset.

    async def unconfirmed(self, frame):
        if frame.get('operation') != 'retry':
            return False
        if not self.enabled or not self.original:
            raise ProjectFault('This worker has no original retry contract.', 409)
        if (not self.claim or frame.get('claim') != self.claim or frame.get('sourceResultId') != self.failed['uuid']
                or frame.get('inputRequestId') != self.claim['inputRequestId']):
            self.unknown(); return True
        if frame.get('inputSubmitted') is False and not self.receipt:
            runtime = self.goal()
            if runtime: runtime.journal.retry_not_submitted(self.claim)
            await self.finish_failed('Fresh native subscription admission was refused before input submission.')
        else:
            self.unknown()
        return True

    async def finish_failed(self, reason):
        if self.w.done.is_set(): return
        try:
            with self.w.store.db: self.write('cancelled', {'kind': 'held', 'reason': reason})
            await self.settle_failed_result()
        except Exception:
            self.uncertain_start = True
        finally:
            self.w.error = (self.w.admission_denial or {}).get('reason') or self.failure['text'] + ' ' + reason
            self.w.outcome = 'unknown' if self.uncertain_start else 'interrupted' if self.w.stopping else 'failed'
            self.w.done.set()

    async def settle_failed_result(self):
        if self.receipt:
            raise ProjectFault('A confirmed continuation input cannot be closed with its earlier failed result.', 409)
        runtime = self.goal()
        if runtime:
            existing = runtime.journal.read()['steps'][-1]['nativeResult']
            if existing is None:
                await runtime.result(self.failed)
            elif existing['id'] != self.failed['uuid']:
                raise ProjectFault('The original retry failure has another Goal result.', 409)

    def unknown(self):
        self.uncertain_start = True
        try:
            with self.w.store.db: self.write('unknown', {'kind': 'unconfirmedInput', 'claim': self.claim})
        except Exception: pass  # A storage failure must still end this worker.
        finally:
            self.w.error = 'The original Claude continuation is unconfirmed. It was not submitted again.'
            self.w.outcome = 'unknown'; self.w.done.set()

    async def closed_receipt(self, confirmed):
        if not self.enabled or not self.claim or self.receipt:
            return
        value = self.w.native_receipt or {}; retry = value.get('retry') or {}
        known_no_input = (confirmed and not self.w.uncertain_effect and value.get('historyReadable') is True
            and value.get('studioRequestId') == self.w.row['request_id']
            and value.get('nativeSessionId') == self.original['nativeSessionId']
            and retry.get('claim') == self.claim and retry.get('stepInputId') == self.logical_step
            and value.get('inputRequestId') == self.claim['inputRequestId'] and value.get('inputSubmitted') is False
            and value.get('resultId') == self.failed['uuid'] and value.get('resultInputRequestId') == self.failed_input)
        runtime = self.goal()
        if known_no_input:
            self.uncertain_start = False
            if runtime:
                runtime.journal.retry_not_submitted(self.claim)
                value = runtime.journal.read()
                if value['steps'][-1]['nativeResult'] is None: await runtime.result(self.failed)
            with self.w.store.db: self.write('cancelled', {'kind': 'confirmedNoInput', 'claim': self.claim})
            self.w.outcome = 'interrupted' if self.w.stopping else 'failed'
            self.w.error = (self.w.admission_denial or {}).get('reason') or self.failure['text']
        elif self.state == 'submitting' or self.uncertain_start:
            self.uncertain_start = True
            if runtime: runtime.clock.mark_unknown(runtime.journal.spec['executionId'])

    async def cancel(self):
        if self.task and self.task is not asyncio.current_task():
            self.task.cancel(); await asyncio.gather(self.task, return_exceptions=True)
        if self.state == 'waiting':
            await self.finish_failed('Pause or Stop cancelled the original retry wait.')
        elif self.state == 'cancelled' and self.failed:
            await self.settle_failed_result()
        elif self.state == 'submitting' and not self.receipt:
            # Await the original native closure/no-input proof. No second submit.
            with self.w.store.db: self.write('submitting', {'kind': 'controlDuringAdmission', 'claim': self.claim})

    async def close(self):
        if self.task and self.task is not asyncio.current_task():
            self.task.cancel(); await asyncio.gather(self.task, return_exceptions=True)
        try:
            if self.original and self.failed and self.state in ('waiting', 'submitting', 'continuing'):
                terminal = ('unknown' if self.uncertain_start or self.w.outcome == 'unknown'
                            else 'completed' if self.w.outcome == 'completed' else 'cancelled')
                with self.w.store.db:self.write(terminal, {'kind': 'closed', 'outcome': self.w.outcome})
        except Exception:pass  # Final run/history evidence still governs recovery.
        finally:self.closed = True
