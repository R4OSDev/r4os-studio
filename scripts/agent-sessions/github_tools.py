"""Project-only Git sidecar outside the model/terminal namespace; inherits the existing run lock."""
import asyncio
import json
from pathlib import Path
import uuid
import re
from session_store import encode
from run_store import item


def publication_receipt(job, request_id, project_id):
    """Qualify the original host receipt; never retry a commit or infer publication."""
    github = {'id': request_id, 'projectId': project_id, 'state': 'pending'}
    if not isinstance(job, dict) or job.get('id') != request_id or job.get('projectId') != project_id or job.get('kind') != 'push':
        return {'success': False, 'error': 'unknown', 'output': 'The original Git receipt could not be matched. Inspect this request before another Git effect.', 'github': github, 'partialChangesPossible': True}
    result = job.get('result') or {}
    if not isinstance(result, dict): result = {}
    commit, remote = result.get('commit'), result.get('remoteHead')
    commit_known = isinstance(commit, str) and re.fullmatch('[a-f0-9]{40}', commit) is not None
    remote_known = isinstance(remote, str) and re.fullmatch('[a-f0-9]{40}', remote) is not None
    # The original host also confirms an ancestor commit when another writer
    # advanced the branch. Different remoteHead alone does not undo that proof.
    pushed = job.get('state') == 'completed' and result.get('pushed') is True and commit_known and remote_known
    nothing = job.get('state') == 'completed' and result.get('nothingToPush') is True and result.get('pushed') is not True and commit == remote and (commit_known or commit is None)
    github.update(state=job.get('state'), phase=job.get('phase'), commit=commit, remoteHead=remote, pushed=pushed, nothingToPush=nothing)
    success = pushed or nothing
    unconfirmed = job.get('state') == 'unknown' or (result.get('pushed') is True and not pushed)
    output = 'Push confirmed.' if pushed else 'Nothing to push. No empty commit was created.' if nothing else 'No commit or push was published. Review the original Git job.' if result.get('notPublished') else job.get('error') or 'Publication remains unconfirmed. Review the original Git job before another push.'
    return {'success': success, 'output': output + '\n' + encode(github), 'github': github,
            **({} if success else {'error': 'unknown' if unconfirmed else 'notPushed'}), **({'partialChangesPossible': True} if unconfirmed else {})}


class GitHubTools:
    def __init__(self, worker): self.worker = worker

    async def call(self, arguments, call_id):
        worker = self.worker
        async with worker.terminals.lock:
            async with worker.sandbox.lock:
                if any(not process.finished.is_set() for process in worker.terminals.processes.values()):
                    return {'success': False, 'error': 'busy', 'output': 'Finish this run’s terminal processes before pushing.'}
                if worker.lease is None or worker.lease.closed: raise ValueError('The project workspace lease is unavailable.')
                request_id = str(uuid.uuid5(uuid.UUID(worker.run_id), 'github:' + call_id))
                github = {'id': request_id, 'projectId': worker.store.project_id, 'state': 'pending'}
                value = {'id': call_id, 'runId': worker.run_id, 'type': 'tool', 'tool': 'studio.push_project', 'arguments': arguments, 'status': 'pending', 'github': github}
                worker.items[call_id] = value; item(worker.store, worker.session_id, worker.run_id, value)
                helper = Path(__file__).resolve().parents[1] / 'project-git/agent_push.py'; descriptor = worker.lease.fileno()
                process = await asyncio.create_subprocess_exec('/usr/bin/python3', '-B', str(helper), str(worker.store.projects), worker.store.project_id, worker.session_id, worker.run_id, str(descriptor),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, pass_fds=(descriptor,), env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}, limit=2 * 1024**2)
                try:
                    raw, _ = await asyncio.wait_for(process.communicate(encode({**arguments, 'callId': call_id}).encode()), 340)
                    if len(raw) > 2 * 1024**2: raise ValueError('Git broker output exceeded its limit.')
                    response = json.loads(raw)
                    if response.get('error'):
                        code = response.get('code', 503)
                        return {'success': False, 'error': 'unknown' if code >= 500 else 'busy' if code == 409 else 'denied', 'output': response['error'], 'github': github, **({'partialChangesPossible': True} if code >= 500 else {})}
                    return publication_receipt(response['result'], request_id, worker.store.project_id)
                finally:
                    if process.returncode is None:
                        process.kill(); await process.wait()
                        try:
                            reader, writer = await asyncio.wait_for(asyncio.open_unix_connection('/run/r4os-studio-git/control.sock'), 5)
                            writer.write((encode({'operation': 'cancel', 'projectId': worker.store.project_id, 'requestId': request_id}) + '\n').encode()); await writer.drain()
                            await asyncio.wait_for(reader.readline(), 5); writer.close(); await writer.wait_closed()
                        except Exception: pass
