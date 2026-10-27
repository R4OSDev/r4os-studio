"""Bound Roadmap subprocess outside model, terminal and build namespaces."""
import asyncio
import json
from pathlib import Path
from roadmap_access import require
from session_store import encode


class RoadmapTools:
    def __init__(self, worker): self.worker = worker

    async def call(self, name, arguments, call_id):
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
            raw, _ = await asyncio.wait_for(process.communicate(encode({'tool': name, 'callId': call_id, 'arguments': arguments}).encode()), 30)
            if len(raw) > 131072: raise ValueError('Roadmap result exceeded its limit.')
            response = json.loads(raw)
            if response.get('error'):
                code = response.get('code', 503)
                uncertain = name == 'update_roadmap' and code >= 500
                return {'success': False, 'error': 'unknown' if uncertain else 'conflict' if code == 409 else 'denied' if code == 403 else 'failed',
                        'output': response['error'], 'roadmap': {'operation': name, 'code': code, 'requestId': arguments.get('requestId')},
                        **({'partialChangesPossible': True} if uncertain else {})}
            value = response['result']
            summary = {'operation': name, 'requestId': arguments.get('requestId'), **{k: value[k] for k in ('revision', 'currentVersionId', 'requestId', 'versionId', 'sha256') if k in value}}
            if value.get('available') is False:
                return {'success': False, 'error': 'unavailable', 'output': value['message'], 'roadmap': summary}
            return {'success': True, 'output': encode(value), 'roadmap': summary}
        finally:
            if process.returncode is None: process.kill(); await process.wait()
