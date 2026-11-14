#!/usr/bin/env python3
"""One systemd-owned run; independent of the web app and host coordinator."""
from tool_catalog import tool_scope,WEB_TOOLS,GOAL_TOOLS,native_specifications
import asyncio
import fcntl
import json
import os
from pathlib import Path
import signal
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / 'project-development'))

from profile import NOTE_TOOLS, REMOTE_TOOLS, ROADMAP_TOOLS, prepare, SANDBOX_MODE, tools_for, DEVELOPMENT_TOOLS, AUTHOR_TOOLS
from profile import WINDOW_TOOLS, write_json
from session_store import SessionStore, encode, now
from run_store import get_run, transition, event, item, request_text
from codex_rpc import CodexRPC
from tool_catalog import specifications, validate_arguments
from workspace_tools import WorkspaceTools
from terminal import Terminals, bounded_text
from system_prompt import snapshot as prompt_snapshot
from store import ProjectFault
from owner import binding, open_lock

class Worker:
    def __init__(self, manifest):
        self.manifest = manifest
        kind, ident = binding(manifest)
        self.store = SessionStore(manifest['projects'], manifest['r4os'], ident, kind)
        self.store.public_stream_failed = self.defer_stop
        self.run_id = manifest['runId']; self.row = get_run(self.store, self.run_id)
        self.session_id = self.row['session_id']; self.config = json.loads(self.row['config'])
        from active_tools import verify as verify_catalog
        verify_catalog(self.config)
        self.store.row(self.session_id)
        if manifest.get('sessionId', self.session_id) != self.session_id:
            raise ValueError('This run belongs to another session.')
        expected_owner = {'type': kind, 'id': ident}
        if ('owner' in self.config and self.config['owner'] != expected_owner) or (kind == 'skill' and self.config.get('owner') != expected_owner):
            raise ValueError('The run owner binding changed.')
        # A previous coordinator may admit a new-release worker while older
        # workers finish. Freeze its prompt once, before starting any inference.
        if kind == 'project' and self.row['busy'] and 'systemPrompt' not in self.config:
            self.config['systemPrompt'] = prompt_snapshot(self.store.projects)
            with self.store.db:
                self.store.db.execute('UPDATE runs SET config=? WHERE id=?', (encode(self.config), self.run_id))
        # An older compatible coordinator may still admit a new-release worker.
        # Settings are locked for this busy run, so freeze the omitted choice once.
        if self.row['busy'] and 'fastMode' not in self.config:
            self.config['fastMode'] = self.store.get(self.session_id)['fastMode']
            with self.store.db:
                self.store.db.execute('UPDATE runs SET config=? WHERE id=?', (encode(self.config), self.run_id))
        self.client = None; self.turn_id = None; self.thread_id = None
        self.done = asyncio.Event(); self.stopping = False; self.outcome = 'unknown'; self.error = None
        self.turn_requested = False
        self.uncertain_effect = False
        self.items = {}; self.lease = None
        self.api_runtime=None;self.api_worker=None;self.zai_watch=None
        self.generated_started=set();self.stop_task=None;self.interrupt_tasks={};self.closing=False
        self.workspace_tools = WorkspaceTools(self)
        from skill_resources import SkillResources
        self.skill_resources = SkillResources(self)
        from skill_mcp_tools import SkillTools as ManagedSkillTools
        self.skill_mcp = ManagedSkillTools(self)
        self.terminals = Terminals(self)
        from agent_snapshot import AgentSnapshots
        self.build_snapshots = AgentSnapshots(self)
        from development_tools import DevelopmentTools
        self.development = DevelopmentTools(self)
        from skill_tools import SkillTools
        self.skills = SkillTools(self)
        self.vision_helper = None
        self.generation_helper = None
        self.goal_worker = None
        from goal_keepalive_run import RunGoal
        self.keepalive_goal=RunGoal(self) if self.config.get('goalKeepalive') else None
        self.message_worker = None
        from usage_stats import WorkerUsage
        self.usage_stats=WorkerUsage(self)
        from session_context import Context
        self.context=Context(self)
        if self.row['busy'] and 'contextProtocol' not in self.config and not self.config.get('apiProvider'):
            self.config['contextProtocol']=1
            with self.store.db:self.store.db.execute('UPDATE runs SET config=? WHERE id=?',(encode(self.config),self.run_id))
        if self.config['engine'].get('kind') == 'studio':
            pass  # The Studio loop owns its lifecycle; never instantiate native Goal control.
        elif self.config.get('goalExecution'):
            from goal_worker import GoalWorker
            self.goal_worker = GoalWorker(self)
        elif self.config.get('nativeGoalPreparation') is True:
            from goal_worker import GoalWorker
            self.goal_worker = GoalWorker(self,dormant=True)
        from provider_retry import ProviderRetry
        self.provider_retry = ProviderRetry(self)

    async def notify(self, method, params):
        if params.get('threadId') and params['threadId'] != self.thread_id: return
        if method != 'item/agentMessage/delta':
            from public_stream import flush
            flush(self.store)
        if method in ('turn/started', 'turn/completed') and params.get('turn', {}).get('id') in self.provider_retry.held_turns:
            return  # A duplicate old boundary cannot finish the current continuation.
        if method == 'turn/completed' and params.get('turn', {}).get('status') == 'failed' and not self.error:
            from provider_errors import describe
            if isinstance(params['turn'].get('error'), dict): self.error = describe(params['turn']['error'],api=bool(self.config.get('apiProvider')),subscription=self.api_runtime)['text']
        self.usage_stats.notify(method,params)
        self.context.notify(method,params)
        if self.message_worker: self.message_worker.observe(method, params)
        retry_hold = self.provider_retry.observe(method, params)
        if self.goal_worker and await self.goal_worker.notify(method, params, retry_hold=retry_hold): return
        if retry_hold: return
        if method == 'turn/started':
            self.turn_id = params['turn']['id']
            transition(self.store, self.run_id, 'running', turn_id=self.turn_id)
            if self.stopping:self.defer_interrupt(self.turn_id)
        elif method == 'turn/completed':
            self.turn_id = params['turn']['id']
            status = params['turn']['status']
            self.outcome = 'unknown' if self.uncertain_effect else {'completed': 'completed', 'failed': 'failed', 'interrupted': 'interrupted'}.get(status, 'unknown')
            if self.outcome == 'failed': self.error = self.error or 'The agent run failed.'
            self.done.set()
        elif method == 'studio/processExited':
            if self.done.is_set(): return
            self.error = self.error or 'The agent process stopped before its result was confirmed.'
            self.done.set()
        elif method == 'error':
            from provider_errors import describe
            description = describe(params.get('error'),api=bool(self.config.get('apiProvider')),subscription=self.api_runtime); retrying = params.get('willRetry') is True
            event(self.store, self.session_id, self.run_id, 'notice', {'text': description['text'], 'retrying': retrying,
                'providerError': {key: value for key, value in description.items() if key != 'text'}})
            if not retrying: self.error = description['text']
        elif method in ('item/started', 'item/completed'):
            native = params['item']; kind = native.get('type'); ident = native.get('id')
            if kind == 'agentMessage':
                value = {'id': ident, 'runId': self.run_id, 'type': 'assistant', 'text': native.get('text', ''),
                         'phase': native.get('phase'), 'status': 'completed' if method == 'item/completed' else 'running'}
                self.items[ident] = value; item(self.store, self.session_id, self.run_id, value)
            elif kind == 'dynamicToolCall':
                value = self.items.get(ident) or {'id': ident, 'runId': self.run_id, 'type': 'tool',
                         'tool': native.get('tool', '').replace('studio_', 'studio.', 1), 'arguments': native.get('arguments'), 'status': 'pending'}
                if method == 'item/completed' and value['status'] == 'pending':
                    value['status'] = 'completed' if native.get('success') else 'failed'
                    content = native.get('contentItems') or []
                    value['output'] = '\n'.join(v.get('text', '') for v in content if v.get('type') == 'inputText')[:24000]
                self.items[ident] = value
                item(self.store, self.session_id, self.run_id, value)
            elif kind == 'imageGeneration':
                if self.config.get('nativeImageGeneration') is not True:
                    self.error='Native image generation was reported while disabled.';self.outcome='failed';self.defer_stop();return
                from generated_images import presentation
                self.generated_started.add(ident)
                if len(self.generated_started)>8:
                    self.error='The run reached its eight-image limit; generation was stopped.';self.uncertain_effect=True;self.defer_stop();return
                try:value=presentation(self,native,method=='item/completed')
                except Exception as error:
                    self.error=str(error) if isinstance(error,__import__('store').ProjectFault) else 'Image storage could not be confirmed. Native history was preserved; do not regenerate.'
                    self.uncertain_effect=True;self.defer_stop();return
                if value['status']=='failed' and value.get('error')!='usageLimitExceeded':
                    # Native failure metadata cannot establish whether the image
                    # POST was processed before its response was lost.
                    self.uncertain_effect=True;self.outcome='unknown'
                    value.update(status='unknown',partialChangesPossible=True)
                self.items[ident]=value;item(self.store,self.session_id,self.run_id,value)
                if value['status'] in ('failed','unknown'):
                    self.error=value['output'];self.defer_stop();return
            elif kind == 'webSearch':
                if self.config.get('webSearchEnabled') is not True:
                    self.error = 'Web search was reported although it is disabled for this run.'
                    self.outcome = 'failed'; self.defer_stop()
                    return
                from web_search import presentation
                value = presentation(native, self.run_id, completed=method == 'item/completed')
                self.items[ident] = value; item(self.store, self.session_id, self.run_id, value)
            elif kind == 'contextCompaction':
                event(self.store, self.session_id, self.run_id, 'notice', {'text': 'Conversation context compacted.'})
            elif kind not in ('userMessage', 'reasoning', 'plan'):
                self.error = 'An unsupported native tool or item was reported; the run was stopped.'
                self.outcome = 'failed'; self.defer_stop()
        elif method == 'item/agentMessage/delta':
            ident = params['itemId']; value = self.items.setdefault(ident, {'id': ident, 'runId': self.run_id, 'type': 'assistant', 'text': '', 'status': 'running'})
            value['text'] += params['delta']
            if len(value['text'].encode()) > 196608: raise RuntimeError('Agent message exceeds output limit.')
            from public_stream import delta as public_delta
            public_delta(self.store, self.session_id, self.run_id, value, {'itemId': ident, 'text': params['delta']})
        elif method == 'thread/tokenUsage/updated':
            total = params.get('tokenUsage', {}).get('total', {})
            safe = {k: v for k, v in total.items() if type(v) is int and v >= 0}
            event(self.store, self.session_id, self.run_id, 'usage', safe)

    async def execute(self, name, arguments, call_id):
        if self.keepalive_goal and name in ('get_goal','update_goal'):return await self.keepalive_goal.tool(name,arguments)
        if name in ('skill_discover','skill_call','read_skill_result'):
            return await self.skill_mcp.call(name,arguments,call_id)
        if name=='generate_image':
            from image_generation_call import ImageGeneration
            try:
                if self.generation_helper is None:self.generation_helper=ImageGeneration(self)
                return await self.generation_helper.generate(call_id,arguments)
            except ProjectFault as error:return {'success':False,'error':'imageUnavailable','output':str(error)}
        if name in NOTE_TOOLS:
            from environment_note_tools import execute
            return execute(self,name,arguments,call_id)
        if name=='read_context_result':
            from context_results import execute
            try:return await execute(self,arguments,call_id)
            except ProjectFault as error:return {'success':False,'error':'unavailable','output':str(error)}
        if name in ('list_generated_images','import_generated_image'):
            from generation_tools import execute
            return await execute(self,name,arguments,call_id)
        if name=='read_attachment':
            from document_inputs import read_attachment
            return await read_attachment(self,arguments)
        if name in REMOTE_TOOLS:
            from remote_tools import RemoteTools
            return await RemoteTools(self).call(name, arguments, call_id)
        if name in (*ROADMAP_TOOLS,'finish_github_issue'):
            from roadmap_tools import RoadmapTools
            return await RoadmapTools(self).call(name, arguments, call_id)
        if name == 'push_project' and self.store.owner_type == 'project':
            from github_tools import GitHubTools
            return await GitHubTools(self).call(arguments, call_id)
        if name == 'read_project_git' and self.store.owner_type == 'project':
            from github_tools import GitHubTools
            return await GitHubTools(self).inspect(arguments,call_id)
        if name in AUTHOR_TOOLS and self.store.owner_type == 'skill': return await self.skills.call(name, arguments, call_id)
        if name in (*DEVELOPMENT_TOOLS, *WINDOW_TOOLS) and self.store.owner_type == 'project': return await self.development.call(name, arguments, call_id)
        if name in ('exec_command', 'write_stdin', 'terminate_process'):
            return await self.terminals.call(name, arguments)
        if name in ('list_directory', 'read_file', 'search', 'write_file', 'apply_patch', 'create_directory'):
            return await self.workspace_tools.file(name, arguments, call_id)
        return {'success': False, 'error': 'unavailable', 'output': 'This tool is not available in this Studio release.'}

    def unconfirmed(self):
        if self.uncertain_effect: return
        self.uncertain_effect = True; self.stopping = True; self.outcome = 'unknown'
        self.error = 'A tool result is unconfirmed. Inspect possible partial changes before sending a follow-up.'
        transition(self.store, self.run_id, 'stopping', self.error)
        self.defer_stop()

    async def tool(self, params):
        async def output(result, image_data=None):
            return await self.development.native_output(result, image_data)
        name = params.get('tool', '')
        if self.provider_retry.state in ('waiting', 'submitting'):
            return await output({'success': False, 'error': 'interrupted', 'output': 'No native tool is admitted while the original continuation is waiting.'})
        if (not name.startswith('studio_') or name[7:] not in tools_for(tool_scope(self.config)) or params.get('namespace') is not None
            or self.config.get('toolCatalog') is not None and name not in self.config['toolCatalog']['tools']
            or params.get('threadId') != self.thread_id or params.get('turnId') != self.turn_id):
            return await output({'success': False, 'error': 'invalidCall', 'output': 'This call does not belong to the active Studio run.'})
        return await self.bound_tool(name,params['arguments'],params['callId'])

    async def bound_tool(self,name,arguments,call_id,output=None,admission_error=None):
        """Common Studio receipts/effects after an engine proves its own binding."""
        from public_stream import flush
        flush(self.store)
        if output is None:
            async def output(result,image_data=None):return await self.development.native_output(result,image_data)
        if (not isinstance(name,str) or not name.startswith('studio_') or name[7:] not in tools_for(tool_scope(self.config))
            or self.config.get('toolCatalog') is not None and name not in self.config['toolCatalog']['tools']
            or not isinstance(call_id,str) or not 1<=len(call_id.encode())<=256 or any(ord(c)<=32 or ord(c)==127 for c in call_id)):
            return await output({'success':False,'error':'invalidCall','output':'This tool is outside the original Studio run binding.'})
        if not isinstance(arguments, dict) or len(encode(arguments).encode()) > 131072:
            return await output({'success': False, 'error': 'invalidArguments', 'output': 'Invalid tool arguments.'})
        try: validate_arguments(name[7:], arguments, self.config)
        except ValueError as e: return await output({'success': False, 'error': 'invalidArguments', 'output': str(e)})
        from tool_catalog import operation
        from tool_receipt_boundary import fingerprint, original_hash, record_input
        requested=name
        requested_hash=fingerprint(name,arguments)
        handler,arguments=operation(name[7:],arguments,self.config)
        name='studio_'+handler
        if name[7:] in NOTE_TOOLS:
            from environment_note_tools import require
            try:require(self)
            except ProjectFault as error:return await output({'success':False,'error':'disabled','output':str(error)})
        roadmap_denial = None
        if name[7:] in ROADMAP_TOOLS:
            from roadmap_access import require
            try: require(self)
            except ProjectFault as error: roadmap_denial = str(error)
        if name[7:] in WEB_TOOLS:
            try:__import__('studio_web').require(self)
            except ProjectFault as error:roadmap_denial=str(error)
        hashed = requested_hash if requested==name else fingerprint(name,arguments)
        previous = self.store.db.execute('SELECT t.* FROM tools t JOIN runs r ON r.id=t.run_id WHERE r.session_id=? AND t.call_id=? LIMIT 1', (self.session_id, call_id)).fetchone()
        tool_id = name.replace('studio_', 'studio.', 1)
        from tool_deadlines import seconds_for
        from tool_outcomes import execute_with_deadline, reported_result
        deadline = seconds_for(self.config, tool_id)
        if previous:
            if roadmap_denial:
                return await output({'success': False, 'error': 'disabled', 'output': roadmap_denial})
            if original_hash(self.store,previous) != requested_hash:
                return await output({'success': False, 'error': 'conflict', 'output': 'Tool call ID has different arguments.'})
            if name[7:] in NOTE_TOOLS:
                from environment_note_tools import replay
                return await output(replay(self,name[7:],arguments,previous))
            if previous['result']:
                result = json.loads(previous['result'])
                result.pop('_fileVersions', None)
                if deadline is not None:
                    result = reported_result(result)
                if result.get('image') and result.get('error')=='unknown' and name in ('studio_capture_vm','studio_send_vm_input'):
                    self.unconfirmed()
                    return await output(result)
                if name == 'studio_read_development_job':
                    result = self.development.replay_read(arguments, result)
                if result.get('error') != 'unknown':
                    if result.get('skillMcp'):
                        reference=result['skillMcp']
                        current={(entry['id'],entry['activeHash']) for entry in self.config.get('skillAccess',{}).get('entries',[]) if entry.get('mcp')}
                        if (not self.config['permissions'].get(name.replace('studio_','studio.',1),False)
                                or (reference['skillId'],reference['packageHash']) not in current):
                            return await output({'success':False,'error':'unavailable','output':'This historical skill result is outside the current accepted skill selection. Its original data was preserved.'})
                    if result.get('skillResources'):
                        current = {(entry['id'], entry['activeHash']) for entry in self.config.get('skillAccess', {}).get('entries', [])}
                        if (not self.config['permissions'].get(name.replace('studio_', 'studio.', 1), False)
                                or any((reference['id'], reference['hash']) not in current for reference in result['skillResources'])):
                            return await output({'success': False, 'error': 'unavailable', 'output': 'This historical skill resource receipt is outside the current run selection. Its stored history was preserved.'})
                    return await output(result)
            if name == 'studio_read_project_git':
                return await output({'success':False,'error':'interrupted','output':'The original read-only Git response is unavailable. No commit, pull or push was submitted by this read.'})
            result = {'success': False, 'error': 'unknown', 'output': 'The previous tool outcome is unconfirmed; it was not repeated.', 'partialChangesPossible': True}
            self.unconfirmed()
            value = {'id': call_id, 'runId': self.run_id, 'type': 'tool', 'tool': name.replace('studio_', 'studio.', 1),
                     'arguments': arguments, 'status': 'unknown', 'output': result['output'], 'error': 'unknown', 'partialChangesPossible': True}
            self.items[call_id] = value; item(self.store, self.session_id, self.run_id, value)
            return await output(result)
        with self.store.db:
            self.store.db.execute('BEGIN IMMEDIATE')
            row = get_run(self.store, self.run_id)
            admission_closed = self.closing or self.stopping or not row['busy'] or row['state'] == 'stopping'
            self.store.db.execute('INSERT INTO tools VALUES (?,?,?,?,?,?,NULL)',
                                  (self.run_id, call_id, name, hashed, 'intent', encode(arguments)))
            if requested!=name:
                record_input(self.store,self.run_id,call_id,requested,requested_hash)
        if admission_closed:
            result = {'success': False, 'error': 'interrupted', 'output': 'The run is stopping.'}
        elif admission_error is not None:
            result = admission_error
        elif roadmap_denial:
            result = {'success': False, 'error': 'disabled', 'output': roadmap_denial}
        elif (name[7:] not in (*ROADMAP_TOOLS,*NOTE_TOOLS,*WEB_TOOLS)
                and not ((self.config['engine'].get('kind')=='studio' or self.config.get('goalKeepalive')) and name[7:] in __import__('tool_catalog').GOAL_TOOLS)
                and not self.config['permissions'].get(tool_id, False)):
            result = {'success': False, 'error': 'disabled', 'output': 'This tool call is disabled in session settings.'}
        else:
            try:
                if deadline is None:
                    result = await self.execute(name[7:], arguments, call_id)
                else:
                    result = await execute_with_deadline(self, name[7:], arguments, call_id, deadline)
            except asyncio.CancelledError:
                result = ({'success':False,'error':'interrupted','output':'The read-only Git inspection was interrupted. No commit, pull or push was submitted.'}
                    if name == 'studio_read_project_git' else
                    {'success': False, 'error': 'interrupted', 'output': 'The tool was interrupted; partial effects may remain.', 'partialChangesPossible': True})
            except Exception:
                uncertain = name[7:] in ('generate_image','import_generated_image','run_remote_command', 'remote_files', 'stop_remote_job', 'update_roadmap', 'cleanup_roadmap', 'write_file', 'apply_patch', 'create_directory', 'exec_command', 'write_stdin', 'terminate_process', 'start_project_vm', 'stop_project_vm','restart_project_vm', 'run_vm_command', 'deploy_project', 'run_project', 'complete_development_job', 'stop_development_job', 'send_vm_input', 'save_skill', 'push_project', 'finish_github_issue', 'plan_update_package', 'build_update_package', 'upload_update_package', 'install_update_package', 'commit_update', 'resume_update', 'abort_update', 'rollback_update', 'cleanup_update_transport')
                uncertain = uncertain or name == 'studio_control_app_window' and (not isinstance(arguments,dict) or arguments.get('action') != 'status')
                uncertain = uncertain or name == 'studio_skill_call'
                result = {'success': False, 'error': 'unknown' if uncertain else 'failed', 'output': 'The workspace tool could not confirm its result.',
                          **({'partialChangesPossible': True} if uncertain else {})}
            if deadline is not None:
                result = reported_result(result)
        # Strip image bytes before any durable tool result, item or SSE event.
        # Replayed results have only the image reference and revalidate its file.
        image_data = result.pop('_transientImage', None)
        file_versions = result.pop('_fileVersions', None)
        if result.get('error') == 'unknown':
            self.unconfirmed()
        stored_result = {**result,'_fileVersions':file_versions} if file_versions else result
        with self.store.db:
            self.store.db.execute('UPDATE tools SET state=?,result=? WHERE run_id=? AND call_id=?',
                                  ('completed' if result['success'] else ('unknown' if result.get('error') == 'unknown' else 'failed'), encode(stored_result), self.run_id, call_id))
        value = {'id': call_id, 'runId': self.run_id, 'type': 'tool', 'tool': tool_id, 'arguments': arguments,
                 'status': 'completed' if result['success'] else {'disabled': 'denied', 'interrupted': 'interrupted', 'unknown': 'unknown'}.get(result.get('error'), 'failed'),
                 'output': result.get('output', ''), 'error': result.get('error')}
        for key in ('remote', 'roadmap', 'webSearch', 'development', 'developmentStop', 'github', 'githubIssue', 'image', 'captureState', 'imageDelivery', 'visionAnalysis', 'exitCode', 'signal', 'reason', 'nextLine', 'nextOffset', 'totalLines', 'lineTruncated', 'skippedFiles', 'reasonCode', 'partialChangesPossible', 'files', 'skill', 'generatedAsset', 'generatedImage', 'imageGeneration', 'skillMcp', 'skillMcpRequest', 'deadlineSeconds'):
            if key in result: value[key] = result[key]
        if name in ('studio_exec_command','studio_write_stdin','studio_terminate_process'):
            from terminal_timing import FIELDS as terminal_time_fields
            for key in ('processId',*terminal_time_fields):
                if key in result:value[key]=result[key]
        value['truncated'] = bool(result.get('truncated') or result.get('outputTruncated'))
        base_size = len(encode({**value, 'output': ''}).encode())
        value['output'], clipped = bounded_text(str(value['output']), max(2, 261000-base_size))
        value['truncated'] = value['truncated'] or clipped
        self.items[call_id] = value; item(self.store, self.session_id, self.run_id, value)
        reply = await output(result, image_data)
        if file_versions and result['success']:
            self.workspace_tools.record_file_versions(file_versions, call_id)
        return reply

    def defer_stop(self):
        # A notification runs on the RPC reader. Keep it free to receive the
        # replies needed by Goal pause/interrupt; close new tool admission now.
        self.stopping=True
        if self.stop_task is None:self.stop_task=asyncio.create_task(self._stop())

    async def stop(self):
        self.defer_stop()
        if asyncio.current_task() is not self.stop_task:await asyncio.shield(self.stop_task)

    def defer_interrupt(self,turn_id):
        if self.closing or not self.client or not self.thread_id or not turn_id:return None
        key=(self.thread_id,turn_id)
        if key not in self.interrupt_tasks:
            if len(self.interrupt_tasks)>=64:
                self.uncertain_effect=True;self.outcome='unknown'
                self.error=self.error or 'Native turns continued after Stop. The worker will close without starting new work.'
                self.done.set();return None
            async def interrupt():
                try:await self.client.request('turn/interrupt',{'threadId':key[0],'turnId':key[1]},timeout=5)
                except Exception:pass  # Native process closure remains the final stop boundary.
            self.interrupt_tasks[key]=asyncio.create_task(interrupt())
        return self.interrupt_tasks[key]

    async def _stop(self):
        try:
            self.stopping = True
            if self.vision_helper: await self.vision_helper.close()
            if self.generation_helper: await self.generation_helper.close()
            await self.provider_retry.cancel_for_control()
            await self.skill_mcp.close()
            if self.goal_worker:
                user_stop = get_run(self.store,self.run_id)['state']=='stopping' and not self.uncertain_effect
                await self.goal_worker.pause(origin='user' if user_stop else 'automatic')
            if 'run_remote_command' in tools_for(tool_scope(self.config)):
                from remote_tools import RemoteTools
                await RemoteTools(self).stop_owned()
            if 'run_project' in tools_for(tool_scope(self.config)): await self.development.stop_owned()
            interrupt=self.defer_interrupt(self.turn_id)
            if interrupt:await asyncio.shield(interrupt)
        except Exception:
            self.uncertain_effect=True
            self.error=self.error or 'The original stop outcome could not be confirmed.'
        finally:
            if not self.done.is_set():
                if self.outcome not in ('completed','failed'):self.outcome='unknown' if self.uncertain_effect else 'interrupted'
                self.done.set()

    async def cleanup(self):
        self.closing=True
        if self.vision_helper: await self.vision_helper.close()
        if self.generation_helper: await self.generation_helper.close()
        if self.keepalive_goal and self.goal_worker is not self.keepalive_goal:await self.keepalive_goal.close()
        if self.stop_task and self.stop_task is not asyncio.current_task():await asyncio.gather(self.stop_task,return_exceptions=True)
        self.closing=True
        await self.provider_retry.close()
        await self.usage_stats.close()
        if self.message_worker: await self.message_worker.close()
        if self.goal_worker: await self.goal_worker.close()
        if self.interrupt_tasks:await asyncio.gather(*self.interrupt_tasks.values(),return_exceptions=True)
        if 'run_remote_command' in tools_for(tool_scope(self.config)):
            from remote_tools import RemoteTools
            await RemoteTools(self).stop_owned()
        await self.build_snapshots.close()
        if self.client: await self.client.close()
        await self.terminals.close()
        await self.workspace_tools.close()
        await self.skill_mcp.close()
        await self.skill_resources.close()
        from public_stream import flush
        flush(self.store)

    async def run(self):
        if not self.row['busy']: return
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
        try:
            if self.row['state'] == 'stopping': self.outcome = 'interrupted'; return
            if (self.config.get('apiProvider') and (self.config.get('goalExecution') or self.config.get('nativeGoalPreparation'))
                    and self.config.get('apiGoalProtocol')!=1):
                raise __import__('store').ProjectFault('This original API run has no qualified Goal lifecycle contract. Its frozen snapshot was preserved.',409)
            if self.config.get('nativeImageGeneration') is True:
                from image_generation import freeze
                capability=freeze(self.config,self.config.get('imageGenerationCapability'))
                if not self.config.get('imageGenerationEnabled') or not capability['available']:
                    self.error='The frozen image generation capability is unavailable.';raise __import__('store').ProjectFault(self.error,409)
                from generated_images import GeneratedImages
                GeneratedImages(self.store,self.session_id).check_capacity(self.run_id)
            self.lease = open_lock(self.store.projects, self.store.owner_type, self.store.owner_id)
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.config.get('inputContractVersion')==1 and self.config.get('goalExecution'):
                from human_context import text as human_text
                if human_text(self.store.db,self.session_id,self.run_id,self.config['owner'])!=self.config['goalExecution']['objective']:
                    self.error='The original human Goal Play evidence changed. Preserve the run and review it.'
                    raise __import__('store').ProjectFault(self.error,409)
            if self.store.owner_type == 'project': await self.build_snapshots.start()
            transition(self.store, self.run_id, 'starting', worker={'release': self.manifest['release'], 'pid': os.getpid(), 'birth': __import__('lease').birth(os.getpid()), **__import__('model_operations').worker_identity()})
            state = self.store.directory / self.session_id / 'Codex'
            provider_home = Path(self.manifest['providers']) / self.config['providerId']
            if self.config.get('apiProvider'):
                from api_provider_store import ApiProviders,private
                from api_runtime import ApiRuntime
                self.api_worker={'release':self.manifest['release'],'pid':os.getpid(),'birth':__import__('lease').birth(os.getpid())}
                credential=ApiProviders(self.manifest['providers']).claim(self.run_id,self.store.owner_type,self.store.owner_id,
                    self.session_id,self.row['request_id'],self.config,self.api_worker)
                # This session owns its native home; it cannot see subscription
                # auth or the API secret database. Only the trusted relay gets
                # the exact credential revision reserved at admission.
                state.mkdir(mode=0o700,parents=True,exist_ok=True);private(state,directory=True)
                provider_home=state/'ApiHome';provider_home.mkdir(mode=0o700,exist_ok=True);private(provider_home,directory=True)
                reasoning=None
                if self.config.get('apiChat',{}).get('schema')==2:
                    history=state/('ZaiReasoning' if self.config['apiProvider']['kind']=='zai-coding-plan' else 'OpenRouterReasoning');history.mkdir(mode=0o700,exist_ok=True);private(history,directory=True)
                    reasoning={'directory':str(history),'providerKind':self.config['apiProvider']['kind'],'scope':{'ownerType':self.store.owner_type,'ownerId':self.store.owner_id,
                        'sessionId':self.session_id,'providerId':self.config['providerId'],'model':self.config['model'],
                        'baseUrl':self.config['apiProvider']['baseUrl'],'protocol':self.config['apiProvider']['protocol']},
                        'origin':{'configRevision':self.config['apiProvider']['revision'],
                            'credentialRevision':self.config['apiProvider']['credentialRevision'],'engineSha256':self.config['engine']['sha256']}}
                self.api_runtime=ApiRuntime(self.config['apiProvider'],self.config['model'],credential,
                    self.store.directory/self.session_id/'ApiTransport'/self.run_id,chat=self.config.get('apiChat'),reasoning=reasoning,client=self.config.get('apiZaiClient'),
                    limit_observer=(lambda value:__import__('zai_limits').observe(self.manifest['providers'],self.config['apiProvider'],self.config['model'],self.run_id,value)) if self.config['apiProvider']['kind']=='zai-coding-plan' else None)
                credential=None
                await self.api_runtime.start()
                if self.config['apiProvider']['kind']=='zai-coding-plan':
                    from zai_limit_guard import watch
                    self.zai_watch=asyncio.create_task(watch(self))
            from codex_runtime import binary as runtime_binary
            binary = runtime_binary(self.manifest['r4os'], self.config['engine'])
            from image_inputs import mounts as image_mounts,native_input
            try:mounts=image_mounts(self.store,self.session_id,self.config)
            except __import__('store').ProjectFault as error:
                self.error=str(error);raise
            args, runtime = prepare(binary, provider_home, state,
                                    json.loads((Path(__file__).parent / 'features.json').read_text()), self.config['model'], self.config['providerId'], tool_scope(self.config),
                                    fast_mode=self.config.get('fastMode', False), web_search_enabled=self.config.get('webSearchEnabled', False), goals_enabled=bool(self.goal_worker),attachment_mounts=mounts,image_modalities=self.config.get('imageInputModalities'),image_generation_enabled=self.config.get('nativeImageGeneration') is True,generated_root=GeneratedImages(self.store,self.session_id).native_root() if self.config.get('nativeImageGeneration') else None,catalog_data=self.config.get('apiModels'),expected_engine=self.config['engine'],workspace=self.store.workspace)
            if self.api_runtime:args=self.api_runtime.arguments(args)
            from instructions import compose
            instructions = compose(self.config, self.store.project if self.store.owner_type == 'project' else None)
            if self.goal_worker and self.goal_worker.dormant:
                instructions += '\n\nSTUDIO GOAL CONTROL: Native Goal capability is dormant. Only a deliberate browser Goal Save/Play command can authorize Goal activation. Do not call create_goal or update_goal to start or replace a Goal during ordinary work. Loading a session, queue input, capability availability and model text do not authorize Play. Finish the current user request normally unless the browser explicitly activates a Goal.'
            from native_tools import synchronize as synchronize_tools
            try:
                native_catalog = await asyncio.to_thread(synchronize_tools, self.store, self.session_id, self.run_id, self.config)
            except Exception:
                self.error = 'The current tool catalog could not be prepared for this saved conversation. Original history and the refresh journal were preserved; no model turn was started.'
                raise
            try:
                write_json(Path(self.manifest['projects']) / '.studio/agents' / self.run_id / 'tool-catalog.json',
                           {'catalog': self.config.get('toolCatalog'), 'native': native_catalog})
            except Exception:
                self.error = 'The current tool catalog was prepared, but its run receipt could not be saved. The saved conversation was preserved; no model turn was started.'
                raise
            self.client = CodexRPC(args, self.notify, self.tool)
            from generated_images import GeneratedImages
            if self.config.get('nativeImageGeneration') or GeneratedImages(self.store,self.session_id).rows():
                from generated_images import RPC_IMAGE_LIMIT
                self.client.inbound_limit=RPC_IMAGE_LIMIT
            self.client.version = self.manifest['version']
            await self.client.start()
            if self.config.get('nativeImageGeneration'):
                from image_generation import evaluate
                capability=await self.client.request('modelProvider/capabilities/read',{},timeout=5)
                account=await self.client.request('account/read',{'refreshToken':False},timeout=5)
                frozen=self.config['imageGenerationCapability']
                current=evaluate(self.config,{'imageInputs':'supported','inputModalities':frozen.get('inputModalities')},capability,account,runtime,True)
                if not current['available'] or current.get('accountSha256')!=frozen.get('accountSha256'):
                    self.error='The native image account or provider changed after admission. No turn was started.'
                    raise __import__('store').ProjectFault(self.error,409)
            self.thread_id = self.store.row(self.session_id)['thread_id']
            if self.goal_worker: await self.goal_worker.before_resume()
            # Explicit default clears a Fast tier saved by an earlier native turn.
            service_tier = 'priority' if self.config.get('fastMode', False) else 'default'
            web_search_mode = 'live' if self.config.get('webSearchEnabled', False) else 'disabled'
            from image_provider import selection as image_provider_selection
            native_provider=image_provider_selection(self.config.get('nativeModelProvider'))
            if self.api_runtime:native_provider=self.api_runtime.selection()
            if self.thread_id:
                try:
                    response=await self.client.request('thread/resume', {**native_provider,'threadId': self.thread_id, 'path': str(__import__('native_tools').binding(self.store, self.session_id)['path']), 'cwd': str(self.store.workspace), 'excludeTurns': True, 'model': self.config['model'], 'serviceTier': service_tier, 'baseInstructions': instructions, 'sandbox': SANDBOX_MODE, 'approvalPolicy': 'never', 'config': {'web_search': web_search_mode, **({'model_reasoning_effort': self.config['effort']} if self.goal_worker and self.config['effort'] else {})}})
                except Exception:
                    self.error = 'The saved conversation could not be resumed. Its files were preserved.'; raise
            else:
                response = await self.client.request('thread/start', {**native_provider,'cwd': str(self.store.workspace), 'model': self.config['model'], 'serviceTier': service_tier,
                           'ephemeral': False, 'dynamicTools': native_specifications(self.config), 'baseInstructions': instructions, 'config': {'web_search': web_search_mode, **({'model_reasoning_effort': self.config['effort']} if self.goal_worker and self.config['effort'] else {})},
                           'sandbox': SANDBOX_MODE, 'approvalPolicy': 'never'})
                self.thread_id = response['thread']['id']
                with self.store.db:
                    self.store.db.execute('UPDATE sessions SET thread_id=? WHERE id=?', (self.thread_id, self.session_id))
            if self.config.get('nativeImageGeneration'):
                from generated_images import native_output
                native_output(provider_home, GeneratedImages(self.store, self.session_id).native_root(), self.thread_id)
            self.context.native(response)
            if self.stopping: self.outcome = 'interrupted'; return
            if self.goal_worker: await self.goal_worker.start_control()
            from message_worker import MessageWorker
            self.message_worker = MessageWorker(self)
            await self.message_worker.start()
            from codex_runtime import native
            qualified_messages = native(self.config['engine'])
            message_identity = {'release':self.manifest['release'],'pid':os.getpid(),'birth':__import__('lease').birth(os.getpid()),'runtime':runtime,'messageProtocol':1 if qualified_messages else 0,'messageTurnActive':False}
            if self.config.get('nativeGoalPreparation') is True: message_identity.update(liveGoalPreparation=1,liveGoalControl=1,liveGoalOpen=True)
            transition(self.store,self.run_id,'starting',worker=message_identity)
            await self.provider_retry.bind()
            if self.config.get('goalExecution'):
                await self.goal_worker.activate()
                await self.done.wait()
                return
            self.turn_requested = True
            try:
                result = await self.client.request('turn/start', {'threadId': self.thread_id,
                             'clientUserMessageId': self.row['request_id'], 'input': native_input(self.store,self.run_id,self.config),
                             'model': self.config['model'], 'effort': self.config['effort'] or None, 'serviceTier': service_tier})
                if not self.turn_id:
                    self.turn_id = result['turn']['id']
                    message_identity['messageTurnActive'] = True
                    if not self.done.is_set(): transition(self.store, self.run_id, 'running', turn_id=self.turn_id,
                                                           worker=message_identity)
            except asyncio.TimeoutError:
                # A missing RPC reply does not negate a native started/completed
                # event. Continue observing this one turn; never send it again.
                if not self.turn_id and not self.done.is_set():
                    self.uncertain_effect = True; self.outcome = 'unknown'
                    self.error = 'The run start was not confirmed. It was not submitted again.'
                    await self.stop()
            await self.done.wait()
        except Exception:
            if self.outcome == 'unknown':
                self.outcome = 'unknown' if self.turn_requested else 'failed'
            self.error = self.error or 'The agent service could not confirm this run. Existing data was preserved.'
        finally:
            if self.goal_worker:
                if self.outcome not in ('completed',):
                    try:await self.goal_worker.pause()
                    except Exception:
                        self.uncertain_effect=True;self.outcome='unknown';self.error=self.error or 'The original Goal pause could not be confirmed.'
            if self.config.get('goalExecution'):
                from goal_store import Goals
                goals = Goals(self.store); rid = self.config['goalExecution']['requestId']
                if goals.command(self.session_id, rid)['state'] == 'pending':
                    goals.finish(self.session_id, rid, 'unknown' if self.turn_requested else 'failed', self.error or 'The original Goal activation was not confirmed.')
            try:await self.cleanup()
            except Exception:
                if not self.config.get('apiProvider'):raise
                self.outcome='unknown';self.uncertain_effect=True
                self.error=self.error or 'The original API run cleanup is unconfirmed. Inspect its retained receipts.'
                if self.client:
                    try:await self.client.close()
                    except Exception:pass
            finally:
                if self.config.get('apiProvider'):
                    try:
                        if self.zai_watch:
                            self.zai_watch.cancel();await asyncio.gather(self.zai_watch,return_exceptions=True)
                        if self.api_runtime:await self.api_runtime.close()
                        if self.client and self.client.child and self.client.child.returncode is None:raise RuntimeError('Native process closure is unconfirmed.')
                        from api_provider_store import ApiProviders
                        ApiProviders(self.manifest['providers']).release(self.run_id,self.store.owner_type,self.store.owner_id,
                            self.session_id,self.row['request_id'],self.config,self.api_worker)
                    except Exception:
                        self.outcome='unknown';self.uncertain_effect=True
                        self.error=self.error or 'The original API transport closure is unconfirmed. Credentials and history were preserved.'
            self.usage_stats.finalize()
            if self.api_runtime and self.config['apiProvider']['kind'] in ('openrouter','zai-coding-plan'):
                # Observations belong to this original run, not the model input,
                # a tool receipt or an invented billing/generation identity.
                for origin in self.api_runtime.origins:
                    try:
                        detail={'providerId':self.config['providerId'],'configRevision':self.config['apiProvider']['revision'],**origin}
                        brand='Z.AI Coding Plan' if self.config['apiProvider']['kind']=='zai-coding-plan' else 'OpenRouter'
                        label=(brand+' · selected: '+origin['requestedModel']+' · reported model: '+(origin['reportedModel'] or 'Unknown')
                            +' · backend: '+(origin['reportedBackend'] or origin['endpointBackend'] or 'Unknown'))
                        if origin['endpointModel'] and origin['endpointModel']!=origin['reportedModel']:label+=' · endpoint model: '+origin['endpointModel']
                        with self.store.db:
                            item(self.store,self.session_id,self.run_id,{'id':'api-origin-'+self.run_id+'-'+str(origin['ordinal']),
                                'runId':self.run_id,'type':'notice','status':'completed','text':label,'apiOrigin':detail})
                    except Exception:pass  # Metadata loss cannot replay an original model/tool action.
            if self.goal_worker:
                from goal_worker import end_turns
                self.goal_worker.clock.end(unknown=self.uncertain_effect or self.outcome=='unknown')
                self.goal_worker.finish_pending()
                end_turns(self.store,self.run_id)
            try:
                from image_recovery import reconcile
                reconcile(self.store,self.session_id,self.run_id,finalizing=True)
            except Exception:pass  # Retain original unknown evidence; no inference/import retry.
            if self.lease: self.lease.close()
            reconcile_items(self.store, self.run_id, self.outcome)
            transition(self.store, self.run_id, self.outcome, self.error, turn_id=self.turn_id)
            self.store.close()


def reconcile_items(store, run_id, outcome='unknown'):
    row = get_run(store, run_id)
    values = store.db.execute('SELECT payload FROM items WHERE run_id=?', (run_id,)).fetchall()
    for r in values:
        value = json.loads(r['payload'])
        if value.get('status') in ('running', 'pending'):
            receipt = store.db.execute('SELECT result FROM tools WHERE run_id=? AND call_id=?', (run_id, value['id'])).fetchone() if value.get('type') == 'tool' else None
            if receipt and receipt['result']:
                result = json.loads(receipt['result'])
                value.update(status='completed' if result['success'] else ('denied' if result.get('error') == 'disabled' else 'failed'),
                             output=result.get('output', ''), error=result.get('error'))
            else:
                value['status'] = 'interrupted' if outcome == 'interrupted' else 'unknown'
                value['error'] = 'This item ended without a confirmed result; partial effects may remain.'
            store.db.execute('UPDATE items SET payload=? WHERE run_id=? AND item_id=?', (encode(value), run_id, value['id']))
            event(store, row['session_id'], run_id, 'itemStatus', {'itemId': value['id'], 'status': value['status'], 'error': value['error']})
    with store.db: store.db.execute("UPDATE tools SET state='unknown' WHERE run_id=? AND result IS NULL", (run_id,))


def finalize(manifest):
    kind, ident = binding(manifest)
    store = SessionStore(manifest['projects'], manifest['r4os'], ident, kind)
    try:
        row = get_run(store, manifest['runId'])
        store.row(row['session_id'])
        if manifest.get('sessionId', row['session_id']) != row['session_id']: raise ValueError('Run session changed.')
        if row['busy']:
            try:
                from image_recovery import reconcile
                reconcile(store,row['session_id'],row['id'],finalizing=True)
            except Exception:pass
            stopped = row['state'] == 'stopping'
            state = 'interrupted' if stopped else ('failed' if row['state'] == 'queued' else 'unknown')
            reconcile_items(store, row['id'], state)
            if (json.loads(row['config'])['engine'].get('kind')=='studio'
                    and store.db.execute("SELECT 1 FROM tools WHERE run_id=? AND state='unknown'",(row['id'],)).fetchone()):state='unknown'
            transition(store, row['id'], state, 'Run stopped.' if stopped else 'The run service exited without a confirmed result; tool effects were not repeated.')
            from goal_store import Goals
            Goals(store).lost_worker(row['id'])
    finally: store.close()


if __name__ == '__main__':
    os.umask(0o077)
    path = Path(sys.argv[1]).absolute()
    if path.resolve(strict=True) != path: raise SystemExit('Invalid worker manifest.')
    manifest = json.loads(path.read_text())
    if len(sys.argv) > 2 and sys.argv[2] == '--finalize': finalize(manifest)
    else:
        kind,ident=binding(manifest)
        selected=SessionStore(manifest['projects'],manifest['r4os'],ident,kind)
        try:engine_kind=json.loads(get_run(selected,manifest['runId'])['config'])['engine'].get('kind')
        finally:selected.close()
        if engine_kind=='claude-code':
            from claude_worker import ClaudeWorker
            asyncio.run(ClaudeWorker(manifest).run())
        elif engine_kind == 'studio':
            from studio_worker import StudioWorker
            asyncio.run(StudioWorker(manifest).run())
        else:asyncio.run(Worker(manifest).run())
