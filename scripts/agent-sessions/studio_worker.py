"""One Studio-owned model/tool loop for every direct wire protocol."""
import asyncio
import fcntl
from http.client import HTTPException
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
        from active_history import ActiveHistory
        self.history_reader = ActiveHistory(self.store, self.session_id)
        self.model = None; self.operation = None; self.credential = None
        self.round = 0
        from model_operations import Operations
        self.operations=Operations(self.store)
        from studio_media import Media
        self.media=Media(self)
        from studio_web import Web
        self.web=Web(self)
        from studio_context import StudioContext
        self.context = StudioContext(self)
        from studio_goal import StudioGoal
        self.goal_worker = self.keepalive_goal or StudioGoal(self)

    def declarations(self):
        def allowed(name):
            if name in __import__('tool_catalog').WEB_TOOLS:return self.config.get('webSearchEnabled',False)
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
        return [tool for tool in specifications(self.config) if allowed(tool['name'][7:])]

    def validate_calls(self, calls, tools, rejected=()):
        names = {tool['name'] for tool in tools}; ids = set()
        previous_effect=False
        for call in calls:
            if call['name'] not in names or call['callId'] in ids: raise ModelFault('model_tool_not_allowed')
            if call['callId'] in rejected:raise ModelFault('model_tool_identity_conflict')
            ids.add(call['callId'])
            previous = self.store.db.execute('SELECT arguments_hash FROM tools WHERE run_id=? AND call_id=?',
                (self.run_id, self.receipt_id(call['callId']))).fetchone()
            expected = hashlib.sha256(encode({'tool':call['name'], 'arguments':call['arguments']}).encode()).hexdigest()
            if previous and previous['arguments_hash'] != expected: raise ModelFault('model_tool_identity_conflict')
            previous_effect=previous_effect or previous is not None
        invalid=[]
        for call in calls:
            try: validate_arguments(call['name'][7:], call['arguments'], tool_scope(self.config))
            except ValueError as error:
                # Only the pure schema validator supplies feedback: no host,
                # provider or tool-execution exception can enter this path.
                invalid.append({'callId':call['callId'],'message':str(error)[:1024]})
        if invalid:
            if previous_effect:raise ModelFault('model_invalid_tool_arguments')
            raise ToolArgumentsFault(invalid[:8])

    def receipt_id(self, call_id):
        return 'studio-' + hashlib.sha256(encode([self.run_id, call_id]).encode()).hexdigest()

    async def _stop(self):
        self.stopping = True
        await self.web.close()
        if self.operation and not self.operation.done(): self.operation.cancel()
        await super()._stop()

    async def tool_result(self, result, image_data=None, call_id=None):
        if not result.get('success') or not call_id:return result
        images=self.skill_mcp.images(result)
        if image_data:
            import base64
            meta=result.get('image')
            if (not isinstance(image_data,dict) or image_data.get('metadata')!=meta or not meta
                    or meta.get('projectId')!=self.manifest.get('projectId') or meta.get('kind')!='screenshot'
                    or hashlib.sha256(base64.b64decode(image_data.get('base64',''),validate=True)).hexdigest()!=meta.get('sha256')):
                raise ProjectFault('The original screenshot reference changed.',409)
            images.append({'data':image_data['base64'],'mimeType':'image/png'})
        declared=result.get('skillMcp',{}).get('imageCount',len(images))
        if not images:return {**result,'imageErrors':['Original service images are retained but unavailable for this image transport.']} if declared else result
        from generated_images import GeneratedImages
        registered=[];errors=[]
        for index,block in enumerate(images):
            try:registered.append(GeneratedImages(self.store,self.session_id).accept_tool(self.run_id,self.thread_id,call_id,index,block))
            except ProjectFault as error:errors.append(str(error))
        value={**result,'images':registered}
        value['imageDelivery']='pixels' if self.config.get('apiModel',{}).get('imageInput')=='supported' else 'reference-only'
        if len(images)<declared:errors.append('Additional original images remain in the retained service result; they were not visually inspected.')
        if errors:value['imageErrors']=errors
        if registered or errors:
            saved=self.store.db.execute('SELECT payload FROM items WHERE run_id=? AND item_id=?',(self.run_id,call_id)).fetchone()
            if saved:
                public=json.loads(saved['payload']);public['generatedImages']=registered;public['imageErrors']=errors
                public['imageDelivery']=value['imageDelivery']
                item(self.store,self.session_id,self.run_id,public)
        return value

    async def execute(self,name,arguments,call_id):
        if name in __import__('tool_catalog').WEB_TOOLS:
            try:return await self.web.call(arguments,call_id)
            except (ProjectFault,OSError,ValueError,HTTPException) as error:
                return {'success':False,'error':'webUnavailable','output':str(error) if isinstance(error,ProjectFault) else 'The original web response could not be confirmed. No alternate service was used.'}
        if name in __import__('tool_catalog').GOAL_TOOLS:
            return await self.goal_worker.tool(name,arguments)
        result=await super().execute(name,arguments,call_id)
        reference=result.get('skillMcp',{})
        if reference.get('imageCount'):
            entry=self.skill_mcp.entry(reference['skillId']);_,raw=self.skill_mcp.retained(entry,reference['reference'])
            original=json.loads(raw)
            text='\n'.join(p['text'] for p in original.get('content',[]) if isinstance(p,dict) and p.get('type')=='text' and isinstance(p.get('text'),str))
            from terminal import bounded_text
            preview,clipped=bounded_text(text,8192)
            result['output']=encode({'kind':'untrusted_tool_media','originalResultReference':reference['reference'],
                'imageCount':reference['imageCount'],'textPreview':preview,'textTruncated':clipped,'fullOriginalRetained':True})
        return result

    async def cleanup(self):
        await self.web.close()
        await super().cleanup()

    def active(self):
        row = get_run(self.store, self.run_id)
        return not self.stopping and bool(row['busy']) and row['state'] != 'stopping'

    def validate_lease(self):
        from api_provider_store import ApiProviders
        ApiProviders(self.manifest['providers']).validate_active(self.run_id, self.store.owner_type,
            self.store.owner_id, self.session_id, self.row['request_id'], self.config, self.api_worker)

    def active_history(self):
        # Accepted records/configs are immutable. Recovery gets a new reader;
        # any changed current route or credential discards worker-local reuse.
        scope = encode([self.config, hashlib.sha256((self.credential or '').encode()).hexdigest()])
        return self.history_reader.read(scope)

    def transport(self):
        scope = encode([self.config, self.credential, getattr(self,'model_headers',None)])
        if getattr(self,'transport_scope',None) == scope:
            return self.prepared_transport
        model=ModelTransport({**self.config['apiProvider'], **self.config.get('apiModel', {}),
            **self.config.get('apiModel', {}).get('messages', {})}, self.config['model'], self.credential,
            headers=getattr(self,'model_headers',None), chat_policy=self.config.get('apiChat'), client=self.config.get('apiZaiClient'))
        model.media_resolver=self.media.resolve
        self.transport_scope=scope;self.prepared_transport=model
        return model

    async def infer(self,messages,instructions,tools,on_text=None):
        while True:
            try:return await self.infer_once(messages,instructions,tools,on_text)
            except ModelFault as error:
                if not await self.provider_retry.direct(error):raise

    async def infer_once(self,messages,instructions,tools,on_text=None):
        self.validate_lease()
        if self.config['apiProvider']['kind']=='codex-subscription':
            from native_openai import access
            original=await asyncio.to_thread(access,self.manifest['providers'],self.config['apiProvider']['id'],self.config['apiNativeAccount'])
            self.credential=original['key'];self.model_headers=original['extraHeaders']
            self.validate_lease()
            if not self.active():raise asyncio.CancelledError()
        if self.config['apiProvider']['kind']=='chatgpt-plan':
            from chatgpt_plan import Plan
            self.credential=await asyncio.to_thread(Plan(self.manifest['providers']).credential,self.config['apiProvider'],self.config['apiPlanGrant'])
            self.validate_lease()
            if not self.active():raise asyncio.CancelledError()
        if self.config['apiProvider']['kind']=='claude-plan':
            from claude_plan import ClaudePlan
            plan=ClaudePlan(self.manifest['providers'])
            try:await asyncio.to_thread(plan.require_included,self.config['apiProvider'])
            except ProjectFault:raise ModelFault('claude_subscription_unavailable',429,not_dispatched=True) from None
            self.credential=await asyncio.to_thread(plan.credential,self.config['apiProvider'],self.config['apiClaudeGrant'])
            self.validate_lease()
            if not self.active():raise asyncio.CancelledError()
        if self.config['apiProvider']['kind']=='zai-coding-plan':
            from zai_limits import state
            if state(self.manifest['providers'],self.config['apiProvider'],self.config['model']):
                await self.goal_worker.pause(status='usageLimited',reason='The original subscription has a retained native limit. Review its actual account state.')
                raise ModelFault('zai_subscription_exhausted',429,not_dispatched=True)
        if self.goal_worker.execution and not self.goal_worker.active:
            raise GoalHalted()
        self.model = self.transport(); self.turn_requested = True
        request_id = str(uuid.uuid4())
        self.operations.begin(self.run_id,request_id)
        self.model.process_observer=lambda stage,child:self.operations.process(request_id,stage,child,request_sha256=self.model.request_sha256)
        self.model.event_observer=lambda raw:self.operations.wire(request_id,raw)
        self.model.flush_observer=lambda:self.operations.flush(request_id)
        self.model.flush_delay=lambda:self.operations.flush_delay(request_id)
        execution = self.goal_worker.execution if self.goal_worker.active else None
        self.operation = asyncio.create_task(self.model.response(messages,instructions,tools,self.config['effort'],on_text=on_text))
        try:result = await self.operation
        except (asyncio.CancelledError,ProjectFault) as error:
            unsent=isinstance(error,ModelFault) and error.not_dispatched
            if isinstance(error,ModelFault):self.observe_limit(error)
            self.operations.finish(request_id,error=error,attempted=self.model.attempted and not unsent)
            if self.model.attempted and not unsent and execution and execution == self.goal_worker.execution:self.goal_worker.missing_usage(request_id)
            if isinstance(error,ModelFault) and execution and execution == self.goal_worker.execution:
                if not unsent:await self.goal_worker.pause(status='usageLimited' if error.category in ('billing','rate','quota') else 'blocked',reason=str(error))
            raise
        self.operations.finish(request_id,result=result,attempted=self.model.attempted)
        self.provider_retry.direct_complete()
        if execution and execution == self.goal_worker.execution:self.goal_worker.observe(result,request_id)
        result['origin']['studioRequestId'] = request_id
        return result

    def observe_limit(self,error):
        if self.config['apiProvider']['kind']!='zai-coding-plan' or not error.details:return
        try:
            import base64
            raw=json.loads(base64.b64decode(error.details.get('providerBodyBase64','')))
            if not isinstance(raw,dict):return
            nested=raw.get('error');code=nested.get('code',raw.get('code')) if isinstance(nested,dict) else raw.get('code')
            from zai_limits import REASONS,observe
            if str(code) not in REASONS:return
            error.category='quota' if str(code) in ('1308','1310','1316','1317','1320','1321') else 'access'
            error.args=(REASONS[str(code)],)
            ordinal=self.store.db.execute('SELECT COUNT(*) FROM studio_model_calls WHERE run_id=?',(self.run_id,)).fetchone()[0]
            observe(self.manifest['providers'],self.config['apiProvider'],self.config['model'],self.run_id,
                {'code':str(code),'ordinal':ordinal,'resetAt':None,'httpStatus':error.http_status})
        except (ValueError,TypeError,KeyError,ProjectFault):pass

    async def response(self, instructions, tools):
        self.validate_lease()
        active = await self.context.prepare(instructions, tools)
        self.round += 1; self.turn_id = 'studio-' + str(uuid.uuid4())
        transition(self.store, self.run_id, 'running', turn_id=self.turn_id)
        ident = 'assistant-' + self.run_id + '-' + str(self.round)
        preview = {'id': ident, 'runId': self.run_id, 'type': 'assistant', 'text': '', 'status': 'running'}
        announced = False
        async def text(delta):
            nonlocal announced
            # Announce the stable projection before its first delta. Textless
            # tool turns need no empty message, and readers see live answers.
            if not announced and delta:
                item(self.store, self.session_id, self.run_id, preview)
                announced = True
            # The public preview has the existing item bound. The full original
            # belongs in Conversation, independently of UI truncation.
            from terminal import bounded_text
            previous = preview['text']
            preview['text'], clipped = bounded_text(previous + delta, 196608)
            preview['truncated'] = bool(preview.get('truncated') or clipped)
            added = preview['text'][len(previous):]
            if not added: return
            from public_stream import delta as public_delta
            public_delta(self.store, self.session_id, self.run_id, preview, {'itemId': ident, 'text': added})
        try:
            result = await self.infer(active,instructions,tools,on_text=text)
        finally:
            from public_stream import flush
            flush(self.store)
        self.conversation.append(self.run_id, ident, 'assistant', result['content'],
            {**result['origin'], 'usage': result['usage'], 'finishReason': result['finishReason'], 'turnId': self.turn_id})
        self.context.report(instructions, tools)
        full = ''.join(part['text'] for part in result['content'] if part['type'] == 'text')
        from terminal import bounded_text
        preview['text'], clipped = bounded_text(full, 196608)
        preview.update(status='completed', truncated=clipped)
        if full or announced: item(self.store, self.session_id, self.run_id, preview)
        return result

    async def cycle(self):
        from instructions import compose
        instructions = compose(self.config, self.store.project if self.store.owner_type == 'project' else None)
        correction_used=False; rejected=set()
        while self.active():
            await self.goal_worker.boundary(allow_play=False)
            if self.active() and (not self.goal_worker.execution or self.goal_worker.active):self.message_worker.boundary()
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
                self.validate_calls(calls, tools, rejected)  # Validate the entire set before any host effect.
            except ModelFault as error:
                correctable=isinstance(error,ToolArgumentsFault) and not correction_used and not self.uncertain_effect
                for index, call in enumerate(calls):
                    feedback={'success':False,'error':'notAdmitted','output':'This entire tool batch was rejected before host execution.'}
                    if isinstance(error,ToolArgumentsFault):
                        feedback['validation']={'code':'invalidArguments','errors':error.details,'correctionAvailable':correctable}
                        feedback['output']+=(' Correct the schema errors using the declared fields and original target IDs, then issue fresh tool calls. No call in this batch ran.'
                            if correctable else ' The single argument-correction opportunity is unavailable; this run ends.')
                    self.conversation.append(self.run_id, 'rejected-' + str(self.round) + '-' + str(index), 'tool',
                        [{'type':'tool_result', 'callId':call['callId'], 'result':feedback}],
                        {'admissionOnly':True, 'reasonCode':error.code, 'turnId':self.turn_id})
                if correctable:
                    correction_used=True;rejected.update(call['callId'] for call in calls)
                    continue
                raise
            if not calls:
                if not any(p['type'] == 'text' and p['text'].strip() for p in result['content']):
                    raise ModelFault('model_empty_response')
                await self.goal_worker.boundary(allow_play=False)
                if not self.active():
                    self.outcome='unknown' if self.uncertain_effect else 'interrupted';return
                if self.message_worker.messages.waiting_after(self.session_id,self.run_id):
                    if self.goal_worker.active and not self.config.get('goalKeepalive'):await self.goal_worker.pause(reason='The original answer ended. Explicit after-response input continues through the saved queue.')
                    self.outcome='completed';return
                if self.message_worker.boundary():
                    # A human input authorizes another ordinary model call. A
                    # completed Goal stays completed; limits never reach here.
                    if self.goal_worker.execution and not self.goal_worker.active:
                        self.goal_worker.execution=None;self.goal_worker.dormant=True
                    continue
                await self.goal_worker.boundary()
                if self.goal_worker.active and not self.config.get('goalKeepalive'):
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
                from functools import partial
                self.operation = asyncio.create_task(self.bound_tool(call['name'], call['arguments'], bound_id, partial(self.tool_result,call_id=bound_id)))
                result = await self.operation
                reply = {**result,'studioReceiptId':bound_id}
                media=[{'type':'image','reference':value['presentation']['reference']} for value in result.get('images',[])] if self.config.get('apiModel',{}).get('imageInput')=='supported' else []
                self.conversation.append(self.run_id, 'tool-' + bound_id + '-' + str(self.round), 'tool',
                    [{'type': 'tool_result', 'callId': call['callId'], 'result': reply},*media],
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
            from model_operations import worker_identity
            transition(self.store, self.run_id, 'starting', worker=worker|worker_identity())
            if self.store.owner_type == 'project': await self.build_snapshots.start()
            from api_provider_store import ApiProviders
            self.api_worker = worker
            self.credential = ApiProviders(self.manifest['providers']).claim(self.run_id, self.store.owner_type,
                self.store.owner_id, self.session_id, self.row['request_id'], self.config, worker)
            await self.goal_worker.start()
            from message_worker import MessageWorker
            self.message_worker=MessageWorker(self);await self.message_worker.start()
            worker=json.loads(get_run(self.store,self.run_id)['worker']);worker.update(messageProtocol=1,messageTurnActive=True)
            transition(self.store,self.run_id,'starting',worker=worker)
            human = self.config['goalExecution']['objective'] if self.config.get('goalExecution') else request_text(self.store, self.run_id)
            from studio_media import user_content
            self.conversation.append(self.run_id, 'user-' + self.row['request_id'], 'user',
                user_content(self.config,human), {'requestId': self.row['request_id'], **({'kind':'humanGoalPlay'} if self.config.get('goalExecution') else {})})
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
                event(self.store, self.session_id, self.run_id, 'notice', {'text': self.error, 'providerError': {'code': error.code, 'httpStatusCode': error.http_status,'category':error.category}})
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
                if not self.config.get('goalKeepalive') and self.message_worker and self.goal_worker.execution and self.goal_worker.current() and self.goal_worker.current()['status'] in ('budgetLimited','usageLimited','blocked'):
                    self.message_worker.messages.hold(self.session_id,'The original Goal reached a limit or blockade. Review its receipt, then continue the queue explicitly.')
                try:
                    from studio_usage import scan
                    from stats_store import Source
                    scan(self.store,self.session_id);Source(self.store).flush()
                except Exception:pass  # Original calls remain available for the existing numeric reconciliation.
                self.store.close()


class GoalHalted(Exception):
    pass


class ToolArgumentsFault(ModelFault):
    def __init__(self,errors):
        super().__init__('model_invalid_tool_arguments',details=errors)
        self.args=('The tool batch failed argument validation before execution. The single correction opportunity is exhausted or unavailable.',)
