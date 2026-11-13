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
from context_policy import optimized
from model_transport import ModelTransport, ModelFault
from owner import open_lock
from profile import NOTE_TOOLS, ROADMAP_TOOLS
from run_store import get_run, transition, event, item, request_text
from session_store import encode
from store import ProjectFault
from tool_catalog import automatic_file_writes, declarations, tool_scope, validate_arguments
from worker import Worker, reconcile_items


class StudioWorker(Worker):
    def __init__(self, manifest):
        super().__init__(manifest)
        if self.config['engine'].get('kind') != 'studio': raise ValueError('Wrong Studio worker binding.')
        self.conversation = Conversation(self.store, self.session_id)
        from active_history import ActiveHistory
        self.history_reader = ActiveHistory(self.store, self.session_id)
        from context_results import Projection
        self.context_results=Projection(self)
        self.measured_input = None
        if optimized(self.config.get('contextPolicy'), 12):
            from measured_input import MeasuredInput
            self.measured_input = MeasuredInput(self.store, self.session_id)
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
        if not hasattr(self,'_tool_declarations'): self._tool_declarations=declarations(self.config)
        if self.config.get('toolCatalog',{}).get('version')==2: return self._tool_declarations
        def allowed(name):
            if name in __import__('tool_catalog').WEB_TOOLS:return self.config.get('webSearchEnabled',False)
            if name == 'generate_image': return self.config.get('imageGenerationEnabled',False) and self.config['permissions'].get('studio.generate_image',False) and self.config.get('imageGenerationTarget',{}).get('available',False)
            if name == 'get_goal': return True
            if name == 'update_goal': return self.goal_worker.active
            if name in NOTE_TOOLS:
                from environment_note_tools import declared
                return declared(self)
            if name in ROADMAP_TOOLS:
                from roadmap_access import require
                try: require(self); return True
                except ProjectFault: return False
            return self.config['permissions'].get('studio.' + name, False)
        return [tool for tool in self._tool_declarations if allowed(tool['name'][7:])]

    def validate_calls(self, calls, tools, rejected=()):
        from tool_receipt_boundary import fingerprint, original_hash
        names = {tool['name'] for tool in tools}; ids = set()
        previous_effect=False
        for call in calls:
            if call['name'] not in names or call['callId'] in ids: raise ModelFault('model_tool_not_allowed')
            if call['callId'] in rejected:raise ModelFault('model_tool_identity_conflict')
            ids.add(call['callId'])
            previous = self.store.db.execute('SELECT run_id,call_id,arguments_hash FROM tools WHERE run_id=? AND call_id=?',
                (self.run_id, self.receipt_id(call['callId']))).fetchone()
            expected = fingerprint(call['name'],call['arguments'])
            if previous and original_hash(self.store,previous) != expected: raise ModelFault('model_tool_identity_conflict')
            previous_effect=previous_effect or previous is not None
        invalid=[]
        for call in calls:
            try: validate_arguments(call['name'][7:], call['arguments'], self.config)
            except ValueError as error:
                # Only the pure schema validator supplies feedback: no host,
                # provider or tool-execution exception can enter this path.
                invalid.append({'callId':call['callId'],'tool':call['name'],'message':str(error)[:1024]})
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
        screenshot=None;registered=[];errors=[]
        meta=result.get('image')
        media_type=result.get('screenshotMediaType','image/png')
        if meta and meta.get('preview',{}).get('error') and result.get('imageDelivery')=='reference-only':return result
        if image_data:
            import base64
            if (not isinstance(image_data,dict) or image_data.get('metadata')!=meta or not meta
                    or meta.get('projectId')!=self.manifest.get('projectId') or meta.get('kind')!='screenshot'
                    or image_data.get('mediaType','image/png')!=media_type):
                raise ProjectFault('The original screenshot reference changed.',409)
            raw=base64.b64decode(image_data.get('base64',''),validate=True)
            if media_type=='image/webp':
                from screenshot_media import check_webp
                try: check_webp(raw,meta['preview'])
                except (ValueError,KeyError): raise ProjectFault('The saved screenshot WebP changed.',409) from None
            elif hashlib.sha256(raw).hexdigest()!=meta.get('sha256'):
                raise ProjectFault('The original screenshot reference changed.',409)
            if result.get('imageDelivery')=='reference-only' and self.config.get('apiModel',{}).get('imageInput')!='supported':
                return result
        if result.get('image'):
            if self.config.get('apiModel',{}).get('imageInput')!='supported':return result
            from screenshot_media import read,reference
            try:
                screenshot=reference(result['image'],media_type)
                read(self.store,self.session_id,screenshot,expected=result['image'])
            except (ProjectFault,KeyError,ValueError,TypeError) as error:
                screenshot=None;errors.append(str(error))
        from generated_images import GeneratedImages
        if result.get('generatedImage'):
            original=GeneratedImages(self.store,self.session_id)
            meta=original.get(result['generatedImage']['id']);original.path(meta['id'])
            if meta!=result['generatedImage']:raise ProjectFault('The original generated image receipt changed.',409)
            registered.append(meta)
        declared=result.get('skillMcp',{}).get('imageCount',len(images))
        if not images and not registered and not result.get('image'):
            return {**result,'imageErrors':['Original service images are retained but unavailable for this image transport.'],'imageDelivery':'reference-only'} if declared else result
        for index,block in enumerate(images):
            try:registered.append(GeneratedImages(self.store,self.session_id).accept_tool(self.run_id,self.thread_id or 'studio-'+self.session_id,call_id,index,block))
            except ProjectFault as error:errors.append(str(error))
        value={**result,'images':registered}
        if screenshot:value['screenshotReference']=screenshot
        value['imageDelivery']='pixels' if (registered or screenshot) and self.config.get('apiModel',{}).get('imageInput')=='supported' else 'reference-only'
        if len(images)<declared:errors.append('Additional original images remain in the retained service result; they were not visually inspected.')
        if errors:value['imageErrors']=errors
        if result.get('image') and not screenshot:
            if value.get('visionAnalysis',{}).get('state')=='native':
                value['visionAnalysis']={**value['visionAnalysis'],'state':'unavailable','reason':'The original screenshot was retained, but its pixels could not be delivered. No frame was captured again.'}
            payload=json.loads(result['output'])
            payload.update(imageDelivery=value['imageDelivery'])
            if value.get('visionAnalysis'):payload['visionAnalysis']=value['visionAnalysis']
            value['output']=encode(payload)
        if registered or screenshot or errors:
            saved=self.store.db.execute('SELECT payload FROM items WHERE run_id=? AND item_id=?',(self.run_id,call_id)).fetchone()
            if saved:
                public=json.loads(saved['payload']);public['generatedImages']=registered;public['imageErrors']=errors
                public['imageDelivery']=value['imageDelivery']
                if screenshot:public['screenshotReference']=screenshot
                if value.get('visionAnalysis'):public['visionAnalysis']=value['visionAnalysis']
                if result.get('image') and not screenshot:public['output']=value['output']
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
        history = self.history_reader.read(scope)
        if self.measured_input:
            self.measured_input.select(history[1])
        return self.context_results.project(*history)

    def transport(self, *, summary=None):
        scope = encode([self.config, self.credential, getattr(self,'model_headers',None), summary])
        scope_attr,transport_attr=('summary_scope','summary_transport') if summary else ('transport_scope','prepared_transport')
        if getattr(self,scope_attr,None) == scope:
            return getattr(self,transport_attr)
        chat_policy = self.config.get('apiChat')
        if summary and chat_policy and 'selectedEffort' in chat_policy:
            chat_policy = {**chat_policy, 'selectedEffort': summary['effort']}
        model=ModelTransport({**self.config['apiProvider'], **self.config.get('apiModel', {}),
            **self.config.get('apiModel', {}).get('messages', {})}, self.config['model'], self.credential,
            headers=getattr(self,'model_headers',None), chat_policy=chat_policy, client=self.config.get('apiZaiClient'),
            prompt_cache_key=self.config.get('promptCacheKey'))
        model.media_resolver=self.media.resolve
        model.context_policy=self.config.get('contextPolicy')
        model.measured_input=self.measured_input if summary is None else None
        model.summary_budget=summary
        if optimized(model.context_policy, 1) and model.binding['protocol']=='messages':
            from instructions import TOOL_EXECUTION
            from signed_history import Prefix, can_restart_messages, instruction_sources
            guidance = TOOL_EXECUTION if self.config.get('toolDeadlines', {}).get('version') == 1 else None
            changed = optimized(model.context_policy,14) and can_restart_messages(self.config)
            sources = instruction_sources(self.config) if changed else None
            model.signed_prefix=Prefix(self.store,self.session_id,model.binding,guidance,current_sources=sources)
        model.count_observer=lambda receipt:event(self.store,self.session_id,self.run_id,'inputCount',receipt)
        from studio_history import recoveries
        model.history_resolver=lambda messages:recoveries(self.store,self.session_id,messages)
        setattr(self,scope_attr,scope);setattr(self,transport_attr,model)
        return model

    async def infer(self,messages,instructions,tools,on_text=None):
        expected_sha256 = None
        original_rejection = None
        while True:
            try:
                return await self.infer_once(messages, instructions, tools, on_text,
                    expected_sha256=expected_sha256,
                    parser_restart_of=original_rejection.rejected_request_id if original_rejection else None)
            except ModelFault as error:
                rejected = getattr(error, 'rejected_request_id', None)
                if rejected and original_rejection is None:
                    await self.goal_worker.boundary(allow_play=False)
                    if not self.active():
                        raise asyncio.CancelledError() from None
                    if not self.goal_worker.execution or self.goal_worker.can_restart_model():
                        original_rejection = error
                        expected_sha256 = self.model.request_sha256
                        continue
                if original_rejection is None and await self.provider_retry.direct(error):
                    expected_sha256 = self.model.request_sha256
                    continue
                if self.stopping: raise asyncio.CancelledError() from None
                execution = getattr(error,'retry_goal_execution',None)
                if execution and execution == self.goal_worker.execution:
                    await self.goal_worker.pause(status='blocked',reason=str(error))
                if original_rejection and error.not_dispatched and error.code in ('model_retry_input_changed', 'model_restart_goal_unavailable'):
                    cause = ('The confirmed input changed' if error.code == 'model_retry_input_changed'
                             else 'The Goal could no longer continue')
                    original_rejection.args = (f'{original_rejection} {cause} before restart.',)
                    raise original_rejection from None
                if original_rejection and not getattr(error, 'parser_failure', None):
                    error.args = (f'Model restart failed. {error} First response. {original_rejection.reason}',)
                raise

    def confirmed_parser_rejection(self, request_id, error):
        if not getattr(error, 'parser_failure', None) or not self.model.closed_confirmed:
            return False
        row, value = self.operations.row(request_id)
        stream = value.get('stream', {})
        status = stream.get('httpStatus')
        # Parsing ends before any tool admission. The conversation only records
        # a model reply after infer has returned a confirmed result.
        return (row['run_id'] == self.run_id and row['phase'] == 'unknown' and value.get('attempted') is True
                and value['sessionId'] == self.session_id and value['purpose'] == 'conversation'
                and row['request_id'] == request_id and value.get('error', {}).get('code') == error.code
                and value.get('requestSha256') == self.model.request_sha256
                and value.get('processEnd', {}).get('confirmed') is True
                and value['processEnd'].get('exitCode') == 0 and type(status) is int and 200 <= status < 300
                and stream.get('httpComplete') is True and stream.get('terminalReceived') is True
                and stream.get('incompleteEvent') is False)

    async def infer_once(self,messages,instructions,tools,on_text=None,*,expected_sha256=None,parser_restart_of=None):
        if not self.active():raise asyncio.CancelledError()
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
            except ProjectFault:
                error=ModelFault('claude_subscription_unavailable',429,not_dispatched=True)
                self.quota_rejected(error)
                raise error from None
            self.credential=await asyncio.to_thread(plan.credential,self.config['apiProvider'],self.config['apiClaudeGrant'])
            self.validate_lease()
            if not self.active():raise asyncio.CancelledError()
        if self.config['apiProvider']['kind']=='zai-coding-plan':
            from zai_limits import state
            if state(self.manifest['providers'],self.config['apiProvider'],self.config['model']):
                error=ModelFault('zai_subscription_exhausted',429,not_dispatched=True)
                if not self.quota_rejected(error):await self.goal_worker.pause(status='usageLimited',reason='The original subscription has a retained native limit. Review its actual account state.')
                raise error
        if self.goal_worker.execution and not self.goal_worker.active:
            raise GoalHalted()
        summary=getattr(self,'request_summary_budget',None)
        self.model = self.transport(summary=summary) if summary else self.transport()
        self.turn_requested = True
        request_id = str(uuid.uuid4())
        purpose = getattr(self, 'request_purpose', 'conversation')
        self.operations.begin(self.run_id, request_id, purpose=purpose, summary_budget=summary, parser_restart_of=parser_restart_of)
        self.operations.observe(self.model,request_id,projection=self.context_results.provenance if not summary else None)
        execution = self.goal_worker.execution if self.goal_worker.active else None

        async def restart_guard():
            await self.goal_worker.boundary(allow_play=False)
            if not self.active():
                raise asyncio.CancelledError()
            self.validate_lease()
            if (self.uncertain_effect or execution != self.goal_worker.execution
                    or execution and not self.goal_worker.can_restart_model()):
                raise ModelFault('model_restart_goal_unavailable', not_dispatched=True)

        self.model.dispatch_guard = restart_guard if parser_restart_of else None
        effort = summary['effort'] if summary else self.config['effort']
        self.operation = asyncio.create_task(self.model.response(messages, instructions, tools, effort,
            on_text=on_text, expected_sha256=expected_sha256, conversation=purpose == 'conversation'))
        try:result = await self.operation
        except (asyncio.CancelledError,ProjectFault) as error:
            unsent=isinstance(error,ModelFault) and error.not_dispatched
            if isinstance(error,ModelFault):self.observe_limit(error)
            from quota_wait import evidence,snapshot_evidence,register
            proof=evidence(self.config,error) or snapshot_evidence(self.config,error,self.manifest['providers'])
            if proof:error.quota_evidence=proof
            self.operations.finish(request_id,error=error,attempted=self.model.attempted and not unsent)
            waiting=register(self,request_id,proof) if proof else None
            retryable = isinstance(error,ModelFault) and (error.confirmed_overload or error.stream_interrupted) and not waiting
            if retryable: error.retry_operation_id=request_id
            rejected = not waiting and StudioWorker.confirmed_parser_rejection(self, request_id, error)
            if self.model.attempted and not unsent and execution and execution == self.goal_worker.execution:
                usage = (getattr(error, 'partial', None) or {}).get('usage') if rejected else None
                if usage is None:
                    self.goal_worker.missing_usage(request_id)
                else:
                    self.goal_worker.observe({'usage': usage}, request_id)
            if (rejected and not parser_restart_of and self.model.stream_progress['visibleOutput'] is False
                    and not self.uncertain_effect and self.active()
                    and (not execution or self.goal_worker.can_restart_model())):
                error.rejected_request_id = request_id
            if isinstance(error,ModelFault) and execution and execution == self.goal_worker.execution:
                if not unsent and not waiting and not getattr(error, 'rejected_request_id', None):
                    if retryable:error.retry_goal_execution=execution
                    else:await self.goal_worker.pause(status='usageLimited' if error.category in ('billing','rate','quota') else 'blocked',reason=str(error))
            raise
        self.operations.finish(request_id,result=result,attempted=self.model.attempted)
        self.provider_retry.direct_complete()
        if execution and execution == self.goal_worker.execution:self.goal_worker.observe(result,request_id)
        result['origin']['studioRequestId'] = request_id
        return result

    def quota_rejected(self,error):
        from quota_wait import snapshot_evidence,register
        proof=snapshot_evidence(self.config,error,self.manifest['providers'])
        if not proof:return False
        request_id=str(uuid.uuid4());error.quota_evidence=proof
        self.operations.begin(self.run_id,request_id,purpose=getattr(self,'request_purpose','conversation'));self.operations.finish(request_id,error=error,attempted=False)
        return bool(register(self,request_id,proof))

    def observe_limit(self,error):
        if self.config['apiProvider']['kind']!='zai-coding-plan' or not error.details:return
        try:
            import base64
            raw=json.loads(base64.b64decode(error.details.get('providerBodyBase64','')))
            if not isinstance(raw,dict):return
            nested=raw.get('error');code=nested.get('code',raw.get('code')) if isinstance(nested,dict) else raw.get('code')
            from zai_limits import REASONS,observe
            if str(code) not in REASONS:return
            error.category='quota' if str(code) in ('1308','1310','1316','1317','1318','1319','1320','1321') else 'access'
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
        from text_budget import TextBuffer
        budget = TextBuffer(196608)
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
            added, clipped = budget.append(delta)
            preview['text'] = budget.value
            preview['truncated'] = bool(preview.get('truncated') or clipped)
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
        final_tool_results = self.config.get('toolDeadlines', {}).get('version') == 1
        correction_attempts=0; rejected=set()
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
                    self.conversation.append(self.run_id,'goal-not-admitted-'+self.run_id+'-'+str(self.round)+'-'+str(index),'tool',
                        [{'type':'tool_result','callId':call['callId'],'result':{'success':False,'error':'notAdmitted','output':'The original Goal budget or control stopped further work before execution.'}}],{'admissionOnly':True,'executionId':self.goal_worker.execution})
                self.outcome='completed';return
            try:
                self.validate_calls(calls, tools, rejected)  # Validate the entire set before any host effect.
            except ModelFault as error:
                correctable=isinstance(error,ToolArgumentsFault) and correction_attempts<5 and not self.uncertain_effect
                errors = {entry['callId']: entry['message'] for entry in error.details} if isinstance(error, ToolArgumentsFault) else {}
                for index, call in enumerate(calls):
                    feedback={'success':False,'error':'notAdmitted','output':'This entire tool batch was rejected before host execution.'}
                    if isinstance(error,ToolArgumentsFault):
                        feedback['validation']={'code':'invalidArguments','errors':error.details,'correctionAvailable':correctable}
                        if call['callId'] in errors:
                            feedback['output'] += ' ' + call['name'] + ': ' + errors[call['callId']]
                        feedback['output']+=(' Correct the schema errors using the declared fields and original target IDs, then issue fresh tool calls. No call in this batch ran.'
                            if correctable else ' No further correction is available before a successful tool batch or while earlier effects are unconfirmed; this run ends.')
                    self.conversation.append(self.run_id, 'rejected-' + self.run_id + '-' + str(self.round) + '-' + str(index), 'tool',
                        [{'type':'tool_result', 'callId':call['callId'], 'result':feedback}],
                        {'admissionOnly':True, 'reasonCode':error.code, 'turnId':self.turn_id})
                if correctable:
                    correction_attempts+=1;rejected.update(call['callId'] for call in calls)
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
                    self.conversation.append(self.run_id,'goal-continuation-'+self.run_id+'-'+str(self.round),'user',
                        [{'type':'text','text':'Continue the explicitly activated Goal. Report complete or blocked with studio_update_goal when justified; preserve unknown effects.'}],
                        {'kind':'goalContinuation','executionId':self.goal_worker.execution,'humanPlayRequestId':self.goal_worker.execution})
                    continue
                self.outcome = 'completed'; return
            # Broker locks serialize workspace effects. Keeping the batch ordered
            # also makes dependent write/read pairs deterministic.
            batch_succeeded=True
            file_preconditions = automatic_file_writes(self.config)
            if file_preconditions:
                # The model will only receive this batch's results together.
                self.workspace_tools.file_batch = self.workspace_tools.file_versions.copy()
            for index, call in enumerate(calls):
                await self.goal_worker.boundary(allow_play=False)
                if not self.active() or self.goal_worker.execution and not self.goal_worker.active:
                    for offset, remaining in enumerate(calls[index:],index):
                        self.conversation.append(self.run_id,'not-admitted-'+self.run_id+'-'+str(self.round)+'-'+str(offset),'tool',
                            [{'type':'tool_result','callId':remaining['callId'],'result':{'success':False,'error':'notAdmitted',
                              'output':'The original run stopped before this tool was admitted.'}}],{'admissionOnly':True})
                    batch_succeeded=False;break
                bound_id = self.receipt_id(call['callId'])
                from functools import partial
                self.operation = asyncio.create_task(self.bound_tool(call['name'], call['arguments'], bound_id, partial(self.tool_result,call_id=bound_id)))
                result = await self.operation
                if result.get('success') is not True or result.get('partialChangesPossible'):batch_succeeded=False
                reply = {**result,'studioReceiptId':bound_id}
                media=[{'type':'image','reference':value['presentation']['reference']} for value in result.get('images',[])] if self.config.get('apiModel',{}).get('imageInput')=='supported' else []
                if result.get('screenshotReference') and result.get('imageDelivery')=='pixels':
                    media.append({'type':'image','reference':result['screenshotReference']})
                origin={'toolReceiptId': bound_id, 'turnId': self.turn_id}
                if media and optimized(self.config.get('contextPolicy'), 1):
                    from context_media import purpose
                    origin['mediaPurpose']=purpose(call['name'],call['arguments'])
                self.conversation.append(self.run_id, 'tool-' + bound_id + '-' + str(self.round), 'tool',
                    [{'type': 'tool_result', 'callId': call['callId'], 'result': reply},*media],
                    origin)
                if not final_tool_results and (result.get('error') == 'unknown'
                        or result.get('partialChangesPossible') and result.get('error') == 'interrupted'):
                    self.unconfirmed()
            if file_preconditions:
                self.workspace_tools.file_batch = None
            # An unrelated later schema error gets its own correction. Text,
            # failed/partial batches and uncertain effects never renew it.
            if batch_succeeded and not self.uncertain_effect:correction_attempts=0
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
                user_content(self.config,human), {'requestId': self.row['request_id'], **({'kind':'quotaContinuation','waitId':self.config['quotaResume']['waitId'],'parentRunId':self.config['quotaResume']['parentRunId']} if self.config.get('quotaResume') else {}), **({'kind':'humanGoalPlay'} if self.config.get('goalExecution') else {})})
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
            self.context.failed(error)
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
        first = errors[0]
        self.args=(first['tool'] + ': ' + first['message'] + ' The tool batch was not executed.',)
