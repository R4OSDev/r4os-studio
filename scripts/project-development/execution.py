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
from sftp import download_many

class Execution:
    def __init__(self, store, job):
        self.store, self.job = store, job
        self.work = folder(store.root / 'ExecutionWork' / job['id'])
        self.log = store.evidence(job['id']) / 'output.log'
        self.mailbox = None
        self.stop_requested = False; self.control = None; self.last = None
        self.completion = None; self.completion_future = None
        self.wake = asyncio.Event(); self.saved_observation = None
        self.output_data = b''
        if self.log.exists():
            with self.log.open('rb') as stream: self.output_data = stream.read(LIMITS['outputBytes'] + 1)
            if len(self.output_data) > LIMITS['outputBytes']: raise DevelopmentFault('Existing execution output exceeds its limit.')
        self.output_limited = False

    def output(self, state):
        try: data = base64.b64decode(state.get('outputBase64', ''), validate=True)
        except ValueError: raise UnconfirmedGuestEffect('The guest returned an invalid output frame.') from None
        if len(data) > 24577: raise UnconfirmedGuestEffect('The guest output frame exceeds the limit.')
        size = len(self.output_data)
        if size + len(data) > LIMITS['outputBytes']: self.output_limited = True
        if self.output_limited: state['outputIncomplete'] = True
        fresh = data[:max(0, LIMITS['outputBytes'] - size)]
        if fresh:
            with self.log.open('ab') as stream: stream.write(fresh)
            self.output_data += fresh
        return bool(fresh)

    async def action(self, message, state, control, lease, process):
        from actions import admit, finish
        from evidence import read
        from observation import capture
        from vm_worker import guard
        authorization = None
        if message.get('owner') is not None:
            from authorization import authorize
            authorization = authorize(self.store, message['owner'], message['operation'], message['peerPid'], self.store.get(self.job['id']))
        operation = message.get('operation')
        if self.completion and operation != 'complete_check': raise DevelopmentFault('This execution is completing its checks; no further input or capture is admitted.')
        if operation not in ('capture', 'input', 'complete_check') or set(message) != ({'operation', 'requestId'} | ({'input'} if operation == 'input' else set()) | ({'owner', 'peerPid'} if authorization else set())):
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
            if operation == 'complete_check':
                if self.completion or self.stop_requested: raise DevelopmentFault('This execution is already completing or stopping.')
                from completion import validate
                from output_files import collect
                deployment = self.store.deployment(job['deploymentId'])
                files = await collect(self.store, job, deployment, control.ssh, self.work)
                # Re-observe after file reads before authorizing a close.
                state = await control.call('poll'); self.output(state); state['outputBase64'] = ''
                job = self.store.get(job['id'])
                marker = validate(self.store, job, state, self.log.read_bytes() if self.log.exists() else b'', files)
                guard(self.store, self.job, lease)
                if authorization: authorize(self.store, message['owner'], operation, message['peerPid'], job)
                marker.update(requestId=message['requestId'])
                save(self.work / 'complete-intent.json', marker)
                self.completion = marker
                self.store.update(job['id'], checkCompletion={'requestId': marker['requestId'], 'reason': 'criteria_complete', 'state': 'closing'}, phase='completing_checks')
                state = await control.call('stop')
                return state, {'pendingCompletion': True}
            if operation == 'capture':
                result = await capture(self.store, job, lease, state, observer={**message['owner'], 'model': authorization['model']} if authorization else None, control=control, consume=self.output)
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
                from frame_binding import current
                if not current(frame, job, state, focused=True):
                    raise DevelopmentFault('The image is older than 30 seconds or its process, window geometry or focus changed. Capture the owned window again before input.')
                if deployment.get('helperCapabilities', {}).get('guiFrameBindingVersion') == 1 and frame.get('captureObservation', {}).get('version') == 1:
                    request.update(frameBindingVersion=1, expectedWindowId=state['windowId'],
                        expectedWindowWidth=state['windowWidth'], expectedWindowHeight=state['windowHeight'])
                else:
                    if frame.get('guestRevision') != state.get('guiRevision'):
                        raise DevelopmentFault('This older guest helper requires unchanged content for input. Deploy again with the current helper to control animations.')
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
        if deployment.get('format') != 'exchange-build-v1':
            raise DevelopmentFault('This historical C: deployment remains readable. Deploy the artifact to Exchange Build before running.')
        desktop = deployment['role'] == 'desktop'
        if desktop and deployment.get('helperCapabilities', {}).get('desktopAdoptionVersion') != 1:
            raise DevelopmentFault('Deploy again with the current Desktop process controller before running.')
        if deployment.get('helperCapabilities', {}).get('exchangeRunVersion') != 1:
            raise DevelopmentFault('Deploy again with an Exchange-run-capable controller before running.')
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
            from quarantine import claim, release
            binding = {'projectId': store.id, 'jobId': job['id'], 'leaseId': lease.id,
                'token': lease.token, 'helperSha256': deployment['target']['helperSha256']}
            try:
                bound = await broker_call({'operation': 'bind_execution', **binding})
                target, invocation_id = bound['target'], bound['vmInvocationId']
            except DevelopmentFault as error:
                # Only an explicit old-protocol rejection permits the legacy reads.
                if error.code != 400 or str(error) != 'Unsupported development coordinator operation.': raise
                from quarantine import admission
                info = await vm_call(lease, 'info')
                admission(store.projects, vm['id'], info['vm']['state'])
                if info['vm']['state'] != 'running': raise DevelopmentFault('The deployment boot has ended. Deploy again to the prepared VM before running.')
                target = await broker_call({'operation': 'bind_target', **binding})
                invocation_id = info['invocationId']
            scope['bootId'] = target['bootId']; save(lease.root / 'leases' / (lease.id + '.json'), lease.value)
            guard(store, job, lease, allow_stopping=True)
            access = Access(store.projects, store.r4os, None)
            async with SshTransport(access, vm, lease) as ssh:
                version = await ssh.exec('VER')
                guest_version(version)
                ssh.publish_host_key()
                from exchange import rebind, inventory, preflight
                info = bound.get('exchangeInfo') if 'bound' in locals() else None
                if info is None: info = await vm_call(lease, 'info')
                deployment, owner_path = await rebind(ssh, info, target, deployment, store.id)
                target = deployment['target']; store.update(job['id'], target=target, phase='verifying_deployment',
                    package={'format': 'exchange-build-v1', 'guestDirectory': deployment['guestDirectory'],
                        'relativeDirectory': deployment['guestDirectory'][3:].replace(chr(92), '/')})
                ssh.package_root = owner_path.rsplit('/', 1)[0]
                entries = await inventory(ssh, target['exchange'])
                preflight(entries, [16384, 4096], 2, 0, len(job['settings'].get('outputFiles', [])))
                guard(store, job, lease, allow_stopping=True)
                await download_many(ssh, [(owner_path, self.work / 'project-owner.json', 4096)] + [(item['path'], self.work / ('verify-' + str(index)), item['bytes'])
                    for index, item in enumerate(deployment['files'])])
                import json
                owner = json.loads((self.work / 'project-owner.json').read_text())
                if owner != {'schema': 1, 'interface': 'r4os-studio-project', 'projectId': store.id, 'exchangeGeneration': target['exchange']['generation']}:
                    raise DevelopmentFault('The Exchange project owner changed. No application was started.')
                for index, item in enumerate(deployment['files']):
                    guard(store, job, lease, allow_stopping=True)
                    path = self.work / ('verify-' + str(index))
                    if path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
                        raise DevelopmentFault('The guest deployment changed. No project process was started.')
                    path.unlink()
                if desktop:
                    from deskrun import capability, command
                    command(deployment, job['settings']['arguments'], min(10000, job['settings']['timeoutSeconds'] * 1000))
                    guard(store, job, lease)
                    try: native_capability = await capability(ssh)
                    except DevelopmentFault as error:
                        store.update(job['id'], readiness={'state': 'unsupported', 'reasonCode': error.reason_code or 'deskrun_unavailable',
                            'reason': str(error), 'checkedAt': now()})
                        raise
                    save(self.work / 'desktop-capability.json', native_capability)
                if self.stop_requested or store.get(job['id'])['state'] == 'stopping':
                    return store.update(job['id'], 'interrupted', phase='stopped', error='Stopped before guest launch.')
                execution_id = str(uuid.uuid4()); control = GuestControl(ssh, deployment, execution_id); self.control = control
                intent = {'schema': 1, 'executionId': execution_id, 'jobId': job['id'], 'deploymentId': deployment['id'],
                    'target': target, 'vmInvocationId': invocation_id, 'role': deployment['role'], 'settings': job['settings'], 'state': 'intent', 'createdAt': now()}
                save(self.work / 'intent.json', intent)
                claim(store.projects, vm['id'], {'jobId': job['id'], 'projectId': store.id, 'executionId': execution_id,
                    'target': target, 'deploymentId': deployment['id']})
                start_sent = False; hello_ready = False
                try:
                    hello = await control.open(); hello_ready = True; save(self.work / 'controller.json', hello)
                    if desktop and hello['result'].get('desktopAdoptionVersion') != 1:
                        raise DevelopmentFault('The guest controller does not support exact Desktop process adoption.')
                    if deployment.get('helperCapabilities', {}).get('guiFrameBindingVersion') == 1 and hello['result'].get('guiFrameBindingVersion') != 1:
                        raise DevelopmentFault('The guest controller does not confirm its declared window binding capability.')
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
                    launcher = None
                    if desktop:
                        from deskrun import DesktopLaunch
                        launcher = DesktopLaunch(self, ssh, deployment, lease)
                        try: state = await launcher.start()
                        except DevelopmentFault as error:
                            if getattr(error, 'launch_not_submitted', False): start_sent = False
                            raise
                    else:
                        state = await control.call('start', role=deployment['role'], arguments=job['settings']['arguments'],
                            timeoutSeconds=job['settings']['timeoutSeconds'], serviceName=('S' + execution_id.replace('-', '')[:24]) if deployment['role'] == 'service' else '')
                    process = {'instanceId': state['instanceId'], 'generation': state['generation'], 'windowId': state['windowId'], 'serviceName': state.get('serviceName')}
                    if not process['instanceId'] or not process['generation'].isdigit() or int(process['generation']) < 1:
                        raise UnconfirmedGuestEffect('The guest start did not confirm a generation-owned process.')
                    save(self.work / 'started.json', {**intent, 'state': 'started', 'process': process})
                    store.update(job['id'], process=process, phase='guest_running',
                        readiness={'state': 'started', 'process': process, 'checkedAt': now()})
                    from job_control import Mailbox
                    from checks import evaluate
                    from output_files import collect
                    self.mailbox = Mailbox(job['id']); await self.mailbox.open()
                    stop_sent = False; service_checked = False; poll_delay = .2; last_poll = None
                    while True:
                        if launcher and state['state'] == 'running':
                            await launcher.refresh()
                        fresh_output = self.output(state); state['outputBase64'] = ''; self.last = state
                        changed = last_poll != state or fresh_output
                        poll_delay = .2 if changed else min(2, poll_delay * 1.6)
                        last_poll = dict(state)
                        if self.saved_observation != state:
                            save(self.work / 'observation.json', state); self.saved_observation = dict(state)
                        process['windowId'] = state['windowId']
                        from deskrun import frame_ready
                        native_ready = bool(launcher and frame_ready(store.get(job['id']), state))
                        readiness = {'state': 'ready' if state.get('serviceEndpointReady') or native_ready else 'started', 'process': process, 'checkedAt': now()}
                        if launcher and not native_ready and launcher.settled() and state['state'] == 'running':
                            readiness.update(state='unknown', reasonCode='desktop_content_unconfirmed',
                                reason='The process is confirmed; Desktop content remains unconfirmed. Inspect this original job without repeating the launch.')
                        current = store.get(job['id'])
                        observed = {'process': process, 'readiness': readiness, 'outputBytes': len(self.output_data),
                            'phase': 'completing_checks' if self.completion else ('desktop_content' if native_ready else ('window_visible' if state.get('windowVisible') else ('service_ready' if state.get('serviceEndpointReady') else 'guest_running'))),
                            'guestState': {k: v for k, v in state.items() if k != 'outputBase64'}}
                        if state['state'] != 'completed':
                            observed['check'] = evaluate(job['settings'], state, self.output_data, visual=current.get('visualAssessment'))
                        store.observe(job['id'], **observed)
                        if job['settings'].get('serviceResponseContains') and state.get('serviceEndpointReady') and not service_checked and not self.stop_requested and store.get(job['id'])['state'] == 'running':
                            service_checked = True
                            state = await control.call('service_check')
                            continue
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
                            completed_check = None
                            if self.completion:
                                from completion import result as completion_result
                                completed_check = completion_result(store, store.get(job['id']), state, data, files, self.completion, cancelled=self.stop_requested or store.get(job['id'])['state'] == 'stopping')
                            intent['state'] = 'closed'; save(self.work / 'closed.json', {**intent, 'completion': state, 'cleanupReceipt': closed,
                                **({'checkCompletion': completed_check, 'checkCompletionIntent': self.completion} if completed_check else {}),
                                'outputReceipt': {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}})
                            release(store.projects, vm['id'], job['id'])
                            stopped = state.get('stopReason'); terminal = 'interrupted' if stopped == 'user_stop' else ('failed' if stopped == 'timeout' else ('unknown' if state['exitCode'] is None else ('failed' if state['exitCode'] != 0 else 'completed')))
                            if completed_check and stopped == 'user_stop': terminal = 'interrupted' if completed_check['cancelled'] else completed_check['state']
                            final = store.update(job['id'], terminal, readiness={'state': 'unknown' if terminal == 'unknown' else 'completed', 'process': process, 'checkedAt': now()}, phase='timeout' if stopped == 'timeout' else ('checks_completed' if completed_check and terminal == 'completed' else ('stopped' if stopped else 'guest_completed')),
                                **({'checkCompletion': completed_check} if completed_check else {}),
                                exitCode=state['exitCode'], guestState={k: v for k, v in state.items() if k != 'outputBase64'},
                                error='Guest execution exceeded its time limit.' if stopped == 'timeout' else ('Check completion could not confirm every criterion.' if completed_check and terminal != 'completed' else None))
                            if completed_check:
                                from actions import finish
                                receipt = finish(store, self.completion['requestId'], {'jobId': job['id'], 'state': terminal, 'closed': True})
                                if self.completion_future and not self.completion_future.done(): self.completion_future.set_result(receipt)
                            return final
                        if state['state'] == 'unknown': raise UnconfirmedGuestEffect('The generation-owned process status became unknown.')
                        guard(store, job, lease, allow_stopping=True)
                        if (self.stop_requested or store.get(job['id'])['state'] == 'stopping') and not stop_sent:
                            stop_sent = True; state = await control.call('stop')
                        else:
                            pending = await self.mailbox.next(poll_delay, self.wake)
                            if pending is None:
                                if self.stop_requested and not stop_sent:
                                    stop_sent = True; state = await control.call('stop')
                                else: state = await control.call('poll')
                            else:
                                message, future = pending; poll_delay = .2
                                try:
                                    state, result = await self.action(message, state, control, lease, process)
                                    if result.get('pendingCompletion'): self.completion_future = future
                                    elif not future.done(): future.set_result(result)
                                except DevelopmentFault as error:
                                    if not future.done(): future.set_exception(error)
                                    if getattr(error, 'uncertain', False): raise
                except BaseException as error:
                    if hello_ready and not start_sent and not (self.work / 'closed.json').exists():
                        try:
                            closed = await control.call('finish')
                            if closed.get('closed') and closed.get('watchdogRemoved'):
                                save(self.work / 'closed.json', {**intent, 'state': 'closed', 'applicationStarted': False,
                                    'launchRejected': bool(getattr(error, 'launch_not_submitted', False)), 'error': str(error), 'cleanupReceipt': closed})
                                release(store.projects, vm['id'], job['id'])
                        except Exception: pass
                    if start_sent and not (self.work / 'closed.json').exists():
                        if isinstance(error, UnconfirmedGuestEffect): raise
                        raise UnconfirmedGuestEffect('Guest control ended without a confirmed cleanup receipt. Its watchdog remains responsible; no start was replayed.') from error
                    raise
                finally:
                    if self.completion_future and not self.completion_future.done():
                        self.completion_future.set_exception(UnconfirmedGuestEffect('The original check completion has no confirmed cleanup receipt. Do not repeat it.'))
                    if self.mailbox: await self.mailbox.close()
                    await control.close(); self.control = None
