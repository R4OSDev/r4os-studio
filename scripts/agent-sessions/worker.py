#!/usr/bin/env python3
"""One systemd-owned run; independent of the web app and host coordinator."""
import asyncio
import fcntl
import json
import os
from pathlib import Path
import signal
import sys

from profile import prepare, write_json, TOOLS
from session_store import SessionStore, encode, now
from run_store import get_run, transition, event, item, request_text
from codex_rpc import CodexRPC
from tool_catalog import specifications


class Worker:
    def __init__(self, manifest):
        self.manifest = manifest
        self.store = SessionStore(manifest['projects'], manifest['r4os'], manifest['projectId'])
        self.run_id = manifest['runId']; self.row = get_run(self.store, self.run_id)
        self.session_id = self.row['session_id']; self.config = json.loads(self.row['config'])
        self.client = None; self.turn_id = None; self.thread_id = None
        self.done = asyncio.Event(); self.stopping = False; self.outcome = 'unknown'; self.error = None
        self.items = {}; self.lease = None

    async def notify(self, method, params):
        if params.get('threadId') and params['threadId'] != self.thread_id: return
        if method == 'turn/started':
            self.turn_id = params['turn']['id']
            transition(self.store, self.run_id, 'running', turn_id=self.turn_id)
        elif method == 'turn/completed':
            status = params['turn']['status']
            self.outcome = {'completed': 'completed', 'failed': 'failed', 'interrupted': 'interrupted'}.get(status, 'unknown')
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
        # Subsequent tool releases implement these handlers. Declarations remain
        # stable on native thread resume, but an absent handler never executes.
        return {'success': False, 'error': 'unavailable', 'output': 'This tool is not available in this Studio release.'}

    async def tool(self, params):
        def output(result):
            return {'success': result['success'], 'contentItems': [{'type': 'inputText', 'text': encode(result)}]}
        name = params.get('tool', '')
        if (not name.startswith('studio_') or name[7:] not in TOOLS or params.get('namespace') is not None
            or params.get('threadId') != self.thread_id or params.get('turnId') != self.turn_id):
            return output({'success': False, 'error': 'invalidCall', 'output': 'This call does not belong to the active Studio run.'})
        call_id = params['callId']; arguments = params['arguments']
        if not isinstance(arguments, dict) or len(encode(arguments).encode()) > 131072:
            return output({'success': False, 'error': 'invalidArguments', 'output': 'Invalid tool arguments.'})
        import hashlib
        hashed = hashlib.sha256(encode({'tool': name, 'arguments': arguments}).encode()).hexdigest()
        previous = self.store.db.execute('SELECT * FROM tools WHERE run_id=? AND call_id=?', (self.run_id, call_id)).fetchone()
        if previous:
            if previous['arguments_hash'] != hashed:
                return output({'success': False, 'error': 'conflict', 'output': 'Tool call ID has different arguments.'})
            if previous['result']: return output(json.loads(previous['result']))
            return output({'success': False, 'error': 'unknown', 'output': 'The previous tool outcome is unconfirmed; it was not repeated.'})
        with self.store.db:
            self.store.db.execute('INSERT INTO tools VALUES (?,?,?,?,?,?,NULL)',
                                  (self.run_id, call_id, name, hashed, 'intent', encode(arguments)))
        tool_id = name.replace('studio_', 'studio.', 1)
        if self.stopping or not get_run(self.store, self.run_id)['busy']:
            result = {'success': False, 'error': 'interrupted', 'output': 'The run is stopping.'}
        elif not self.config['permissions'].get(tool_id, False):
            result = {'success': False, 'error': 'disabled', 'output': 'This tool call is disabled in session settings.'}
        else:
            try: result = await self.execute(name[7:], arguments, call_id)
            except asyncio.CancelledError: result = {'success': False, 'error': 'interrupted', 'output': 'The tool was interrupted; partial effects may remain.'}
            except Exception: result = {'success': False, 'error': 'failed', 'output': 'The project tool could not complete.'}
        with self.store.db:
            self.store.db.execute('UPDATE tools SET state=?,result=? WHERE run_id=? AND call_id=?',
                                  ('completed' if result['success'] else 'failed', encode(result), self.run_id, call_id))
        value = {'id': call_id, 'runId': self.run_id, 'type': 'tool', 'tool': tool_id, 'arguments': arguments,
                 'status': 'completed' if result['success'] else ('denied' if result.get('error') == 'disabled' else 'failed'),
                 'output': result.get('output', ''), 'error': result.get('error')}
        if 'exitCode' in result: value['exitCode'] = result['exitCode']
        self.items[call_id] = value; item(self.store, self.session_id, self.run_id, value)
        return output(result)

    async def stop(self):
        self.stopping = True
        if self.client and self.turn_id:
            try: await self.client.request('turn/interrupt', {'threadId': self.thread_id, 'turnId': self.turn_id}, timeout=5)
            except Exception: pass
        if not self.done.is_set():
            if self.outcome not in ('completed', 'failed'): self.outcome = 'interrupted'
            self.done.set()

    async def cleanup(self):
        if self.client: await self.client.close()

    async def run(self):
        if not self.row['busy']: return
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
        try:
            if self.row['state'] == 'stopping': self.outcome = 'interrupted'; return
            self.lease = (self.store.projects / '.studio' / ('workspace-' + self.manifest['projectId'] + '.lock')).open('a')
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            transition(self.store, self.run_id, 'starting', worker={'release': self.manifest['release'], 'pid': os.getpid()})
            state = self.store.directory / self.session_id / 'Codex'
            provider_home = Path(self.manifest['providers']) / self.config['providerId']
            binary = Path(self.manifest['r4os']) / 'Toolchains/Codex' / self.config['engine']['version'] / 'codex'
            args, profile = prepare(binary, provider_home, state,
                                    json.loads((Path(__file__).parent / 'features.json').read_text()), self.config['model'])
            self.client = CodexRPC(args, self.notify, self.tool)
            self.client.version = self.manifest['version']
            await self.client.start()
            self.thread_id = self.store.row(self.session_id)['thread_id']
            if self.thread_id:
                await self.client.request('thread/resume', {'threadId': self.thread_id, 'cwd': '/workspace', 'excludeTurns': True, 'model': self.config['model']})
            else:
                response = await self.client.request('thread/start', {'cwd': '/workspace', 'model': self.config['model'],
                           'ephemeral': False, 'dynamicTools': specifications()})
                self.thread_id = response['thread']['id']
                with self.store.db:
                    self.store.db.execute('UPDATE sessions SET thread_id=? WHERE id=?', (self.thread_id, self.session_id))
            if self.stopping: self.outcome = 'interrupted'; return
            result = await self.client.request('turn/start', {'threadId': self.thread_id,
                         'clientUserMessageId': self.row['request_id'], 'input': [{'type': 'text', 'text': request_text(self.store, self.run_id)}],
                         'model': self.config['model'], 'effort': self.config['effort']})
            self.turn_id = result['turn']['id']
            if not self.done.is_set(): transition(self.store, self.run_id, 'running', turn_id=self.turn_id,
                                                   worker={'release': self.manifest['release'], 'pid': os.getpid(), 'profile': profile})
            await asyncio.wait_for(self.done.wait(), timeout=1800)
        except asyncio.TimeoutError:
            self.error = 'The agent run reached the host time limit.'; await self.stop()
        except Exception:
            if self.outcome == 'unknown':
                self.outcome = 'unknown' if self.turn_id else 'failed'
            self.error = self.error or 'The agent service could not confirm this run. Existing data was preserved.'
        finally:
            await self.cleanup()
            if self.lease: self.lease.close()
            transition(self.store, self.run_id, self.outcome, self.error)
            self.store.close()


def finalize(manifest):
    store = SessionStore(manifest['projects'], manifest['r4os'], manifest['projectId'])
    try:
        row = get_run(store, manifest['runId'])
        if row['busy']:
            stopped = row['state'] == 'stopping'
            state = 'interrupted' if stopped else ('failed' if row['state'] == 'queued' else 'unknown')
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
