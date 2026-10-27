"""Trusted worker harness: one admission, original-job observation and own Stop."""
import asyncio
import json
import os
from pathlib import Path
from profile import REMOTE_PROFILE
from session_store import encode
from run_store import item
from store import ProjectFault

SOCKET_PATH = '/run/r4os-studio-remote/agent.sock'

class RemoteTools:
    def __init__(self, worker): self.worker = worker

    def frame(self):
        worker = self.worker
        if (worker.store.owner_type != 'project' or worker.config.get('owner') != {'type': 'project', 'id': worker.store.project_id}
                or worker.config.get('engine', {}).get('profile') != REMOTE_PROFILE or worker.lease is None or worker.lease.closed):
            raise ProjectFault('This conversation has no active project Remote Host lease.', 403)
        birth = (Path('/proc') / str(os.getpid()) / 'stat').read_text().rsplit(') ', 1)[1].split()[19]
        return {'protocol': 1, 'projectId': worker.store.project_id,
                'actor': {'sessionId': worker.session_id, 'runId': worker.run_id, 'workerPid': os.getpid(), 'workerBirth': birth,
                          'release': worker.manifest['release'], 'revision': worker.config['revision']}}

    @staticmethod
    def summary(value):
        result = value.get('result') or {}
        return {**{k: value[k] for k in ('id', 'requestId', 'hostId', 'hostName', 'operation', 'state', 'phase', 'deadlineAt', 'binding', 'stopRequested', 'remoteProcessEndConfirmed') if k in value},
                **{k: result[k] for k in ('localClientEndConfirmed', 'remoteProcessEndConfirmed', 'commandReturnConfirmed', 'commandExitCode') if k in result}}

    def progress(self, name, arguments, call_id, value):
        worker = self.worker
        card = {'id': call_id, 'runId': worker.run_id, 'type': 'tool', 'tool': 'studio.' + name,
                'arguments': arguments, 'status': 'running', 'remote': self.summary(value)}
        worker.items[call_id] = card; item(worker.store, worker.session_id, worker.run_id, card)

    async def invoke(self, frame, stream=False, progress=None):
        worker = self.worker; descriptor = worker.lease.fileno()
        helper = Path(__file__).resolve().parents[1] / 'remote-hosts/agent_call.py'
        # The socket path is fixed host configuration, never model input.
        path = SOCKET_PATH
        process = await asyncio.create_subprocess_exec('/usr/bin/python3', '-B', str(helper), path, str(descriptor),
            *(['--wait', '--stream'] if stream else []), pass_fds=(descriptor,), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=262144,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        try:
            process.stdin.write(encode(frame).encode()); await process.stdin.drain(); process.stdin.close()
            async def receive():
                response = None; frames = 0
                while raw := await process.stdout.readline():
                    frames += 1
                    if len(raw) > 260000 or frames > 1024: raise ValueError()
                    value = json.loads(raw)
                    if 'progress' in value:
                        if progress: progress(value['progress'])
                    else: response = value
                await process.wait()
                if response is None: raise ValueError()
                return response
            return await asyncio.wait_for(receive(), 150 if stream else 20)
        finally:
            if process.returncode is None: process.kill(); await process.wait()

    async def call(self, name, arguments, call_id):
        worker = self.worker; frame = {**self.frame(), 'operation': 'tool', 'tool': name, 'callId': call_id, 'arguments': arguments}
        if worker.config['permissions'].get('studio.' + name) is not True:
            return {'success': False, 'error': 'disabled', 'output': 'This run’s Remote Host permission is disabled.'}
        if name == 'remote_files':
            # Share local file/terminal admission locks with existing file tools.
            async with worker.terminals.lock:
                async with worker.sandbox.lock:
                    if any(not process.finished.is_set() for process in worker.terminals.processes.values()):
                        return {'success': False, 'error': 'busy', 'output': 'Finish this run’s terminal processes before a remote file transfer.'}
                    return await self.perform(frame, name, arguments, call_id)
        return await self.perform(frame, name, arguments, call_id)

    async def perform(self, frame, name, arguments, call_id):
        mutating = name == 'run_remote_command' or (name == 'remote_files' and arguments.get('action') in ('upload', 'download'))
        try: response = await self.invoke(frame, stream=name in ('run_remote_command', 'remote_files'), progress=lambda value: self.progress(name, arguments, call_id, value))
        except (OSError, ValueError, asyncio.TimeoutError):
            response = {'error': 'The original Remote Host receipt could not be read. Preserve its requestId; do not repeat a possible effect.', 'code': 503}
        if response.get('error'):
            code = response.get('code', 503); uncertain = mutating and code >= 500
            return {'success': False, 'error': 'unknown' if uncertain else 'denied' if code == 403 else 'conflict' if code == 409 else 'unavailable',
                    'output': response['error'], 'remote': {'requestId': arguments.get('requestId'), 'operation': name, 'code': code},
                    **({'partialChangesPossible': True} if uncertain else {})}
        value = response['result']; summary = self.summary(value)
        if name == 'get_remote_host':
            return {'success': value.get('available', False), 'output': encode(value), 'remote': summary,
                    **({'error': 'unavailable'} if not value.get('available', False) else {})}
        unknown = value.get('state') == 'unknown' and name in ('run_remote_command', 'remote_files')
        failed = value.get('state') == 'failed' and name in ('run_remote_command', 'remote_files')
        running = value.get('state') in ('queued', 'starting', 'running', 'stopping') and name in ('run_remote_command', 'remote_files')
        result = {'success': not (unknown or failed or running), 'output': encode(value), 'remote': summary}
        if unknown or running: result.update(error='unknown', partialChangesPossible=mutating)
        elif failed: result['error'] = 'failed'
        if (value.get('result') or {}).get('commandExitCode') is not None: result['exitCode'] = value['result']['commandExitCode']
        return result

    async def stop_owned(self):
        if not self.worker.config.get('remoteHostBinding'): return {'result': {'jobIds': [], 'stopRequested': False}}
        try: return await self.invoke({**self.frame(), 'operation': 'stop_owned'})
        except Exception: return {'error': 'The original remote stop receipt could not be confirmed. Remote effects remain unconfirmed.'}
