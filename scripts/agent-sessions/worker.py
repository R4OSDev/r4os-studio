#!/usr/bin/env python3
"""One systemd-owned run; independent of the web app and host coordinator."""
import asyncio
import fcntl
import json
import os
import re
from pathlib import Path
import signal
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / 'project-development'))

from profile import prepare, write_json, TOOLS, PROFILE, VM_PROFILE, DEVELOPMENT_PROFILE, SANDBOX_MODE, tools_for, DEVELOPMENT_TOOLS
from session_store import SessionStore, encode, now
from run_store import get_run, transition, event, item, request_text
from codex_rpc import CodexRPC
from tool_catalog import specifications, validate_arguments
from sandbox import Sandbox
from terminal import Terminals, bounded_text
from system_prompt import snapshot as prompt_snapshot


class Worker:
    def __init__(self, manifest):
        self.manifest = manifest
        self.store = SessionStore(manifest['projects'], manifest['r4os'], manifest['projectId'])
        self.run_id = manifest['runId']; self.row = get_run(self.store, self.run_id)
        self.session_id = self.row['session_id']; self.config = json.loads(self.row['config'])
        # A previous coordinator may admit a new-release worker while older
        # workers finish. Freeze its prompt once, before starting any inference.
        if self.row['busy'] and 'systemPrompt' not in self.config:
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
        self.sandbox = Sandbox(self)
        self.terminals = Terminals(self)
        from agent_snapshot import AgentSnapshots
        self.build_snapshots = AgentSnapshots(self)
        from development_tools import DevelopmentTools
        self.development = DevelopmentTools(self)

    async def notify(self, method, params):
        if params.get('threadId') and params['threadId'] != self.thread_id: return
        if method == 'turn/started':
            self.turn_id = params['turn']['id']
            transition(self.store, self.run_id, 'running', turn_id=self.turn_id)
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
            code = params.get('error', {}).get('codexErrorInfo')
            message = {'usageLimitExceeded': 'This provider has reached its usage limit.',
                       'rateLimitExceeded': 'The model service is rate limited. Try again later.',
                       'unauthorized': 'The provider needs to sign in again.',
                       'contextWindowExceeded': 'The conversation exceeds the model context limit.'}.get(code if isinstance(code, str) else '', 'The model service reported an error.')
            raw_message = str(params.get('error', {}).get('message', ''))
            if re.search(r'\b401\b|\bunauthorized\b', raw_message, re.I): message = 'The provider needs to sign in again.'
            elif re.search(r'\b429\b|usage limit|quota exceeded', raw_message, re.I): message = 'This provider has reached its usage limit.'
            event(self.store, self.session_id, self.run_id, 'notice', {'text': message, 'retrying': bool(params.get('willRetry'))})
            if not params.get('willRetry'): self.error = message
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
            elif kind == 'contextCompaction':
                event(self.store, self.session_id, self.run_id, 'notice', {'text': 'Conversation context compacted.'})
            elif kind not in ('userMessage', 'reasoning', 'plan'):
                self.error = 'An unsupported native tool or item was reported; the run was stopped.'
                self.outcome = 'failed'; await self.stop()
        elif method == 'item/agentMessage/delta':
            ident = params['itemId']; value = self.items.setdefault(ident, {'id': ident, 'runId': self.run_id, 'type': 'assistant', 'text': '', 'status': 'running'})
            value['text'] += params['delta']
            if len(value['text'].encode()) > 196608: raise RuntimeError('Agent message exceeds output limit.')
            self.store.db.execute('INSERT INTO items VALUES (?,?,?,?) ON CONFLICT(session_id,run_id,item_id) DO UPDATE SET payload=excluded.payload',
                                  (self.session_id, self.run_id, ident, encode(value)))
            event(self.store, self.session_id, self.run_id, 'delta', {'itemId': ident, 'text': params['delta']})
        elif method == 'thread/tokenUsage/updated':
            total = params.get('tokenUsage', {}).get('total', {})
            safe = {k: v for k, v in total.items() if type(v) is int and v >= 0}
            event(self.store, self.session_id, self.run_id, 'usage', safe)

    async def execute(self, name, arguments, call_id):
        if name in DEVELOPMENT_TOOLS: return await self.development.call(name, arguments, call_id)
        if name in ('exec_command', 'write_stdin', 'terminate_process'):
            return await self.terminals.call(name, arguments)
        if name in ('list_directory', 'read_file', 'search', 'write_file', 'apply_patch', 'create_directory'):
            return await self.sandbox.file(name, arguments)
        return {'success': False, 'error': 'unavailable', 'output': 'This tool is not available in this Studio release.'}

    def unconfirmed(self):
        if self.uncertain_effect: return
        self.uncertain_effect = True; self.stopping = True; self.outcome = 'unknown'
        self.error = 'A tool result is unconfirmed. Inspect possible partial changes before sending a follow-up.'
        transition(self.store, self.run_id, 'stopping', self.error)
        asyncio.create_task(self.stop())

    async def tool(self, params):
        async def output(result, image_data=None):
            return await self.development.native_output(result, image_data)
        name = params.get('tool', '')
        if (not name.startswith('studio_') or name[7:] not in tools_for(self.config['engine'].get('profile', PROFILE)) or params.get('namespace') is not None
            or params.get('threadId') != self.thread_id or params.get('turnId') != self.turn_id):
            return await output({'success': False, 'error': 'invalidCall', 'output': 'This call does not belong to the active Studio run.'})
        call_id = params['callId']; arguments = params['arguments']
        if not isinstance(arguments, dict) or len(encode(arguments).encode()) > 131072:
            return await output({'success': False, 'error': 'invalidArguments', 'output': 'Invalid tool arguments.'})
        try: validate_arguments(name[7:], arguments)
        except ValueError as e: return await output({'success': False, 'error': 'invalidArguments', 'output': str(e)})
        import hashlib
        hashed = hashlib.sha256(encode({'tool': name, 'arguments': arguments}).encode()).hexdigest()
        previous = self.store.db.execute('SELECT t.* FROM tools t JOIN runs r ON r.id=t.run_id WHERE r.session_id=? AND t.call_id=? LIMIT 1', (self.session_id, call_id)).fetchone()
        if previous:
            if previous['arguments_hash'] != hashed:
                return await output({'success': False, 'error': 'conflict', 'output': 'Tool call ID has different arguments.'})
            if previous['result']:
                result = json.loads(previous['result'])
                if result.get('error') != 'unknown': return await output(result)
            result = {'success': False, 'error': 'unknown', 'output': 'The previous tool outcome is unconfirmed; it was not repeated.', 'partialChangesPossible': True}
            self.unconfirmed()
            value = {'id': call_id, 'runId': self.run_id, 'type': 'tool', 'tool': name.replace('studio_', 'studio.', 1),
                     'arguments': arguments, 'status': 'unknown', 'output': result['output'], 'error': 'unknown', 'partialChangesPossible': True}
            self.items[call_id] = value; item(self.store, self.session_id, self.run_id, value)
            return await output(result)
        with self.store.db:
            self.store.db.execute('BEGIN IMMEDIATE')
            row = get_run(self.store, self.run_id)
            admission_closed = self.stopping or not row['busy'] or row['state'] == 'stopping'
            self.store.db.execute('INSERT INTO tools VALUES (?,?,?,?,?,?,NULL)',
                                  (self.run_id, call_id, name, hashed, 'intent', encode(arguments)))
        tool_id = name.replace('studio_', 'studio.', 1)
        if admission_closed:
            result = {'success': False, 'error': 'interrupted', 'output': 'The run is stopping.'}
        elif not self.config['permissions'].get(tool_id, False):
            result = {'success': False, 'error': 'disabled', 'output': 'This tool call is disabled in session settings.'}
        else:
            try: result = await self.execute(name[7:], arguments, call_id)
            except asyncio.CancelledError: result = {'success': False, 'error': 'interrupted', 'output': 'The tool was interrupted; partial effects may remain.', 'partialChangesPossible': True}
            except Exception:
                uncertain = name[7:] in ('write_file', 'apply_patch', 'create_directory', 'exec_command', 'write_stdin', 'terminate_process', 'start_project_vm', 'deploy_project', 'run_project', 'complete_development_job')
                result = {'success': False, 'error': 'unknown' if uncertain else 'failed', 'output': 'The project tool could not confirm its result.',
                          **({'partialChangesPossible': True} if uncertain else {})}
        # Strip image bytes before any durable tool result, item or SSE event.
        # Replayed results have only the image reference and revalidate its file.
        image_data = result.pop('_transientImage', None)
        if result.get('error') == 'unknown':
            self.unconfirmed()
        with self.store.db:
            self.store.db.execute('UPDATE tools SET state=?,result=? WHERE run_id=? AND call_id=?',
                                  ('completed' if result['success'] else ('unknown' if result.get('error') == 'unknown' else 'failed'), encode(result), self.run_id, call_id))
        value = {'id': call_id, 'runId': self.run_id, 'type': 'tool', 'tool': tool_id, 'arguments': arguments,
                 'status': 'completed' if result['success'] else {'disabled': 'denied', 'interrupted': 'interrupted', 'unknown': 'unknown'}.get(result.get('error'), 'failed'),
                 'output': result.get('output', ''), 'error': result.get('error')}
        for key in ('development', 'image', 'exitCode', 'signal', 'reason', 'nextLine', 'nextOffset', 'totalLines', 'lineTruncated', 'skippedFiles', 'partialChangesPossible', 'files'):
            if key in result: value[key] = result[key]
        value['truncated'] = bool(result.get('truncated') or result.get('outputTruncated'))
        base_size = len(encode({**value, 'output': ''}).encode())
        value['output'], clipped = bounded_text(str(value['output']), max(2, 261000-base_size))
        value['truncated'] = value['truncated'] or clipped
        self.items[call_id] = value; item(self.store, self.session_id, self.run_id, value)
        return await output(result, image_data)

    async def stop(self):
        self.stopping = True
        if self.config['engine'].get('profile') in (PROFILE, VM_PROFILE, DEVELOPMENT_PROFILE): await self.development.stop_owned()
        if self.client and self.turn_id:
            try: await self.client.request('turn/interrupt', {'threadId': self.thread_id, 'turnId': self.turn_id}, timeout=5)
            except Exception: pass
        if not self.done.is_set():
            if self.outcome not in ('completed', 'failed'): self.outcome = 'unknown' if self.uncertain_effect else 'interrupted'
            self.done.set()

    async def cleanup(self):
        await self.build_snapshots.close()
        if self.client: await self.client.close()
        await self.terminals.close()

    async def run(self):
        if not self.row['busy']: return
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
        try:
            if self.row['state'] == 'stopping': self.outcome = 'interrupted'; return
            self.lease = (self.store.projects / '.studio' / ('workspace-' + self.manifest['projectId'] + '.lock')).open('a')
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            await self.build_snapshots.start()
            transition(self.store, self.run_id, 'starting', worker={'release': self.manifest['release'], 'pid': os.getpid(), 'birth': __import__('lease').birth(os.getpid())})
            state = self.store.directory / self.session_id / 'Codex'
            provider_home = Path(self.manifest['providers']) / self.config['providerId']
            binary = Path(self.manifest['r4os']) / 'Toolchains/Codex' / self.config['engine']['version'] / 'codex'
            args, profile = prepare(binary, provider_home, state,
                                    json.loads((Path(__file__).parent / 'features.json').read_text()), self.config['model'], self.config['providerId'], self.config['engine'].get('profile', PROFILE),
                                    fast_mode=self.config.get('fastMode', False))
            from instructions import compose
            instructions = compose(self.config)
            if 'complete_development_job' in tools_for(self.config['engine']['profile']):
                instructions += '\n\nSTUDIO CHECK LIFECYCLE: Image assessment alone leaves the bounded process running. After all configured test criteria pass, explicitly call studio_complete_development_job and wait for its cleanup receipt before reporting the full test complete. Never complete a plain interactive launch unless the user requested the test to finish. Unknown closure must not be repeated.'
            self.client = CodexRPC(args, self.notify, self.tool)
            self.client.version = self.manifest['version']
            await self.client.start()
            self.thread_id = self.store.row(self.session_id)['thread_id']
            # Explicit default clears a Fast tier saved by an earlier native turn.
            service_tier = 'priority' if self.config.get('fastMode', False) else 'default'
            if self.thread_id:
                try: await self.client.request('thread/resume', {'threadId': self.thread_id, 'cwd': '/workspace', 'excludeTurns': True, 'model': self.config['model'], 'serviceTier': service_tier, 'baseInstructions': instructions, 'sandbox': SANDBOX_MODE, 'approvalPolicy': 'never'})
                except Exception:
                    self.error = 'The saved conversation could not be resumed. Its files were preserved.'; raise
            else:
                response = await self.client.request('thread/start', {'cwd': '/workspace', 'model': self.config['model'], 'serviceTier': service_tier,
                           'ephemeral': False, 'dynamicTools': specifications(self.config['engine'].get('profile', PROFILE)), 'baseInstructions': instructions,
                           'sandbox': SANDBOX_MODE, 'approvalPolicy': 'never'})
                self.thread_id = response['thread']['id']
                with self.store.db:
                    self.store.db.execute('UPDATE sessions SET thread_id=? WHERE id=?', (self.thread_id, self.session_id))
            if self.stopping: self.outcome = 'interrupted'; return
            self.turn_requested = True
            try:
                result = await self.client.request('turn/start', {'threadId': self.thread_id,
                             'clientUserMessageId': self.row['request_id'], 'input': [{'type': 'text', 'text': request_text(self.store, self.run_id)}],
                             'model': self.config['model'], 'effort': self.config['effort'], 'serviceTier': service_tier})
                self.turn_id = result['turn']['id']
                if not self.done.is_set(): transition(self.store, self.run_id, 'running', turn_id=self.turn_id,
                                                       worker={'release': self.manifest['release'], 'pid': os.getpid(), 'birth': __import__('lease').birth(os.getpid()), 'profile': profile})
            except asyncio.TimeoutError:
                # A missing RPC reply does not negate a native started/completed
                # event. Continue observing this one turn; never send it again.
                if not self.turn_id and not self.done.is_set():
                    self.uncertain_effect = True; self.outcome = 'unknown'
                    self.error = 'The run start was not confirmed. It was not submitted again.'
                    await self.stop()
            await asyncio.wait_for(self.done.wait(), timeout=1800)
        except asyncio.TimeoutError:
            self.error = 'The agent run reached the host time limit.'; await self.stop()
        except Exception:
            if self.outcome == 'unknown':
                self.outcome = 'unknown' if self.turn_requested else 'failed'
            self.error = self.error or 'The agent service could not confirm this run. Existing data was preserved.'
        finally:
            await self.cleanup()
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
    store = SessionStore(manifest['projects'], manifest['r4os'], manifest['projectId'])
    try:
        row = get_run(store, manifest['runId'])
        if row['busy']:
            stopped = row['state'] == 'stopping'
            state = 'interrupted' if stopped else ('failed' if row['state'] == 'queued' else 'unknown')
            reconcile_items(store, row['id'], state)
            transition(store, row['id'], state, 'Run stopped.' if stopped else 'The run service exited without a confirmed result; tool effects were not repeated.')
    finally: store.close()


if __name__ == '__main__':
    if os.getuid() == 0: raise SystemExit('Agent workers must run as the unprivileged Studio service user.')
    os.umask(0o077)
    path = Path(sys.argv[1]).absolute()
    if path.resolve(strict=True) != path: raise SystemExit('Invalid worker manifest.')
    manifest = json.loads(path.read_text())
    if len(sys.argv) > 2 and sys.argv[2] == '--finalize': finalize(manifest)
    else: asyncio.run(Worker(manifest).run())
