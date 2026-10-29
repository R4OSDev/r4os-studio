"""Fixed broker calls; VM startup waits in the harness, outside model inference."""
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
            if operation in ('build', 'deploy', 'execution', 'vm_start', 'capture', 'input', 'assess', 'stop_job', 'complete_check', 'cancel_owned', 'update_plan', 'package', 'update_probe', 'update_transfer', 'update_install', 'update_commit', 'update_recovery'):
                raise UnconfirmedGuestEffect('The development request receipt was lost. It was not replayed.') from None
            raise DevelopmentFault('The development coordinator is unavailable.', 503) from None

    def image_capable(self):
        worker = self.worker
        try:
            models = json.loads((worker.store.directory / worker.session_id / 'Codex/models.json').read_text())['models']
            return 'image' in next(v for v in models if v['slug'] == worker.config['model']).get('input_modalities', [])
        except (OSError, ValueError, KeyError, StopIteration): return False

    async def native_output(self, result, image_data=None):
        from session_store import encode
        content = [{'type': 'inputText', 'text': encode(result)}]
        if result.get('image'):
            if not self.image_capable() or not self.worker.config['permissions'].get('studio.capture_vm'):
                return {'success': False, 'contentItems': [{'type': 'inputText', 'text': 'Image inspection is unavailable for this model or permission.'}]}
            image = result['image']
            data = image_data if image_data is not None else await self.request('evidence', id=image['jobId'], evidenceId=image['id'])
            if data['metadata']['sha256'] != image['sha256'] or (image_data is not None and (
                data['metadata'] != image or image['projectId'] != self.worker.manifest['projectId'] or image['kind'] != 'screenshot')):
                raise ValueError('Image identity changed.')
            # Transient RPC image only. Durable tools/events retain opaque refs.
            content.append({'type': 'inputImage', 'imageUrl': 'data:image/png;base64,' + data['base64']})
        return {'success': result['success'], 'contentItems': content}

    async def call(self, name, value, call_id):
        from profile import UPDATE_TOOLS
        if name in UPDATE_TOOLS:
            from update_tools import UpdateTools
            return await UpdateTools(self).call(name,value,call_id)
        from contracts import DevelopmentFault
        from session_store import encode
        request_id = str(uuid.uuid5(uuid.UUID(self.worker.run_id), 'development:' + call_id))
        job = None
        try:
            if name in ('build_project', 'deploy_project', 'run_project', 'start_project_vm'):
                if name == 'start_project_vm':
                    from vm_worker import broker_call
                    capabilities = await broker_call({'operation': 'capabilities'})
                    if capabilities.get('features', {}).get('vmStart') != 1:
                        raise DevelopmentFault('VM start support requires development host maintenance.', 503)
                settings = await self.request('settings')
                from jobs import Jobs
                store = Jobs(self.worker.manifest['projects'], self.worker.manifest['r4os'], self.worker.manifest['projectId'])
                try: revision = store.project['revision']
                finally: store.close()
                body = {'requestId': request_id, 'projectRevision': revision, 'settingsRevision': settings['revision']}
                operation = {'build_project': 'build', 'deploy_project': 'deploy', 'run_project': 'execution', 'start_project_vm': 'vm_start'}[name]
                if name == 'deploy_project': body['artifactId'] = value['artifactId']
                if name == 'run_project':
                    body['deploymentId'] = value['deploymentId']
                    overrides = {k: value[k] for k in ('arguments', 'timeoutSeconds') if k in value}
                    overrides.update(value.get('criteria', {}))
                    if overrides: body['overrides'] = overrides
                job = await self.request(operation, input=body)
                if name == 'start_project_vm': return await self.wait_for_vm(job, call_id, value)
                if name in ('build_project', 'deploy_project', 'run_project'): return await self.wait_for_job(name, job, call_id, value)
                return self.result(job)
            if name == 'read_development_job':
                await asyncio.sleep(value.get('waitMilliseconds', 0) / 1000)
                page = await self.request('read_job', id=value['jobId'], offset=value.get('offset', 0))
                page=await self.with_artifact(page['job'],page)
                return self.result(page['job'], page)
            if name == 'complete_development_job':
                page = await self.request('complete_check', id=value['jobId'], input={'requestId': request_id})
                return self.result(page['job'], page)
            if name == 'stop_development_job':
                from vm_worker import broker_call
                capabilities = await broker_call({'operation': 'capabilities'})
                if capabilities.get('features', {}).get('stopReceipts') != 1:
                    raise DevelopmentFault('The development coordinator must adopt the installed Stop-receipt support before this call.', 503)
                stopped = await self.request('stop_job', id=value['jobId'])
                receipt = stopped.get('stopReceipt') or {}
                confirmed = (receipt.get('version') == 1 and receipt.get('jobId') == value['jobId']
                    and receipt.get('confirmed') is True and receipt.get('outcome') in ('stopped', 'already-ended', 'not-started'))
                return {'success': confirmed, **({} if confirmed else {'error': 'unknown'}),
                    'output': encode({'job': stopped, 'stop': receipt}), 'developmentStop': receipt,
                    'development': {'jobId': stopped['id'], 'kind': stopped['kind'], 'state': stopped['state']}}
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
                if metadata.get('projectId') != self.worker.manifest['projectId'] or (metadata.get('observer') or {}).get('sessionId') != self.worker.session_id:
                    raise DevelopmentFault('The screenshot does not match this session.', 403)
                reference = 'studio-image:' + metadata['jobId'] + '/' + metadata['id']
                presentation = {'reference': reference, 'markdown': '![VM screenshot](' + reference + ')',
                    'instruction': 'When the user asks to see the screenshot, include this image Markdown in your response. You may supply a descriptive alt text. The saved image is reused; do not capture again just to present it.'}
                return {'success': True, 'output': encode({**metadata, 'presentation': presentation}), 'development': {'jobId': value['jobId']}, 'image': metadata,
                    **({'_transientImage': data} if data.get('authorizedForAgentOutput') is True else {})}
            if name == 'send_vm_input':
                if value.get('observeAfterStep') is not None and not self.image_capable():
                    raise DevelopmentFault('An intermediate gesture image requires an image-capable model.', 409)
                data = await self.request('input', id=value['jobId'], input={'requestId': request_id, 'input': {k: v for k, v in value.items() if k != 'jobId'}})
                observation = data.pop('observation', None)
                return {'success': data.get('complete', True), 'output': encode(data), 'development': {'jobId': value['jobId']},
                    **({'image': observation['metadata'], '_transientImage': observation} if observation else {})}
            raise DevelopmentFault('Unknown development tool.', 400)
        except DevelopmentFault as error:
            return {'success': False, 'error': 'unknown' if getattr(error, 'uncertain', False) else 'unavailable', 'output': str(error), 'reasonCode': getattr(error, 'reason_code', None),
                    **({'development': {'jobId': job['id']}} if job else {})}

    async def wait_for_vm(self, job, call_id, arguments):
        from contracts import ACTIVE, DevelopmentFault, LIMITS, UnconfirmedGuestEffect
        from run_store import item
        worker = self.worker
        # Publish the durable job link immediately, but hold the native tool
        # response. Codex resumes this turn only after a terminal receipt.
        value = {'id': call_id, 'runId': worker.run_id, 'type': 'tool', 'tool': 'studio.start_project_vm',
                 'arguments': arguments, 'status': 'pending', 'development': {'jobId': job['id']}}
        worker.items[call_id] = value; item(worker.store, worker.session_id, worker.run_id, value)
        deadline = asyncio.get_running_loop().time() + LIMITS['vmStartTimeoutSeconds'] + 60
        while job['state'] in ACTIVE:
            if worker.stopping:
                return {'success': False, 'error': 'interrupted', 'output': 'VM readiness wait stopped. The VM may remain running.',
                        'development': {'jobId': job['id']}}
            if asyncio.get_running_loop().time() >= deadline:
                raise UnconfirmedGuestEffect('The VM start outcome could not be read before the harness deadline. Inspect the saved job; no start was repeated.')
            try: job = await self.request('wait_vm_start', id=job['id'])
            except DevelopmentFault as error:
                if error.code != 503 or getattr(error, 'uncertain', False): raise
                # Reconnect only to the read-only wait for the same job. Never
                # repeat admission or VM start after a lost coordinator reply.
                await asyncio.sleep(1)
        result = self.result(job)
        ready = job['state'] == 'completed' and (job.get('vmStart') or {}).get('ready') is True
        if not ready and result['success']:
            result.update(success=False, error='interrupted' if job['state'] == 'interrupted' else 'failed')
        return result

    async def wait_for_job(self, name, job, call_id, arguments):
        from contracts import ACTIVE, DevelopmentFault, UnconfirmedGuestEffect, LIMITS
        from run_store import item
        worker = self.worker; operation = {'build_project': 'wait_build', 'deploy_project': 'wait_deploy', 'run_project': 'wait_execution'}[name]
        value = {'id': call_id, 'runId': worker.run_id, 'type': 'tool', 'tool': 'studio.' + name,
                 'arguments': arguments, 'status': 'pending', 'development': {'jobId': job['id']}}
        worker.items[call_id] = value; item(worker.store, worker.session_id, worker.run_id, value)
        timeout = LIMITS['buildTimeoutSeconds'] + 300 if name == 'build_project' else (660 if name == 'deploy_project' else job['settings']['timeoutSeconds'] + 300)
        deadline = asyncio.get_running_loop().time() + timeout; page = None; legacy_build_wait = False
        while job['state'] in ACTIVE:
            if worker.stopping:
                return {'success': False, 'error': 'interrupted', 'output': 'Development wait stopped. Inspect the saved job for process cleanup.',
                        'development': {'jobId': job['id']}}
            if asyncio.get_running_loop().time() >= deadline:
                raise UnconfirmedGuestEffect('The original development job did not return a receipt before the harness deadline. Nothing was submitted again.')
            try:
                if legacy_build_wait:
                    await asyncio.sleep(.5); page = {'job': self.original_build(job['id'])}
                else: page = await self.request(operation, id=job['id'])
                job = page['job']
            except DevelopmentFault as error:
                if name == 'build_project' and error.code == 400 and str(error) == 'Unsupported development coordinator operation.':
                    legacy_build_wait = True; continue
                if error.code != 503 or getattr(error, 'uncertain', False): raise
                # Reconnect to the same read-only job wait only. Never resubmit.
                await asyncio.sleep(1); continue
            if name == 'run_project' and job['state'] == 'running' and ((job.get('readiness') or {}).get('state') == 'ready'
                or (job.get('readiness') or {}).get('reasonCode') == 'desktop_content_unconfirmed'):
                break
        if name=='build_project':page=await self.with_artifact(job,page)
        return self.result(job, page)

    async def with_artifact(self,job,page):
        from contracts import DevelopmentFault
        if job.get('kind')=='build' and job['state']=='completed' and job.get('artifactId'):
            artifact=await self.request('artifact',id=job['artifactId'])
            if (artifact.get('id')!=job['artifactId'] or artifact.get('buildId')!=job['id']
                    or artifact.get('projectId')!=self.worker.manifest['projectId']):
                raise DevelopmentFault('The artifact readback differs from this original project build.',409)
            page={**(page or {'job':job}),'artifact':{key:artifact[key] for key in ('id','entry','files','resourceInputs','resourceInventory') if key in artifact}}
        return page

    def original_build(self, job_id):
        """Read only this admitted build while an older host retains workers."""
        import sqlite3
        from contracts import DevelopmentFault
        from run_store import get_run
        worker = self.worker; run = get_run(worker.store, worker.run_id)
        if not run['busy'] or run['state'] != 'running' or not worker.config['permissions'].get('studio.build_project'):
            raise DevelopmentFault('The original build wait is no longer authorized.', 403)
        path = worker.store.workspace.parent / 'Development/Development.sqlite'
        if path.resolve(strict=True) != path or not path.is_file():
            raise DevelopmentFault('The original build storage is unavailable.', 503)
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try: row = db.execute('SELECT substr(payload,1,2097153) FROM jobs WHERE id=?', (job_id,)).fetchone()
        finally: db.close()
        if not row or len(row[0].encode()) > 2097152: raise DevelopmentFault('The original build receipt is unavailable.', 503)
        value = json.loads(row[0])
        if (value.get('id') != job_id or value.get('kind') != 'build' or value.get('projectId') != worker.manifest['projectId']
            or value.get('sessionId') != worker.session_id or value.get('agentRunId') != worker.run_id):
            raise DevelopmentFault('The build wait does not match its original owner.', 403)
        return value

    def result(self, job, page=None):
        from session_store import encode
        if job.get('source'): job['source'] = {k: v for k, v in job['source'].items() if k not in ('files', 'directories')}
        closure = self.closed_without_exit_status(job)
        if closure:
            return {'success': False, 'error': 'exit_status_unavailable', 'reasonCode': 'guest_exit_status_unavailable',
                    'output': encode({**(page or {'job': job}), 'executionReceipt': closure,
                        'notice': 'The owned process has ended and its cleanup is confirmed. Its exit status is unavailable; '
                            'the execution remains unknown, not successful. Inspect the saved checks and evidence before continuing. '
                            'Do not repeat the launch merely because its exit code is missing.'}),
                    'development': {'jobId': job['id'], 'kind': job['kind'], 'state': job['state']}}
        failure = job['state'] in ('failed', 'interrupted', 'unknown')
        if job['state'] == 'running' and (job.get('readiness') or {}).get('reasonCode') == 'desktop_content_unconfirmed':
            return {'success': False, 'error': 'readiness_unknown', 'output': encode(page or {'job': job}),
                    'development': {'jobId': job['id'], 'kind': job['kind'], 'state': job['state']}}
        return {'success': not failure, **({'error': job['state']} if failure else {}), 'output': encode(page or {'job': job}), 'development': {'jobId': job['id'], 'kind': job['kind'], 'state': job['state']}}

    def closed_without_exit_status(self, job):
        """Attest closure from private originals without changing any job or receipt."""
        from contracts import DevelopmentFault, digest, generation, identity
        from recovery import read
        worker = self.worker
        if (job.get('kind') != 'execution' or job.get('state') != 'unknown'
                or job.get('phase') not in ('guest_completed', 'reconciled') or not job.get('completedAt')
                or job.get('error') is not None or job.get('exitCode') is not None
                or job.get('projectId') != worker.manifest['projectId'] or job.get('sessionId') != worker.session_id):
            return None
        try:
            root = worker.store.workspace.parent / 'Development/ExecutionWork' / identity(job['id'])
            intent, started, closed = (read(root / name) for name in ('intent.json', 'started.json', 'closed.json'))
            expected = {key: job[key] for key in ('executionId', 'deploymentId', 'target', 'settings')}
            expected['jobId'] = job['id']; identity(expected['executionId'])
            if any(type(value.get('schema')) is not int or value['schema'] != 1
                    or any(value.get(key) != val for key, val in expected.items())
                    for value in (intent, started, closed)):
                return None
            if (intent.get('state') != 'intent' or started.get('state') != 'started' or closed.get('state') != 'closed'
                    or closed.get('applicationStarted') is False):
                return None
            process = job['process']; generation(process['generation'])
            if type(process.get('instanceId')) is not int or process['instanceId'] <= 0: return None
            required = {'instanceId': process['instanceId'], 'generation': process['generation'], 'state': 'completed',
                'closeConfirmed': True, 'exitEvidenceUnavailable': True, 'exitCode': None, 'stopReason': None}
            if any((started.get('process') or {}).get(key) != process[key] for key in ('instanceId', 'generation')):
                return None
            if any(any(key not in value or type(value[key]) is not type(val) or value[key] != val for key, val in required.items())
                    for value in (closed.get('completion') or {}, job.get('guestState') or {})):
                return None
            if not all((closed.get('cleanupReceipt') or {}).get(key) is True
                    for key in ('closed', 'serviceRemoved', 'watchdogRemoved')):
                return None
            return {'source': 'private-guest-close-receipt', 'receiptSha256': digest(root / 'closed.json'),
                'processEndConfirmed': True, 'cleanupConfirmed': True, 'exitStatusConfirmed': False}
        except (OSError, ValueError, KeyError, TypeError, AttributeError, DevelopmentFault):
            return None

    def replay_read(self, arguments, result):
        """Reclassify only a saved status read; never replay an old mutation."""
        if (result.get('error') != 'unknown' or result.get('partialChangesPossible')
                or (result.get('development') or {}).get('jobId') != arguments.get('jobId')):
            return result
        try:
            page = json.loads(result['output']); job = page['job']
            if job['id'] != arguments['jobId']: return result
            observed = self.result(job, page)
            return observed if observed.get('error') == 'exit_status_unavailable' else result
        except (ValueError, KeyError, TypeError, AttributeError):
            return result

    async def stop_owned(self):
        try: await self.request('cancel_owned')
        except Exception: pass  # The independently bounded worker/watchdog still owns cleanup.
