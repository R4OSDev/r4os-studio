"""Bound Roadmap subprocess outside model, terminal and build namespaces."""
import asyncio
import json
from pathlib import Path
import uuid
from roadmap_access import require
from session_store import encode


class RoadmapTools:
    def __init__(self, worker): self.worker = worker

    async def call(self, name, arguments, call_id):
        if name == 'cleanup_roadmap' and arguments.get('action') != 'status':
            async with self.worker.terminals.lock:
                async with self.worker.workspace_tools.lock:
                    if any(not process.finished.is_set() for process in self.worker.terminals.processes.values()):
                        return {'success': False, 'error': 'busy', 'output': 'Finish this run’s terminal processes before preparing cleanup.'}
                    return await self.invoke(name, arguments, call_id)
        return await self.invoke(name, arguments, call_id)

    async def invoke(self, name, arguments, call_id):
        worker = self.worker
        require(worker)
        if worker.lease is None or worker.lease.closed:
            return {'success': False, 'error': 'denied', 'output': 'The original workspace lease is unavailable.'}
        helper = Path(__file__).resolve().parents[1] / 'project-roadmaps/agent_adapter.py'
        descriptor = worker.lease.fileno()
        process = await asyncio.create_subprocess_exec('/usr/bin/python3', '-B', str(helper),
            str(worker.store.projects), worker.store.project_id, worker.session_id, worker.run_id,
            str(descriptor), worker.manifest['release'], pass_fds=(descriptor,),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}, limit=131072)
        try:
            raw, _ = await asyncio.wait_for(process.communicate(encode({'tool': name, 'callId': call_id, 'arguments': arguments}).encode()),
                                            260 if name == 'finish_github_issue' else 30)
            if len(raw) > 131072: raise ValueError('Roadmap result exceeded its limit.')
            response = json.loads(raw)
            if response.get('error'):
                code = response.get('code', 503)
                uncertain = (name in ('update_roadmap','finish_github_issue') or (name == 'cleanup_roadmap' and arguments.get('action') != 'status')) and code >= 500
                reason = 'unknown' if uncertain else {403: 'denied', 409: 'conflict'}.get(code, 'failed')
                if code == 400 and name == 'update_roadmap': reason = 'invalidArguments'
                if name == 'finish_github_issue':
                    request_id = str(uuid.uuid5(uuid.UUID(worker.run_id), 'finish-github-issue:' + call_id))
                    return {'success':False,'error':reason,'output':response['error'],
                            'roadmap':{'operation':name,'requestId':request_id,'code':code},
                            **({'partialChangesPossible':True} if uncertain else {})}
                return {'success': False, 'error': reason,
                        'output': response['error'], 'roadmap': {'operation': name, 'code': code, 'requestId': arguments.get('requestId')},
                        **({'partialChangesPossible': True} if uncertain else {})}
            value = response['result']
            if name == 'finish_github_issue':
                completed = value.get('state') == 'complete'
                return {'success':completed,'output':encode(value),'githubIssue':value,
                        **({} if completed else {'error':'incomplete','partialChangesPossible':True})}
            summary = {'operation': name, 'requestId': arguments.get('requestId'), **{k: value[k] for k in ('workflowId', 'phase', 'revision', 'currentVersionId', 'requestId', 'versionId', 'sha256') if k in value}}
            if name == 'read_roadmap' and arguments.get('view') == 'overview' and value.get('exists'):
                summary.update({key: value['roadmap'][key] for key in ('revision', 'currentVersionId')})
            if value.get('available') is False:
                return {'success': False, 'error': 'unavailable', 'output': value['message'], 'roadmap': summary}
            return {'success': True, 'output': encode(value), 'roadmap': summary}
        finally:
            if process.returncode is None: process.kill(); await process.wait()
