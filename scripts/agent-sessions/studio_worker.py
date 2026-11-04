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
        from studio_context import StudioContext
        self.context = StudioContext(self)
        from studio_goal import StudioGoal
        self.goal_worker = StudioGoal(self)

    def declarations(self):
        def allowed(name):
            if name == 'get_goal': return True
            if name == 'update_goal': return self.goal_worker.active
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

    async def execute(self,name,arguments,call_id):
        if name in __import__('tool_catalog').GOAL_TOOLS:
            return await self.goal_worker.tool(name,arguments)
        return await super().execute(name,arguments,call_id)

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

    def transport(self):
        return ModelTransport({**self.config['apiProvider'], **self.config.get('apiModel', {}),
            **self.config.get('apiModel', {}).get('messages', {})}, self.config['model'], self.credential,
            chat_policy=self.config.get('apiChat'), client=self.config.get('apiZaiClient'))

    async def infer(self,messages,instructions,tools,on_text=None):
        self.validate_lease()
        if self.goal_worker.execution and not self.goal_worker.active:
            raise GoalHalted()
        self.model = self.transport(); self.turn_requested = True
        request_id = str(uuid.uuid4())
        execution = self.goal_worker.execution if self.goal_worker.active else None
        self.operation = asyncio.create_task(self.model.response(messages,instructions,tools,self.config['effort'],on_text=on_text))
        try:result = await self.operation
        except (asyncio.CancelledError,ModelFault) as error:
            if self.model.attempted and execution and execution == self.goal_worker.execution:self.goal_worker.missing_usage(request_id)
            if isinstance(error,ModelFault) and execution and execution == self.goal_worker.execution:
                await self.goal_worker.pause(status='usageLimited' if error.http_status in (402,429) else 'blocked',reason=str(error))
            raise
        if execution and execution == self.goal_worker.execution:self.goal_worker.observe(result,request_id)
        result['origin']['studioRequestId'] = request_id
        return result

    async def response(self, instructions, tools):
        self.validate_lease()
        active = await self.context.prepare(instructions, tools)
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
        result = await self.infer(active,instructions,tools,on_text=text)
        self.conversation.append(self.run_id, ident, 'assistant', result['content'],
            {**result['origin'], 'usage': result['usage'], 'finishReason': result['finishReason'], 'turnId': self.turn_id})
        self.context.report(instructions, tools)
        full = ''.join(part['text'] for part in result['content'] if part['type'] == 'text')
        from terminal import bounded_text
        preview['text'], clipped = bounded_text(full, 196608)
        preview.update(status='completed', truncated=clipped)
        if full: item(self.store, self.session_id, self.run_id, preview)
        return result

    async def cycle(self):
        from instructions import compose
        instructions = compose(self.config, self.store.project if self.store.owner_type == 'project' else None)
        while self.active():
            await self.goal_worker.boundary()
            if not self.active():
                self.outcome='unknown' if self.uncertain_effect else 'interrupted';return
            if self.goal_worker.execution and not self.goal_worker.active:
                self.outcome='completed';return
            tools = self.declarations()
            result = await self.response(instructions+self.goal_worker.instructions(), tools)
            calls = [part for part in result['content'] if part['type'] == 'tool_call']
            if self.goal_worker.execution and not self.goal_worker.active:
                for index,call in enumerate(calls):
                    self.conversation.append(self.run_id,'goal-not-admitted-'+str(self.round)+'-'+str(index),'tool',
                        [{'type':'tool_result','callId':call['callId'],'result':{'success':False,'error':'notAdmitted','output':'The original Goal budget or control stopped further work before execution.'}}],{'admissionOnly':True,'executionId':self.goal_worker.execution})
                self.outcome='completed';return
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
                await self.goal_worker.boundary()
                if not self.active():
                    self.outcome='unknown' if self.uncertain_effect else 'interrupted';return
                if self.goal_worker.active:
                    self.conversation.append(self.run_id,'goal-continuation-'+str(self.round),'user',
                        [{'type':'text','text':'Continue the explicitly activated Goal. Report complete or blocked with studio_update_goal when justified; preserve unknown effects.'}],
                        {'kind':'goalContinuation','executionId':self.goal_worker.execution,'humanPlayRequestId':self.goal_worker.execution})
                    continue
                self.outcome = 'completed'; return
            # Broker locks serialize workspace effects. Keeping the batch ordered
            # also makes dependent write/read pairs deterministic.
            for index, call in enumerate(calls):
                await self.goal_worker.boundary(allow_play=False)
                if not self.active() or self.goal_worker.execution and not self.goal_worker.active:
                    for offset, remaining in enumerate(calls[index:],index):
                        self.conversation.append(self.run_id,'not-admitted-'+str(self.round)+'-'+str(offset),'tool',
                            [{'type':'tool_result','callId':remaining['callId'],'result':{'success':False,'error':'notAdmitted',
                              'output':'The original run stopped before this tool was admitted.'}}],{'admissionOnly':True})
                    break
                bound_id = self.receipt_id(call['callId'])
                self.operation = asyncio.create_task(self.bound_tool(call['name'], call['arguments'], bound_id, self.tool_result))
                result = await self.operation
                reply = {**result,'studioReceiptId':bound_id}
                self.conversation.append(self.run_id, 'tool-' + bound_id + '-' + str(self.round), 'tool',
                    [{'type': 'tool_result', 'callId': call['callId'], 'result': reply}],
                    {'toolReceiptId': bound_id, 'turnId': self.turn_id})
                if result.get('error') == 'unknown' or result.get('partialChangesPossible') and result.get('error') == 'interrupted':
                    self.unconfirmed()
        self.outcome = 'unknown' if self.uncertain_effect else 'interrupted'

    async def run(self):
        if not self.row['busy']: self.store.close(); return
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(sig, self.defer_stop)
        try:
            if self.row['state'] == 'stopping': self.outcome = 'interrupted'; return
            if self.conversation.metadata() is None:
                raise ProjectFault('This session needs an explicit Studio history migration before direct execution.', 409)
            self.lease = open_lock(self.store.projects, self.store.owner_type, self.store.owner_id)
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            worker = {'release': self.manifest['release'], 'pid': os.getpid(), 'birth': __import__('lease').birth(os.getpid())}
            transition(self.store, self.run_id, 'starting', worker=worker)
            if self.store.owner_type == 'project': await self.build_snapshots.start()
            from api_provider_store import ApiProviders
            self.api_worker = worker
            self.credential = ApiProviders(self.manifest['providers']).claim(self.run_id, self.store.owner_type,
                self.store.owner_id, self.session_id, self.row['request_id'], self.config, worker)
            await self.goal_worker.start()
            human = self.config['goalExecution']['objective'] if self.config.get('goalExecution') else request_text(self.store, self.run_id)
            self.conversation.append(self.run_id, 'user-' + self.row['request_id'], 'user',
                [{'type': 'text', 'text': human}], {'requestId': self.row['request_id'], **({'kind':'humanGoalPlay'} if self.config.get('goalExecution') else {})})
            await self.cycle()
        except GoalHalted:
            self.outcome='unknown' if self.uncertain_effect else 'interrupted' if self.stopping else 'completed'
        except asyncio.CancelledError:
            self.outcome = 'unknown' if self.uncertain_effect else 'interrupted'
            self.context.invalidate('The model operation was interrupted. Original context and receipts are retained.', 'stale')
        except Exception as error:
            self.outcome = 'unknown' if self.uncertain_effect else 'failed'
            self.error = str(error) if isinstance(error, ProjectFault) else 'The Studio worker could not confirm this run. Inspect its original receipts.'
            if isinstance(error, ModelFault):
                event(self.store, self.session_id, self.run_id, 'notice', {'text': self.error, 'providerError': {'code': error.code, 'httpStatusCode': error.http_status}})
            self.context.invalidate('The latest model operation failed. This is retained earlier context.', 'stale')
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
                if self.config.get('goalExecution'):
                    from goal_store import Goals
                    goals=Goals(self.store);rid=self.config['goalExecution']['requestId']
                    if goals.command(self.session_id,rid)['state']=='pending':
                        goals.finish(self.session_id,rid,'unknown' if self.turn_requested else 'failed',self.error or 'The original Goal activation was not confirmed.')
                self.credential = None
                if self.lease: self.lease.close()
                reconcile_items(self.store, self.run_id, self.outcome)
                transition(self.store, self.run_id, self.outcome, self.error, turn_id=self.turn_id)
                self.store.close()


class GoalHalted(Exception):
    pass
