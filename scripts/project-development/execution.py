"""Bounded, generation-owned guest executions independent of browser/model turns."""
import asyncio
import base64
import uuid
from contracts import DevelopmentFault, UnconfirmedGuestEffect, LIMITS, digest
from jobs import folder, now
from layout import save
from lease import VmLease
from access import Access, SshTransport, image_profile
from vm_client import vm_call
from guest_control import GuestControl
from sftp import download

class Execution:
    def __init__(self, store, job):
        self.store, self.job = store, job
        self.work = folder(store.root / 'ExecutionWork' / job['id'])
        self.log = store.evidence(job['id']) / 'output.log'
        self.stop_requested = False; self.control = None; self.last = None

    def output(self, state):
        try: data = base64.b64decode(state.get('outputBase64', ''), validate=True)
        except ValueError: raise UnconfirmedGuestEffect('The guest returned an invalid output frame.') from None
        if len(data) > 24577: raise UnconfirmedGuestEffect('The guest output frame exceeds the limit.')
        size = self.log.stat().st_size if self.log.exists() else 0
        if size + len(data) > LIMITS['outputBytes']: state['outputIncomplete'] = True
        with self.log.open('ab') as stream: stream.write(data[:max(0, LIMITS['outputBytes'] - size)])

    async def run(self):
        from vm_worker import broker_call, guard
        store, job = self.store, self.job
        deployment = store.deployment(job['deploymentId']); vm = job['binding']; profile = image_profile(vm)
        if deployment.get('helperCapabilities', {}).get('controlVersion') != 2 or deployment.get('helperCapabilities', {}).get('watchdogVersion') != 1:
            raise DevelopmentFault('Deploy again with the current guest controller before running.')
        if deployment['role'] not in ('terminal', 'desktop', 'service') or deployment['kind'] != 'R4X':
            raise DevelopmentFault('This module needs a qualified role-specific test host. Direct execution is unavailable.')
        scope = {'kind': 'job', 'projectId': store.id, 'projectRevision': job['projectRevision'],
            'vmRevision': vm['revision'], 'imageId': vm['imageId'], 'imageSha256': vm['imageSha256'], 'jobId': job['id']}
        with VmLease(store.projects, vm['id'], scope) as lease:
            info = await vm_call(lease, 'info')
            from quarantine import admission, claim, release
            admission(store.projects, vm['id'], info['vm']['state'])
            if info['vm']['state'] != 'running': raise DevelopmentFault('The deployment boot has ended. Deploy again to the prepared VM before running.')
            target = await broker_call({'operation': 'bind_target', 'projectId': store.id, 'jobId': job['id'],
                'leaseId': lease.id, 'token': lease.token, 'helperSha256': deployment['target']['helperSha256']})
            if target != deployment['target']: raise DevelopmentFault('The deployment belongs to an older VM boot or revision. Deploy again before running.')
            scope['bootId'] = target['bootId']; save(lease.root / 'leases' / (lease.id + '.json'), lease.value)
            guard(store, job, lease, allow_stopping=True)
            access = Access(store.projects, store.r4os, None)
            async with SshTransport(access, vm, lease) as ssh:
                version = await ssh.exec('VER')
                if version['exitCode'] or ('R4OS Release ' + profile['guest']['release']) not in version['output'] or ('Kernel active ' + profile['guest']['kernel']) not in version['output']:
                    raise DevelopmentFault('The authenticated runtime differs from the deployment guest profile.')
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
                    'target': target, 'role': deployment['role'], 'settings': job['settings'], 'state': 'intent', 'createdAt': now()}
                save(self.work / 'intent.json', intent)
                claim(store.projects, vm['id'], {'jobId': job['id'], 'projectId': store.id, 'executionId': execution_id,
                    'target': target, 'deploymentId': deployment['id']})
                start_sent = False
                try:
                    hello = await control.open(); save(self.work / 'controller.json', hello)
                    guard(store, job, lease, allow_stopping=True)
                    if self.stop_requested or store.get(job['id'])['state'] == 'stopping':
                        closed = await control.call('finish')
                        if not closed.get('closed') or not closed.get('watchdogRemoved'): raise UnconfirmedGuestEffect('Watchdog stop was not confirmed.')
                        save(self.work / 'closed.json', {**intent, 'state': 'closed', 'applicationStarted': False})
                        release(store.projects, vm['id'], job['id'])
                        return store.update(job['id'], 'interrupted', phase='stopped', error='Stopped before application launch.')
                    store.update(job['id'], phase='starting_guest', executionId=execution_id)
                    # The start is sent once. Missing acknowledgements become unknown.
                    start_sent = True
                    state = await control.call('start', role=deployment['role'], arguments=job['settings']['arguments'],
                        timeoutSeconds=job['settings']['timeoutSeconds'], serviceName=store.project['moduleName'] if deployment['role'] == 'service' else '')
                    process = {'instanceId': state['instanceId'], 'generation': state['generation'], 'windowId': state['windowId'], 'serviceName': state.get('serviceName')}
                    if not process['instanceId'] or not process['generation'].isdigit() or int(process['generation']) < 1:
                        raise UnconfirmedGuestEffect('The guest start did not confirm a generation-owned process.')
                    save(self.work / 'started.json', {**intent, 'state': 'started', 'process': process})
                    store.update(job['id'], process=process, phase='guest_running')
                    stop_sent = False
                    while True:
                        self.output(state); self.last = state
                        save(self.work / 'observation.json', state)
                        process['windowId'] = state['windowId']
                        store.update(job['id'], process=process, phase=('window_visible' if state.get('windowVisible') else ('service_ready' if state.get('serviceEndpointReady') else 'guest_running')), guestState={k: v for k, v in state.items() if k != 'outputBase64'})
                        if state['state'] == 'completed':
                            if not state['closeConfirmed']: raise UnconfirmedGuestEffect('The process completion was not fully reaped.')
                            closed = await control.call('finish')
                            if not closed.get('closed') or not closed.get('serviceRemoved', False) or not closed.get('watchdogRemoved'):
                                raise UnconfirmedGuestEffect('Owned service cleanup was not confirmed.')
                            intent['state'] = 'closed'; save(self.work / 'closed.json', {**intent, 'completion': state})
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
                            await asyncio.sleep(.2); state = await control.call('poll')
                except BaseException as error:
                    if start_sent and not (self.work / 'closed.json').exists():
                        raise UnconfirmedGuestEffect('Guest control ended without a confirmed cleanup receipt. Its watchdog remains responsible; no start was replayed.') from error
                    raise
                finally: await control.close(); self.control = None
