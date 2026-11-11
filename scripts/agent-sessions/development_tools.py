"""Fixed broker calls; VM startup waits in the harness, outside model inference."""
from tool_catalog import tool_scope
import json
import os
from pathlib import Path
import uuid
import asyncio


class DevelopmentTools:
    def __init__(self, worker):
        self.worker = worker
        self.capability_snapshot = None
        self.capability_lock = asyncio.Lock()

    async def capabilities(self):
        from vm_worker import broker_call
        path=Path(os.environ.get('STUDIO_DEVELOPMENT_SOCKET','/run/r4os-studio-development/host.sock'))
        async with self.capability_lock:
            try:
                info=path.stat()
                identity=(info.st_dev,info.st_ino,info.st_ctime_ns)
            except OSError: identity=None
            if identity is not None and self.capability_snapshot and self.capability_snapshot[0]==identity:
                return self.capability_snapshot[1]
            value=await broker_call({'operation':'capabilities'})
            self.capability_snapshot=(identity,value) if identity is not None else None
            return value

    def compact(self): return tool_scope(self.worker.config) == 'project'

    def present(self,job,page=None):
        if not self.compact(): return page or {'job':job}
        from development_projection import summary
        return summary(job,page)

    async def request(self, operation, **fields):
        from vm_worker import broker_call
        from contracts import DevelopmentFault, UnconfirmedGuestEffect
        worker = self.worker
        try:
            return await broker_call({'operation': operation, 'projectId': worker.manifest['projectId'],
                'owner': {'sessionId': worker.session_id, 'agentRunId': worker.run_id}, **fields})
        except (OSError, asyncio.TimeoutError):
            if operation in ('build', 'deploy', 'execution', 'vm_start', 'vm_stop','vm_restart', 'ssh', 'observation', 'capture', 'input', 'window', 'assess', 'stop_job', 'complete_check', 'cancel_owned', 'update_plan', 'package', 'update_probe', 'update_transfer', 'update_install', 'update_commit', 'update_recovery'):
                raise UnconfirmedGuestEffect('The development request receipt was lost. It was not replayed.') from None
            raise DevelopmentFault('The development coordinator is unavailable.', 503) from None

    def image_capable(self):
        worker = self.worker
        if worker.config['engine'].get('kind')=='studio':return worker.config.get('apiModel',{}).get('imageInput')=='supported'
        if worker.config['engine'].get('kind')=='claude-code':return worker.config.get('claudeModel',{}).get('imageInput')=='supported'
        try:
            models = json.loads((worker.store.directory / worker.session_id / 'Codex/models.json').read_text())['models']
            return 'image' in next(v for v in models if v['slug'] == worker.config['model']).get('input_modalities', [])
        except (OSError, ValueError, KeyError, StopIteration): return False

    async def native_output(self, result, image_data=None):
        from session_store import encode
        content = []
        reference = result.get('development') or result.get('developmentRequest')
        if reference:
            # Small original reference comes before presentation text; the
            # durable job/request/call mapping also survives a lost whole reply.
            content.append({'type':'inputText','text':encode({'developmentReference':reference,'referenceOnly':True})})
        content.append({'type': 'inputText', 'text': encode(result)})
        if result.get('skillMcp'):
            images=self.worker.skill_mcp.images(result) if self.image_capable() else []
            for block in images:
                content.append({'type':'inputImage','imageUrl':'data:'+block['mimeType']+';base64,'+block['data']})
            if len(images)<result['skillMcp'].get('imageCount',0):
                content.append({'type':'inputText','text':'Some original skill images remain in the retained result because this model or its image transport limit cannot deliver them. Retention does not confirm visual inspection.'})
        if result.get('generatedImage') and self.image_capable():
            from generated_images import GeneratedImages
            import base64
            images=GeneratedImages(self.worker.store,self.worker.session_id);meta=images.get(result['generatedImage']['id'])
            if meta!=result['generatedImage']:raise ValueError('The original generated image metadata changed.')
            raw=images.path(meta['id']).read_bytes()
            content.append({'type':'inputImage','imageUrl':'data:'+meta['mediaType']+';base64,'+base64.b64encode(raw).decode()})
        if result.get('image'):
            historical=False
            if result.get('contextReadback') and self.worker.config['permissions'].get('studio.read_context_result'):
                from context_results import load
                _,part,_=load(self.worker,result['contextReadback'])
                if part['result'].get('image')!=result['image']:raise ValueError('The historical screenshot reference changed.')
                historical=True
            if not (self.worker.config['permissions'].get('studio.capture_vm') or historical) or (not self.image_capable() and result.get('imageDelivery') != 'reference-only'):
                return {'success': False, 'contentItems': [{'type': 'inputText', 'text': 'Image inspection is unavailable for this model or permission.'}]}
            image = result['image']
            data = image_data if image_data is not None else await self.request('evidence', id=image['jobId'], evidenceId=image['id'])
            if (data['metadata'] != image or image['projectId'] != self.worker.manifest['projectId'] or image['kind'] != 'screenshot'
                    or (image.get('observer') or {}).get('sessionId') != self.worker.session_id):
                raise ValueError('Image identity changed.')
            # Transient RPC image only. Durable tools/events retain opaque refs.
            if self.image_capable():
                content.append({'type': 'inputImage', 'imageUrl': 'data:image/png;base64,' + data['base64']})
            else:
                content.append({'type':'inputText','text':'The saved screenshot reference is available for presentation. This model did not receive pixels. Any visionAnalysis is attributed external image analysis, not this model’s own perception or proof of GUI actions.'})
        return {'success': result['success'], 'contentItems': content}

    def capture_capable(self):
        from contracts import DevelopmentFault
        from store import ProjectFault
        if not self.worker.config['permissions'].get('studio.capture_vm'):
            raise DevelopmentFault('Image inspection is disabled in the original run.',403)
        if not self.image_capable():
            from vision_analysis import configured
            try: configured(self.worker)
            except ProjectFault as error: raise DevelopmentFault(str(error),error.code) from None

    def screenshot(self,data,job_id):
        from contracts import DevelopmentFault
        from session_store import encode
        metadata = data['metadata']
        if (metadata.get('projectId') != self.worker.manifest['projectId'] or metadata.get('jobId') != job_id
                or metadata.get('kind') != 'screenshot' or (metadata.get('observer') or {}).get('sessionId') != self.worker.session_id):
            raise DevelopmentFault('The screenshot does not match this session.',403)
        reference = 'studio-image:' + metadata['jobId'] + '/' + metadata['id']
        presentation = {'reference':reference,'markdown':'![VM screenshot]('+reference+')',
            'instruction':'Reuse this exact saved image reference in your reply; do not capture again just to present it.'}
        return {'success':True,'output':encode({**metadata,'presentation':presentation}),
            'development':{'jobId':job_id},'image':metadata,'presentation':presentation,
            'captureState':'confirmed','imageDelivery':'pixels' if self.image_capable() else 'reference-only',
            '_transientImage':data}

    async def analyse_screenshot(self,result,data,question,call_id):
        from session_store import encode
        from store import ProjectFault
        if question is None: analysis = {'state':'not-requested'}
        elif self.image_capable():
            analysis = {'state':'native','question':question,'reason':'Answer using the original image delivered directly to the main model. No fallback was called.'}
        else:
            from vision_analysis import Vision
            if self.worker.vision_helper is None: self.worker.vision_helper = Vision(self.worker)
            try: analysis = await self.worker.vision_helper.analyse(call_id,data,question)
            except asyncio.CancelledError:
                analysis = {'state':'unknown','reason':'The image analysis was interrupted. Its original operation was not repeated.'}
            except ProjectFault as error:
                analysis = {'state':'unknown' if error.code==503 else 'failed','reason':str(error)}
            except Exception:
                analysis = {'state':'unknown','reason':'The original image analysis could not be confirmed. The saved screenshot is retained; no request was repeated.'}
        result['visionAnalysis'] = analysis
        if analysis['state'] in ('failed','unknown'):
            result.update(success=False,error='unknown' if analysis['state']=='unknown' else 'unavailable')
        result['output'] = encode({**data['metadata'],'presentation':result['presentation'],
            'captureState':'confirmed','imageDelivery':result['imageDelivery'],'visionAnalysis':analysis})
        return result

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
            if name in ('deploy_project', 'run_project'):
                from retired_desktop import request as reject_retired
                reject_retired(value)
            if name in ('build_project', 'deploy_project', 'run_project', 'start_project_vm', 'stop_project_vm','restart_project_vm', 'run_vm_command'):
                if name in ('start_project_vm','stop_project_vm','restart_project_vm'):
                    capabilities = await self.capabilities()
                    if capabilities.get('features', {}).get('vmStart' if name=='start_project_vm' else 'vmLifecycle') != 1:
                        raise DevelopmentFault('VM start support requires development host maintenance.', 503)
                if name == 'run_vm_command':
                    capability = await self.capabilities()
                    if capability.get('features',{}).get('projectSsh') != 1:
                        raise DevelopmentFault('Project SSH requires the current coordinator and SSH worker support. No command was admitted.', 503)
                    if capability.get('sshWait')!=1:
                        raise DevelopmentFault('Wait for the development coordinator to adopt SSH result support before starting this command.',503)
                settings = await self.request('settings')
                from jobs import Jobs
                store = Jobs(self.worker.manifest['projects'], self.worker.manifest['r4os'], self.worker.manifest['projectId'])
                try: revision = store.project['revision']
                finally: store.close()
                body = {'requestId': request_id, 'projectRevision': revision, 'settingsRevision': settings['revision']}
                operation = {'build_project': 'build', 'deploy_project': 'deploy', 'run_project': 'execution', 'start_project_vm': 'vm_start', 'stop_project_vm':'vm_stop','restart_project_vm':'vm_restart', 'run_vm_command': 'ssh'}[name]
                if name == 'deploy_project':
                    body['artifactId'] = value['artifactId']
                if name == 'run_project':
                    body['deploymentId'] = value['deploymentId']
                    if 'windowControl' in value:
                        if type(value['windowControl']) is not bool: raise DevelopmentFault('Window control must be a boolean.',400)
                        if value['windowControl']:
                            capability = await self.capabilities()
                            if capability.get('features',{}).get('windowControl') != 1:
                                raise DevelopmentFault('Window controls require the current development coordinator. No app was started.',503)
                        body['windowControl'] = value['windowControl']
                    overrides = {k: value[k] for k in ('arguments', 'timeoutSeconds') if k in value}
                    overrides.update(value.get('criteria', {}))
                    if overrides: body['overrides'] = overrides
                if name == 'run_vm_command': body['command'] = value['command']
                job = await self.request(operation, input=body)
                if name in ('start_project_vm','stop_project_vm','restart_project_vm'): return await self.wait_for_vm(job, call_id, value,name)
                if name in ('build_project', 'deploy_project', 'run_project','run_vm_command'): return await self.wait_for_job(name, job, call_id, value)
                return self.result(job)
            if name == 'read_development_job':
                if 'lookup' in value:
                    if tool_scope(self.worker.config) != 'project' or set(value) != {'lookup'}:
                        raise DevelopmentFault('Job lookup requires its declared v19 read option.',403)
                    capabilities = await self.capabilities()
                    if capabilities.get('features',{}).get('sessionJobLookup') != 1:
                        raise DevelopmentFault('Original job lookup requires the current development coordinator.',503)
                    references = await self.request('session_jobs',query=value['lookup'])
                    return {'success':True,'output':encode(references)}
                await asyncio.sleep(value.get('waitMilliseconds', 0) / 1000)
                mode=value.get('view','summary') if self.compact() else 'legacy'
                if value.get('channel') and mode != 'output': raise DevelopmentFault('A stdout/stderr channel requires view=output.',400)
                if value.get('cursor') and mode not in ('details','inventory'): raise DevelopmentFault('A detail cursor requires its original details/inventory view.',400)
                if 'tailBytes' in value and mode != 'tail': raise DevelopmentFault('tailBytes requires view=tail.', 400)
                if mode == 'tail' and any(k in value for k in ('offset','cursor','channel')):
                    raise DevelopmentFault('view=tail excludes offset, cursor and channel. Continue with view=output and nextOffset.', 400)
                page = (await self.request('read_job', id=value['jobId'], tailBytes=value.get('tailBytes',8192)) if mode == 'tail' else
                    await self.request('read_job', id=value['jobId'], offset=value.get('offset', 0), **({'channel':value['channel']} if value.get('channel') else {}), **({'metadataOnly':True} if mode!='output' and self.compact() else {})))
                if not self.compact() or mode=='inventory':page=await self.with_artifact(page['job'],page)
                result=self.result(page['job'],page)
                if mode in ('details','inventory','output','tail'):
                    from development_projection import view
                    result['output']=encode(view(page,mode,value.get('cursor'),page.get('startOffset',0) if mode=='tail' else value.get('offset',0)))
                # The read succeeded even when the original job is unknown.
                # Keep its state/evidence visible without declaring a new
                # unconfirmed effect or aborting the native Goal on a read.
                result.update(success=True)
                result.pop('error', None)
                return result
            if name == 'complete_development_job':
                page = await self.request('complete_check', id=value['jobId'], input={'requestId': request_id})
                return self.result(page['job'], page)
            if name == 'stop_development_job':
                capabilities = await self.capabilities()
                if capabilities.get('features', {}).get('stopReceipts') != 1:
                    raise DevelopmentFault('The development coordinator must adopt the installed Stop-receipt support before this call.', 503)
                stopped = await self.request('stop_job', id=value['jobId'])
                receipt = stopped.get('stopReceipt') or {}
                confirmed = (receipt.get('version') == 1 and receipt.get('jobId') == value['jobId']
                    and receipt.get('confirmed') is True and receipt.get('outcome') in ('stopped', 'already-ended', 'not-started'))
                return {'success': confirmed, **({} if confirmed else {'error': 'unknown'}),
                    'output': encode(self.present(stopped,{'job': stopped, 'stop': receipt})), 'developmentStop': receipt,
                    'development': {'jobId': stopped['id'], 'kind': stopped['kind'], 'state': stopped['state']}}
            if name == 'capture_vm':
                self.capture_capable()
                if value.get('action', 'capture') == 'assess':
                    if set(value) != {'jobId', 'action', 'evidenceId', 'state', 'notes'}: raise DevelopmentFault('Provide image ID, state and notes for assessment.', 400)
                    job = await self.request('assess', id=value['jobId'], input={'requestId': request_id,
                        'evidenceId': value['evidenceId'], 'state': value['state'], 'notes': value['notes']})
                    # This call commits a host image judgment. An earlier
                    # unconfirmed guest execution is separate from that receipt.
                    result = self.result(job)
                    result.update(success=True)
                    result.pop('error', None)
                    return result
                action = value.get('action','capture')
                if action not in ('capture','inspect'): raise DevelopmentFault('Unknown screenshot action.',400)
                allowed = {'jobId','action','evidenceId','question'} if action=='inspect' else {'jobId','action','analysisQuestion','scope'}
                if set(value)-allowed: raise DevelopmentFault('Unexpected screenshot fields.',400)
                question = value.get('question' if action=='inspect' else 'analysisQuestion')
                if action=='inspect' or question is not None:
                    from vision_analysis import validate_question
                    try: validate_question(question)
                    except __import__('store').ProjectFault as error: raise DevelopmentFault(str(error),error.code) from None
                if 'scope' in value and value['scope'] != 'vm': raise DevelopmentFault('Choose the explicit vm diagnosis scope.', 400)
                diagnostic = value.get('scope') == 'vm'
                if diagnostic:
                    capability = await self.capabilities()
                    if capability.get('features',{}).get('vmObservation') != 1:
                        raise DevelopmentFault('VM diagnosis requires the current development coordinator.', 503)
                if action == 'inspect':
                    data = await self.request('evidence', id=value['jobId'], evidenceId=value['evidenceId'])
                elif diagnostic and 'jobId' not in value:
                    context = self.worker.config.get('vmObservation') or {}
                    if context.get('available') is not True:
                        raise DevelopmentFault('VM diagnosis was unavailable in this accepted input. Review the assigned VM and send a new input.', 409)
                    settings = await self.request('settings')
                    job = await self.request('observation', input={'requestId':request_id,
                        'projectRevision':context['projectRevision'], 'settingsRevision':settings['revision'], 'toolCallId':call_id})
                    waited = await self.wait_for_job('capture_vm', job, call_id, value)
                    if not waited['success']: return waited
                    page = await self.request('wait_observation', id=job['id'])
                    job = page['job']
                    if job.get('captureState') != 'confirmed' or not job.get('evidenceId'):
                        raise DevelopmentFault('The original observation has no confirmed image receipt. Do not recapture automatically.', 503)
                    data = await self.request('evidence', id=job['id'], evidenceId=job['evidenceId'])
                else:
                    data = await self.request('capture', id=value['jobId'], input={'requestId':request_id,
                        **({'scope':'vm'} if diagnostic else {})})
                result = self.screenshot(data,data['metadata']['jobId'])
                return await self.analyse_screenshot(result,data,question,call_id)
            if name == 'control_app_window':
                data = await self.request('window', id=value['jobId'], input={'requestId': request_id, 'input': {k: v for k, v in value.items() if k != 'jobId'}})
                return {'success': data.get('confirmed', False), 'output': encode(data), 'development': {'jobId': value['jobId']}}
            if name == 'send_vm_input':
                if value.get('kind') == 'keyPlan':
                    capability = await self.capabilities()
                    if capability.get('features',{}).get('keyPlan') != 1:
                        raise DevelopmentFault('Key plans require the current development coordinator; no input was admitted.',503)
                if 'interrupt' in value:
                    capability = await self.capabilities()
                    if capability.get('features', {}).get('dragInterrupt') != 1:
                        raise DevelopmentFault('Drag interrupts require the current development coordinator; no input was admitted.', 503)
                if value.get('observeAfterStep') is not None: self.capture_capable()
                data = await self.request('input', id=value['jobId'], input={'requestId': request_id, 'input': {k: v for k, v in value.items() if k != 'jobId'}})
                observation = data.pop('observation', None)
                result = {'success':data.get('complete',True),'output':encode(data),'development':{'jobId':value['jobId']}}
                if observation:
                    image = self.screenshot(observation,value['jobId'])
                    result.update({k:v for k,v in image.items() if k not in ('success','output','development')})
                    result['visionAnalysis'] = {'state':'not-requested'}
                return result
            raise DevelopmentFault('Unknown development tool.', 400)
        except DevelopmentFault as error:
            return {'success': False, 'error': 'unknown' if getattr(error, 'uncertain', False) else 'unavailable', 'output': str(error), 'reasonCode': getattr(error, 'reason_code', None),
                    **({'developmentRequest': {'requestId':request_id,'originRunId':self.worker.run_id,'toolCallId':call_id,
                         'receiptState':'unknown' if getattr(error,'uncertain',False) else 'request_error'}}
                       if job is None and name in ('build_project','deploy_project','run_project','start_project_vm','stop_project_vm','restart_project_vm','capture_vm') else {}),
                    **({'development': {'jobId': job['id']}} if job else
                       {'development': {'jobId': value['jobId']}} if name in ('control_app_window','send_vm_input') else {})}

    async def wait_for_vm(self, job, call_id, arguments, name='start_project_vm'):
        from contracts import ACTIVE, DevelopmentFault, LIMITS, UnconfirmedGuestEffect
        from run_store import item
        worker = self.worker
        # Publish the durable job link immediately, but hold the native tool
        # response. Codex resumes this turn only after a terminal receipt.
        value = {'id': call_id, 'runId': worker.run_id, 'type': 'tool', 'tool': 'studio.'+name,
                 'arguments': arguments, 'status': 'pending', 'development': {'jobId': job['id'],'requestId':job.get('requestId')}}
        worker.items[call_id] = value; item(worker.store, worker.session_id, worker.run_id, value)
        deadline = asyncio.get_running_loop().time() + LIMITS['vmStartTimeoutSeconds' if name=='start_project_vm' else 'vmLifecycleTimeoutSeconds'] + 60
        while job['state'] in ACTIVE:
            if worker.stopping:
                return {'success': False, 'error': 'interrupted', 'output': 'VM readiness wait stopped. The VM may remain running.' if name=='start_project_vm' else 'VM lifecycle wait stopped. Inspect the original job and VM state; no power action was repeated.',
                        'development': {'jobId': job['id']}}
            if asyncio.get_running_loop().time() >= deadline:
                raise UnconfirmedGuestEffect('The VM start outcome could not be read before the harness deadline. Inspect the saved job; no start was repeated.')
            try: job = await self.request({'start_project_vm':'wait_vm_start','stop_project_vm':'wait_vm_stop','restart_project_vm':'wait_vm_restart'}[name], id=job['id'])
            except DevelopmentFault as error:
                if error.code != 503 or getattr(error, 'uncertain', False): raise
                # Reconnect only to the read-only wait for the same job. Never
                # repeat admission or VM start after a lost coordinator reply.
                await asyncio.sleep(1)
        result = self.result(job)
        lifecycle=job.get('vmLifecycle') or {}
        ready=job['state']=='completed' and (job.get('vmStart') or {}).get('ready') is True
        if name=='stop_project_vm':ready=job['state']=='completed' and lifecycle.get('stopped',{}).get('confirmed') is True
        elif name=='restart_project_vm':
            ready=bool(ready and lifecycle.get('stopped',{}).get('confirmed') and lifecycle.get('newBootId')
                and lifecycle['newBootId']!=lifecycle.get('original',{}).get('bootId'))
        if not ready and result['success']:
            result.update(success=False, error='interrupted' if job['state'] == 'interrupted' else 'failed')
        return result

    async def wait_for_job(self, name, job, call_id, arguments):
        from contracts import ACTIVE, DevelopmentFault, UnconfirmedGuestEffect, LIMITS
        from run_store import item
        worker = self.worker; operation = {'build_project': 'wait_build', 'deploy_project': 'wait_deploy',
            'run_project': 'wait_execution', 'capture_vm':'wait_observation','run_vm_command':'wait_ssh'}[name]
        value = {'id': call_id, 'runId': worker.run_id, 'type': 'tool', 'tool': 'studio.' + name,
                 'arguments': arguments, 'status': 'pending', 'development': {'jobId': job['id'],'requestId':job.get('requestId')}}
        worker.items[call_id] = value; item(worker.store, worker.session_id, worker.run_id, value)
        if name=='run_vm_command':
            from tool_deadlines import seconds_for
            timeout=seconds_for(worker.config,'studio.run_vm_command') or 600
        elif name=='capture_vm': timeout=120
        else: timeout=LIMITS['buildTimeoutSeconds']+300 if name=='build_project' else (660 if name=='deploy_project' else job['settings']['timeoutSeconds']+300)
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
        if name=='run_vm_command' and page is None:
            page=await self.request('wait_ssh',id=job['id']); job=page['job']
        return self.result(job, page)

    async def with_artifact(self,job,page):
        from contracts import DevelopmentFault
        if self.compact() and job.get('kind') in ('deploy','execution') and job.get('artifactId'):
            try:
                artifact=await self.request('artifact',id=job['artifactId'])
                if artifact.get('id')!=job['artifactId'] or artifact.get('projectId')!=self.worker.manifest['projectId']:
                    raise DevelopmentFault('This artifact differs from the original job binding.',409)
                return {**(page or {'job':job}),'artifact':artifact}
            except DevelopmentFault:
                return {**(page or {'job':job}),'artifactUnavailable':'The original artifact inventory could not be verified. Job status and receipts were retained.'}
        if job.get('kind')=='build' and job['state']=='completed' and job.get('artifactId'):
            artifact=await self.request('artifact',id=job['artifactId'])
            if (artifact.get('id')!=job['artifactId'] or artifact.get('buildId')!=job['id']
                    or artifact.get('projectId')!=self.worker.manifest['projectId']):
                raise DevelopmentFault('The artifact readback differs from this original project build.',409)
            page={**(page or {'job':job}),'artifact':{key:artifact[key] for key in (('id','entry','files','resourceInputs','resourceInventory','pins','packageSha256','sourceSha256','manifestSha256','buildProof','kind','role','createdAt') if self.compact() else ('id','entry','files','resourceInputs','resourceInventory')) if key in artifact}}
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
                    'output': encode({**self.present(job,page), 'executionReceipt': closure,
                        'notice': 'The owned process has ended and its cleanup is confirmed. Its exit status is unavailable; '
                            'the execution remains unknown, not successful. Inspect the saved checks and evidence before continuing. '
                            'Do not repeat the launch merely because its exit code is missing.'}),
                    'development': {'jobId': job['id'], 'requestId':job.get('requestId'), 'kind': job['kind'], 'state': job['state']}}
        failure = job['state'] in ('failed', 'interrupted', 'unknown')
        if job['state'] == 'running' and (job.get('readiness') or {}).get('reasonCode') == 'desktop_content_unconfirmed':
            return {'success': False, 'error': 'readiness_unknown', 'output': encode(self.present(job,page)),
                    'development': {'jobId': job['id'], 'requestId':job.get('requestId'), 'kind': job['kind'], 'state': job['state']}}
        return {'success': not failure, **({'error': job['state']} if failure else {}), 'output': encode(self.present(job,page)), 'development': {'jobId': job['id'], 'requestId':job.get('requestId'), 'kind': job['kind'], 'state': job['state']}}

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
