"""Seven fixed broker calls; no VM credential, path or command reaches the model."""
import json
from pathlib import Path
import uuid
import asyncio


class DevelopmentTools:
    def __init__(self, worker): self.worker = worker

    async def request(self, operation, **fields):
        from vm_worker import broker_call
        from contracts import DevelopmentFault, UnconfirmedGuestEffect
        worker = self.worker
        try:
            return await broker_call({'operation': operation, 'projectId': worker.manifest['projectId'],
                'owner': {'sessionId': worker.session_id, 'agentRunId': worker.run_id}, **fields})
        except (OSError, asyncio.TimeoutError):
            if operation in ('build', 'deploy', 'execution', 'capture', 'input', 'assess', 'stop_job', 'cancel_owned'):
                raise UnconfirmedGuestEffect('The development request receipt was lost. It was not replayed.') from None
            raise DevelopmentFault('The development coordinator is unavailable.', 503) from None

    def image_capable(self):
        worker = self.worker
        try:
            models = json.loads((worker.store.directory / worker.session_id / 'Codex/models.json').read_text())['models']
            return 'image' in next(v for v in models if v['slug'] == worker.config['model']).get('input_modalities', [])
        except (OSError, ValueError, KeyError, StopIteration): return False

    async def native_output(self, result):
        from session_store import encode
        content = [{'type': 'inputText', 'text': encode(result)}]
        if result.get('image'):
            if not self.image_capable() or not self.worker.config['permissions'].get('studio.capture_vm'):
                return {'success': False, 'contentItems': [{'type': 'inputText', 'text': 'Image inspection is unavailable for this model or permission.'}]}
            image = result['image']
            data = await self.request('evidence', id=image['jobId'], evidenceId=image['id'])
            if data['metadata']['sha256'] != image['sha256']: raise ValueError('Image identity changed.')
            # Transient RPC image only. Durable tools/events retain opaque refs.
            content.append({'type': 'inputImage', 'imageUrl': 'data:image/png;base64,' + data['base64']})
        return {'success': result['success'], 'contentItems': content}

    async def call(self, name, value, call_id):
        from contracts import DevelopmentFault
        from session_store import encode
        request_id = str(uuid.uuid5(uuid.UUID(self.worker.run_id), 'development:' + call_id))
        try:
            if name in ('build_project', 'deploy_project', 'run_project'):
                settings = await self.request('settings')
                from jobs import Jobs
                store = Jobs(self.worker.manifest['projects'], self.worker.manifest['r4os'], self.worker.manifest['projectId'])
                try: revision = store.project['revision']
                finally: store.close()
                body = {'requestId': request_id, 'projectRevision': revision, 'settingsRevision': settings['revision']}
                operation = {'build_project': 'build', 'deploy_project': 'deploy', 'run_project': 'execution'}[name]
                if name == 'deploy_project': body['artifactId'] = value['artifactId']
                if name == 'run_project':
                    body['deploymentId'] = value['deploymentId']
                    overrides = {k: value[k] for k in ('arguments', 'timeoutSeconds') if k in value}
                    overrides.update(value.get('criteria', {}))
                    if overrides: body['overrides'] = overrides
                job = await self.request(operation, input=body)
                return self.result(job)
            if name == 'read_development_job':
                await asyncio.sleep(value.get('waitMilliseconds', 0) / 1000)
                page = await self.request('read_job', id=value['jobId'], offset=value.get('offset', 0))
                return self.result(page['job'], page)
            if name == 'stop_development_job': return self.result(await self.request('stop_job', id=value['jobId']))
            if name == 'capture_vm':
                if not self.image_capable(): raise DevelopmentFault('This model has no confirmed native image capability. Choose an image-capable model.', 409)
                if value.get('action', 'capture') == 'assess':
                    if set(value) != {'jobId', 'action', 'evidenceId', 'state', 'notes'}: raise DevelopmentFault('Provide image ID, state and notes for assessment.', 400)
                    job = await self.request('assess', id=value['jobId'], input={'requestId': request_id,
                        'evidenceId': value['evidenceId'], 'state': value['state'], 'notes': value['notes']})
                    return self.result(job)
                if set(value) - {'jobId', 'action'}: raise DevelopmentFault('Unexpected capture fields.', 400)
                data = await self.request('capture', id=value['jobId'], input={'requestId': request_id})
                metadata = data['metadata']
                return {'success': True, 'output': encode(metadata), 'development': {'jobId': value['jobId']}, 'image': metadata}
            if name == 'send_vm_input':
                data = await self.request('input', id=value['jobId'], input={'requestId': request_id, 'input': {k: v for k, v in value.items() if k != 'jobId'}})
                return {'success': True, 'output': encode(data), 'development': {'jobId': value['jobId']}}
            raise DevelopmentFault('Unknown development tool.', 400)
        except DevelopmentFault as error:
            return {'success': False, 'error': 'unknown' if getattr(error, 'uncertain', False) else 'unavailable', 'output': str(error)}

    def result(self, job, page=None):
        from session_store import encode
        if job.get('source'): job['source'] = {k: v for k, v in job['source'].items() if k not in ('files', 'directories')}
        uncertain = job['state'] == 'unknown' and not (job.get('guestState') or {}).get('closeConfirmed')
        return {'success': not uncertain, **({'error': 'unknown'} if uncertain else {}), 'output': encode(page or {'job': job}), 'development': {'jobId': job['id'], 'kind': job['kind'], 'state': job['state']}}

    async def stop_owned(self):
        try: await self.request('cancel_owned')
        except Exception: pass  # The independently bounded worker/watchdog still owns cleanup.
