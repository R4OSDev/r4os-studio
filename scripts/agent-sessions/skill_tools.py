"""Bound author calls outside the model namespace, under the active worker lease."""
import asyncio
import json
from pathlib import Path
from session_store import encode


class SkillTools:
    def __init__(self, worker): self.worker = worker

    async def call(self, name, arguments, call_id):
        worker = self.worker
        async with worker.terminals.lock:
            async with worker.sandbox.lock:
                if any(not process.finished.is_set() for process in worker.terminals.processes.values()):
                    return {'success': False, 'error': 'busy', 'output': 'Wait for this run\'s terminal processes to finish before validating or saving the skill.'}
                if worker.lease is None or worker.lease.closed: raise ValueError('The author workspace lease is unavailable.')
                helper = Path(__file__).resolve().parents[1] / 'skills/author.py'
                data = {**arguments, **({'callId': call_id} if name == 'save_skill' else {})}
                fd = worker.lease.fileno()
                process = await asyncio.create_subprocess_exec('/usr/bin/python3', '-B', str(helper),
                    str(worker.store.projects), worker.store.owner_id, worker.session_id, worker.run_id, str(fd), name, '/usr/bin/node',
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    pass_fds=(fd,), env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}, limit=2 * 1024 * 1024)
                try:
                    raw, _ = await asyncio.wait_for(process.communicate(encode(data).encode()), 15)
                    if len(raw) > 2 * 1024 * 1024: raise ValueError('The author response exceeded its limit.')
                    response = json.loads(raw)
                    if response.get('error'):
                        code = response.get('code')
                        if code == 503: raise ValueError('The author effect was not confirmed.')
                        return {'success': False, 'error': 'conflict' if code == 409 else 'denied' if code == 403 else 'invalid', 'output': response['error']}
                    if process.returncode: raise ValueError('The author effect was not confirmed.')
                    value = response['result']; validation = value['validation']; saved = value.get('saved') is True
                    summary = {'id': value['skill']['id'], 'revision': value['skill']['revision'], 'draftHash': value['draftHash'],
                        'activeRevision': value['skill']['activeRevision'], 'activeHash': value['skill']['activeHash'],
                        'validated': validation['valid'], 'saved': saved, 'errors': validation['errors']}
                    output = {'skill': summary, 'files': value['files'], 'validation': validation}
                    return {'success': validation['valid'] and (name != 'save_skill' or saved),
                        **({'error': 'validation'} if not validation['valid'] else {}), 'output': encode(output), 'skill': summary, 'files': value['files']}
                finally:
                    if process.returncode is None: process.kill(); await process.wait()
