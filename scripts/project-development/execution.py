"""Bounded, generation-owned guest executions independent of browser/model turns."""
import asyncio
import base64
import uuid
from contracts import DevelopmentFault, UnconfirmedGuestEffect, LIMITS, digest
from jobs import folder, now
from layout import save
from lease import VmLease
from access import Access, SshTransport, guest_version
from vm_client import vm_call
from guest_control import GuestControl
from sftp import download

class Execution:
    def __init__(self, store, job):
        self.store, self.job = store, job
        self.work = folder(store.root / 'ExecutionWork' / job['id'])
        self.log = store.evidence(job['id']) / 'output.log'
        self.mailbox = None
        self.stop_requested = False; self.control = None; self.last = None

    def output(self, state):
        try: data = base64.b64decode(state.get('outputBase64', ''), validate=True)
        except ValueError: raise UnconfirmedGuestEffect('The guest returned an invalid output frame.') from None
        if len(data) > 24577: raise UnconfirmedGuestEffect('The guest output frame exceeds the limit.')
        size = self.log.stat().st_size if self.log.exists() else 0
        if size + len(data) > LIMITS['outputBytes']: state['outputIncomplete'] = True
        with self.log.open('ab') as stream: stream.write(data[:max(0, LIMITS['outputBytes'] - size)])

    async def action(self, message, state, control, lease, process):
        from actions import admit, finish
        from evidence import read
        from observation import capture
        from vm_worker import guard
        import datetime
        authorization = None
        if message.get('owner') is not None:
            from authorization import authorize
            authorization = authorize(self.store, message['owner'], message['operation'], message['peerPid'], self.store.get(self.job['id']))
        operation = message.get('operation')
        if operation not in ('capture', 'input') or set(message) != ({'operation', 'requestId'} | ({'input'} if operation == 'input' else set()) | ({'owner', 'peerPid'} if authorization else set())):
            raise DevelopmentFault('Invalid execution action.', 400)
        previous = admit(self.store, self.job['id'], message)
        if previous is not None:
            if previous.get('error'): return state, previous
            result = read(self.store, self.job['id'], previous['evidenceId']) if operation == 'capture' else previous
            return state, result
        guard(self.store, self.job, lease)
        # Refresh and consume output once before another observation/action.
        state = await control.call('poll'); self.output(state); state['outputBase64'] = ''
        self.last = state
        job = self.store.get(self.job['id'])
        try:
            if operation == 'capture':
                result = await capture(self.store, job, lease, state, observer={**message['owner'], 'model': authorization['model']} if authorization else None)
                finish(self.store, message['requestId'], {'evidenceId': result['metadata']['id']})
                return state, result
            value = message['input']
            if not isinstance(value, dict) or value.get('kind') not in ('text', 'key', 'click'):
                raise DevelopmentFault('Choose a bounded console or GUI input.', 400)
            kind = value['kind']; allowed = {'kind', 'text'} if kind == 'text' else ({'kind', 'key', 'frameId'} if kind == 'key' else {'kind', 'x', 'y', 'frameId'})
            if set(value) != allowed: raise DevelopmentFault('Unexpected VM input fields.', 400)
            if state['state'] != 'running': raise DevelopmentFault('The owned guest process has ended.')
            deployment = self.store.deployment(job['deploymentId'])
            if kind != 'text' and not deployment.get('helperCapabilities', {}).get('guiInput'):
                raise DevelopmentFault('Deploy again with a GUI-input-capable helper before sending this input.')
            request = {'generation': process['generation']}
            if kind != 'text': request['inputKind'] = kind
            if kind == 'text':
                text = value['text']
                if not isinstance(text, str) or len(text) > 64 or len(text.encode()) > 1024 or '\x00' in text:
                    raise DevelopmentFault('Console input is limited to 64 Unicode characters.', 400)
                if job['binding'] is None: raise DevelopmentFault('The execution has no target.')
                request['input'] = text
            else:
                frame = read(self.store, job['id'], value['frameId'])['metadata']
                elapsed = datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(frame['createdAt'])
                if (frame['kind'] != 'screenshot' or frame['bootId'] != job['target']['bootId']
                    or (frame.get('process') or {}).get('generation') != process['generation'] or elapsed.total_seconds() > 30
                    or frame.get('guestRevision') != state.get('guiRevision') or not state.get('windowFocused')):
                    raise DevelopmentFault('The image or GUI focus changed. Capture the owned window again before input.')
                request['expectedRevision'] = state['guiRevision']
                if kind == 'key':
                    keys = {'Enter': 13, 'Tab': 9, 'Escape': 27, 'Space': 32}
                    if value['key'] not in keys: raise DevelopmentFault('Unsupported GUI key.', 400)
                    request['key'] = keys[value['key']]
                else:
                    if any(type(value[k]) is not int or not 0 <= value[k] <= 1279 for k in ('x', 'y')):
                        raise DevelopmentFault('Invalid client coordinates.', 400)
                    request.update(x=value['x'], y=value['y'])
            guard(self.store, self.job, lease)
            if authorization: authorize(self.store, message['owner'], 'input', message['peerPid'], job)
            state = await control.call('input', **request)
            result = {'accepted': state.get('inputAccepted', 0), 'kind': kind, 'process': process,
                'delivery': 'owned-event-queue', 'consumptionConfirmed': False,
                'complete': state.get('inputAccepted', 0) == (len(value['text']) if kind == 'text' else (2 if kind == 'click' else 1))}
            finish(self.store, message['requestId'], result)
            return state, result
        except DevelopmentFault as error:
            if not getattr(error, 'uncertain', False):
                result = finish(self.store, message['requestId'], {'error': str(error), 'code': error.code})
                return state, result
            raise

    async def run(self):
        from vm_worker import broker_call, guard
        store, job = self.store, self.job
        deployment = store.deployment(job['deploymentId']); vm = job['binding']
        if deployment.get('helperCapabilities', {}).get('controlVersion') != 2 or deployment.get('helperCapabilities', {}).get('watchdogVersion') != 1:
            raise DevelopmentFault('Deploy again with the current guest controller before running.')
        if job['settings'].get('serviceResponseContains') and not deployment.get('helperCapabilities', {}).get('serviceSelfTest'):
            raise DevelopmentFault('Deploy again with a self-test-capable guest helper before running these criteria.')
        if deployment['role'] not in ('terminal', 'desktop', 'service') or deployment['kind'] != 'R4X':
            raise DevelopmentFault('This module needs a role-specific test host. Direct execution is unavailable.')
        scope = {'kind': 'job', 'projectId': store.id, 'projectRevision': job['projectRevision'],
            'vmRevision': vm['revision'], 'imageId': vm['imageId'], 'imageSha256': vm['imageSha256'], 'jobId': job['id']}
        from queue_lease import reserve
        async with reserve(store, job, scope) as lease:
            info = await vm_call(lease, 'info')
            from quarantine import admission, claim, release
            admission(store.projects, vm['id'], info['vm']['state'])
            if info['vm']['state'] != 'running': raise DevelopmentFault('The deployment boot has ended. Deploy again to the prepared VM before running.')
            target = await broker_call({'operation': 'bind_target', 'projectId': store.id, 'jobId': job['id'],
                'leaseId': lease.id, 'token': lease.token, 'helperSha256': deployment['target']['helperSha256']})
            # Profile labels are descriptive metadata, not a VM qualification.
            # Existing deployments retain their recorded label across updates.
            previous = {k: v for k, v in deployment['target'].items() if k != 'profileId'}
            if {k: v for k, v in target.items() if k != 'profileId'} != previous:
                raise DevelopmentFault('The deployment belongs to an older VM boot or revision. Deploy again before running.')
            scope['bootId'] = target['bootId']; save(lease.root / 'leases' / (lease.id + '.json'), lease.value)
            guard(store, job, lease, allow_stopping=True)
            access = Access(store.projects, store.r4os, None)
            async with SshTransport(access, vm, lease) as ssh:
                version = await ssh.exec('VER')
                guest_version(version)
                ssh.publish_host_key()
                store.update(job['id'], phase='verifying_deployment')
                for index, item in enumerate(deployment['files']):
                    guard(store, job, lease, allow_stopping=True)
                    path = self.work / ('verify-' + str(index))
                    await download(ssh, item['path'], path, maximum=item['bytes'])
                    if path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
                        raise DevelopmentFault('The guest deployment changed. No project process was started.')
                    path.unlink()
                if self.stop_requested or store.get(job['id'])['state'] == 'stopping':
                    return store.update(job['id'], 'interrupted', phase='stopped', error='Stopped before guest launch.')
                execution_id = str(uuid.uuid4()); control = GuestControl(ssh, deployment, execution_id); self.control = control
                intent = {'schema': 1, 'executionId': execution_id, 'jobId': job['id'], 'deploymentId': deployment['id'],
                    'target': target, 'vmInvocationId': info['invocationId'], 'role': deployment['role'], 'settings': job['settings'], 'state': 'intent', 'createdAt': now()}
                save(self.work / 'intent.json', intent)
                claim(store.projects, vm['id'], {'jobId': job['id'], 'projectId': store.id, 'executionId': execution_id,
                    'target': target, 'deploymentId': deployment['id']})
                start_sent = False; hello_ready = False
                try:
                    hello = await control.open(); hello_ready = True; save(self.work / 'controller.json', hello)
                    guard(store, job, lease, allow_stopping=True)
                    if self.stop_requested or store.get(job['id'])['state'] == 'stopping':
                        closed = await control.call('finish')
                        if not closed.get('closed') or not closed.get('watchdogRemoved'): raise UnconfirmedGuestEffect('Watchdog stop was not confirmed.')
                        save(self.work / 'closed.json', {**intent, 'state': 'closed', 'applicationStarted': False})
                        release(store.projects, vm['id'], job['id'])
                        return store.update(job['id'], 'interrupted', phase='stopped', error='Stopped before application launch.')
                    store.update(job['id'], phase='starting_guest', executionId=execution_id)
                    guard(store, job, lease)
                    # The start is sent once. Missing acknowledgements become unknown.
                    start_sent = True
                    state = await control.call('start', role=deployment['role'], arguments=job['settings']['arguments'],
                        timeoutSeconds=job['settings']['timeoutSeconds'], serviceName=store.project['moduleName'] if deployment['role'] == 'service' else '')
                    process = {'instanceId': state['instanceId'], 'generation': state['generation'], 'windowId': state['windowId'], 'serviceName': state.get('serviceName')}
                    if not process['instanceId'] or not process['generation'].isdigit() or int(process['generation']) < 1:
                        raise UnconfirmedGuestEffect('The guest start did not confirm a generation-owned process.')
                    save(self.work / 'started.json', {**intent, 'state': 'started', 'process': process})
                    store.update(job['id'], process=process, phase='guest_running')
                    from job_control import Mailbox
                    from checks import evaluate
                    from output_files import collect
                    self.mailbox = Mailbox(job['id']); await self.mailbox.open()
                    stop_sent = False; service_checked = False
                    while True:
                        self.output(state); state['outputBase64'] = ''; self.last = state
                        save(self.work / 'observation.json', state)
                        process['windowId'] = state['windowId']
                        store.update(job['id'], process=process, phase=('window_visible' if state.get('windowVisible') else ('service_ready' if state.get('serviceEndpointReady') else 'guest_running')), guestState={k: v for k, v in state.items() if k != 'outputBase64'})
                        if job['settings'].get('serviceResponseContains') and state.get('serviceEndpointReady') and not service_checked and not self.stop_requested and store.get(job['id'])['state'] == 'running':
                            service_checked = True
                            state = await control.call('service_check')
                            continue
                        current = store.get(job['id'])
                        output = self.log.read_bytes() if self.log.exists() else b''
                        if state['state'] != 'completed':
                            store.update(job['id'], check=evaluate(job['settings'], state, output, visual=current.get('visualAssessment')))
                        if state['state'] == 'completed':
                            if not state['closeConfirmed']: raise UnconfirmedGuestEffect('The process completion was not fully reaped.')
                            files = await collect(store, store.get(job['id']), deployment, ssh, self.work)
                            store.update(job['id'], outputFiles=files, check=evaluate(job['settings'], state, self.log.read_bytes() if self.log.exists() else b'', files, store.get(job['id']).get('visualAssessment')))
                            closed = await control.call('finish')
                            if not closed.get('closed') or not closed.get('serviceRemoved', False) or not closed.get('watchdogRemoved'):
                                raise UnconfirmedGuestEffect('Owned service cleanup was not confirmed.')
                            import os, hashlib
                            with self.log.open('ab') as output_stream: output_stream.flush(); os.fsync(output_stream.fileno())
                            data = self.log.read_bytes()
                            intent['state'] = 'closed'; save(self.work / 'closed.json', {**intent, 'completion': state, 'cleanupReceipt': closed,
                                'outputReceipt': {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}})
                            release(store.projects, vm['id'], job['id'])
                            stopped = state.get('stopReason'); terminal = 'interrupted' if stopped == 'user_stop' else ('failed' if stopped == 'timeout' else ('unknown' if state['exitCode'] is None else ('failed' if state['exitCode'] != 0 else 'completed')))
                            return store.update(job['id'], terminal, phase='timeout' if stopped == 'timeout' else ('stopped' if stopped else 'guest_completed'),
                                exitCode=state['exitCode'], guestState={k: v for k, v in state.items() if k != 'outputBase64'},
                                error='Guest execution exceeded its time limit.' if stopped == 'timeout' else None)
                        if state['state'] == 'unknown': raise UnconfirmedGuestEffect('The generation-owned process status became unknown.')
                        guard(store, job, lease, allow_stopping=True)
                        if (self.stop_requested or store.get(job['id'])['state'] == 'stopping') and not stop_sent:
                            stop_sent = True; state = await control.call('stop')
                        else:
                            if self.mailbox.queue.empty():
                                await asyncio.sleep(.2); state = await control.call('poll')
                            else:
                                message, future = self.mailbox.queue.get_nowait()
                                try:
                                    state, result = await self.action(message, state, control, lease, process)
                                    if not future.done(): future.set_result(result)
                                except DevelopmentFault as error:
                                    if not future.done(): future.set_exception(error)
                                    if getattr(error, 'uncertain', False): raise
                except BaseException as error:
                    if hello_ready and not start_sent and not (self.work / 'closed.json').exists():
                        try:
                            closed = await control.call('finish')
                            if closed.get('closed') and closed.get('watchdogRemoved'):
                                save(self.work / 'closed.json', {**intent, 'state': 'closed', 'applicationStarted': False, 'cleanupReceipt': closed})
                                release(store.projects, vm['id'], job['id'])
                        except Exception: pass
                    if start_sent and not (self.work / 'closed.json').exists():
                        raise UnconfirmedGuestEffect('Guest control ended without a confirmed cleanup receipt. Its watchdog remains responsible; no start was replayed.') from error
                    raise
                finally:
                    if self.mailbox: await self.mailbox.close()
                    await control.close(); self.control = None
