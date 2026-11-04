"""One Studio-owned model/tool loop for every direct wire protocol."""
import asyncio
import fcntl
import hashlib
import json
import os
import signal
import uuid

from conversation import Conversation
from model_transport import ModelTransport, ModelFault
from owner import open_lock
from profile import NOTE_TOOLS, ROADMAP_TOOLS
from run_store import get_run, transition, event, item, request_text
from session_store import encode
from store import ProjectFault
from tool_catalog import specifications, tool_scope, validate_arguments
from worker import Worker, reconcile_items


class StudioWorker(Worker):
    def __init__(self, manifest):
        super().__init__(manifest)
        if self.config['engine'].get('kind') != 'studio': raise ValueError('Wrong Studio worker binding.')
        self.conversation = Conversation(self.store, self.session_id)
        self.model = None; self.operation = None; self.credential = None
        self.round = 0

    def declarations(self):
        def allowed(name):
            if name in NOTE_TOOLS:
                from environment_note_tools import require
                try: require(self); return True
                except ProjectFault: return False
            if name in ROADMAP_TOOLS:
                from roadmap_access import require
                try: require(self); return True
                except ProjectFault: return False
            return self.config['permissions'].get('studio.' + name, False)
        return [tool for tool in specifications(tool_scope(self.config)) if allowed(tool['name'][7:])]

    def validate_calls(self, calls, tools):
        names = {tool['name'] for tool in tools}; ids = set()
        for call in calls:
            if call['name'] not in names or call['callId'] in ids: raise ModelFault('model_tool_not_allowed')
            ids.add(call['callId'])
            try: validate_arguments(call['name'][7:], call['arguments'], tool_scope(self.config))
            except ValueError: raise ModelFault('model_invalid_tool_arguments') from None
            previous = self.store.db.execute('SELECT arguments_hash FROM tools WHERE run_id=? AND call_id=?',
                (self.run_id, self.receipt_id(call['callId']))).fetchone()
            expected = hashlib.sha256(encode({'tool':call['name'], 'arguments':call['arguments']}).encode()).hexdigest()
            if previous and previous['arguments_hash'] != expected: raise ModelFault('model_tool_identity_conflict')

    def receipt_id(self, call_id):
        return 'studio-' + hashlib.sha256(encode([self.run_id, call_id]).encode()).hexdigest()

    async def _stop(self):
        self.stopping = True
        if self.operation and not self.operation.done(): self.operation.cancel()
        await super()._stop()

    async def tool_result(self, result, image_data=None):
        # Image bytes remain private/transient. Delivery is added by the common
        # attachment path, never by a protocol-specific tool runner.
        return result

    def active(self):
        row = get_run(self.store, self.run_id)
        return not self.stopping and bool(row['busy']) and row['state'] != 'stopping'

    def validate_lease(self):
        from api_provider_store import ApiProviders
        ApiProviders(self.manifest['providers']).validate_active(self.run_id, self.store.owner_type,
            self.store.owner_id, self.session_id, self.row['request_id'], self.config, self.api_worker)

    def history(self):
        values = []; cursor = 0
        while True:
            page = self.conversation.records(after=cursor, limit=200)
            if not page: return values
            values.extend(page); cursor = page[-1]['sequence']

    async def response(self, instructions, tools):
        self.validate_lease()
        self.round += 1; self.turn_id = 'studio-' + str(uuid.uuid4())
        transition(self.store, self.run_id, 'running', turn_id=self.turn_id)
        ident = 'assistant-' + self.run_id + '-' + str(self.round)
        preview = {'id': ident, 'runId': self.run_id, 'type': 'assistant', 'text': '', 'status': 'running'}
        async def text(delta):
            # The public preview has the existing item bound. The full original
            # belongs in Conversation, independently of UI truncation.
            from terminal import bounded_text
            previous = preview['text']
            preview['text'], clipped = bounded_text(previous + delta, 196608)
            preview['truncated'] = bool(preview.get('truncated') or clipped)
            added = preview['text'][len(previous):]
            if not added: return
            self.store.db.execute('INSERT INTO items VALUES (?,?,?,?) ON CONFLICT(session_id,run_id,item_id) DO UPDATE SET payload=excluded.payload',
                (self.session_id, self.run_id, ident, encode(preview)))
            event(self.store, self.session_id, self.run_id, 'delta', {'itemId': ident, 'text': added})
        self.model = ModelTransport({**self.config['apiProvider'], **self.config.get('apiModel', {}),
            **self.config.get('apiModel', {}).get('messages', {})}, self.config['model'], self.credential,
            chat_policy=self.config.get('apiChat'), client=self.config.get('apiZaiClient'))
        self.turn_requested = True
        self.operation = asyncio.create_task(self.model.response(self.history(), instructions,
            tools, self.config['effort'], on_text=text))
        result = await self.operation
        self.conversation.append(self.run_id, ident, 'assistant', result['content'],
            {**result['origin'], 'usage': result['usage'], 'finishReason': result['finishReason'], 'turnId': self.turn_id})
        full = ''.join(part['text'] for part in result['content'] if part['type'] == 'text')
        from terminal import bounded_text
        preview['text'], clipped = bounded_text(full, 196608)
        preview.update(status='completed', truncated=clipped)
        if full: item(self.store, self.session_id, self.run_id, preview)
        return result

    async def cycle(self):
        from instructions import compose
        instructions = compose(self.config)
        tools = self.declarations()
        while self.active():
            result = await self.response(instructions, tools)
            calls = [part for part in result['content'] if part['type'] == 'tool_call']
            try:
                self.validate_calls(calls, tools)  # Validate the entire set before any host effect.
            except ModelFault as error:
                for index, call in enumerate(calls):
                    self.conversation.append(self.run_id, 'rejected-' + str(self.round) + '-' + str(index), 'tool',
                        [{'type':'tool_result', 'callId':call['callId'], 'result':{'success':False, 'error':'notAdmitted',
                          'output':'This entire tool batch was rejected before host execution.'}}],
                        {'admissionOnly':True, 'reasonCode':error.code, 'turnId':self.turn_id})
                raise
            if not calls:
                if not any(p['type'] == 'text' and p['text'].strip() for p in result['content']):
                    raise ModelFault('model_empty_response')
                self.outcome = 'completed'; return
            # Broker locks serialize workspace effects. Keeping the batch ordered
            # also makes dependent write/read pairs deterministic.
            for call in calls:
                if not self.active(): break
                bound_id = self.receipt_id(call['callId'])
                self.operation = asyncio.create_task(self.bound_tool(call['name'], call['arguments'], bound_id, self.tool_result))
                result = await self.operation
                self.conversation.append(self.run_id, 'tool-' + bound_id + '-' + str(self.round), 'tool',
                    [{'type': 'tool_result', 'callId': call['callId'], 'result': result}],
                    {'toolReceiptId': bound_id, 'turnId': self.turn_id})
                if result.get('error') == 'unknown' or result.get('partialChangesPossible') and result.get('error') == 'interrupted':
                    self.unconfirmed(); break
        self.outcome = 'unknown' if self.uncertain_effect else 'interrupted'

    async def run(self):
        if not self.row['busy']: self.store.close(); return
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(sig, self.defer_stop)
        try:
            if self.row['state'] == 'stopping': self.outcome = 'interrupted'; return
            if self.conversation.metadata() is None:
                raise ProjectFault('This session needs an explicit Studio history migration before direct execution.', 409)
            if self.config.get('goalExecution'):
                raise ProjectFault('Studio Goal execution is not available in this worker release.', 409)
            self.lease = open_lock(self.store.projects, self.store.owner_type, self.store.owner_id)
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            worker = {'release': self.manifest['release'], 'pid': os.getpid(), 'birth': __import__('lease').birth(os.getpid())}
            transition(self.store, self.run_id, 'starting', worker=worker)
            if self.store.owner_type == 'project': await self.build_snapshots.start()
            from api_provider_store import ApiProviders
            self.api_worker = worker
            self.credential = ApiProviders(self.manifest['providers']).claim(self.run_id, self.store.owner_type,
                self.store.owner_id, self.session_id, self.row['request_id'], self.config, worker)
            self.conversation.append(self.run_id, 'user-' + self.row['request_id'], 'user',
                [{'type': 'text', 'text': request_text(self.store, self.run_id)}], {'requestId': self.row['request_id']})
            await self.cycle()
        except asyncio.CancelledError:
            self.outcome = 'unknown' if self.uncertain_effect else 'interrupted'
        except Exception as error:
            self.outcome = 'unknown' if self.uncertain_effect else 'failed'
            self.error = str(error) if isinstance(error, ProjectFault) else 'The Studio worker could not confirm this run. Inspect its original receipts.'
            if isinstance(error, ModelFault):
                event(self.store, self.session_id, self.run_id, 'notice', {'text': self.error, 'providerError': {'code': error.code, 'httpStatusCode': error.http_status}})
        finally:
            try:
                if self.model: await self.model.close()
                await self.cleanup()
                if self.model and not self.model.closed_confirmed: raise ValueError('Unconfirmed model process end')
                from api_provider_store import ApiProviders
                ApiProviders(self.manifest['providers']).release(self.run_id, self.store.owner_type,
                    self.store.owner_id, self.session_id, self.row['request_id'], self.config, self.api_worker)
            except Exception:
                self.outcome = 'unknown'; self.error = self.error or 'The original worker cleanup is unconfirmed. Inspect its retained receipts.'
            finally:
                self.credential = None
                if self.lease: self.lease.close()
                reconcile_items(self.store, self.run_id, self.outcome)
                transition(self.store, self.run_id, self.outcome, self.error, turn_id=self.turn_id)
                self.store.close()
