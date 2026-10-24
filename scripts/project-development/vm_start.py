"""One assigned-VM start followed by bounded authenticated SSH readiness.

No compiler, guest helper, upload or application launch is used here.
"""
import asyncio
import re
from types import SimpleNamespace

from contracts import DevelopmentFault, SshNotReady, UnconfirmedGuestEffect, LIMITS
from jobs import folder, now
from layout import save


async def bind(host, request, peer_pid):
    from access import vm_config
    from authorization import authorize_job
    from lease import inspect
    from vm_client import vm_call
    complete = request['operation'] == 'complete_vm_start'
    if set(request) != {'operation', 'projectId', 'jobId', 'leaseId', 'token'} | ({'version'} if complete else set()):
        raise DevelopmentFault('Invalid private VM start binding.', 400)
    lease = inspect(host.config['projects'], request['leaseId'], request['token'], check_boot=complete)
    scope = lease['scope']
    if (lease['pid'] != peer_pid or scope.get('kind') != 'job' or scope.get('projectId') != request['projectId']
            or scope.get('jobId') != request['jobId']):
        raise DevelopmentFault('This VM start reservation belongs to another worker.', 403)
    store = host.store(request['projectId'])
    try:
        job = store.get(request['jobId']); vm = vm_config(store.r4os, lease['vmId'])
        authorize_job(store, job)
        if (job['kind'] != 'vm_start' or job['state'] != 'running' or not job.get('agentRunId') or job['binding']['id'] != vm['id']
                or any(job['binding'][k] != vm[k] for k in ('revision', 'imageId', 'imageSha256'))
                or store.project['vmId'] != vm['id'] or store.project['revision'] != job['projectRevision']):
            raise DevelopmentFault('This VM start no longer has its original project binding.')
        info = await vm_call(SimpleNamespace(id=request['leaseId'], token=request['token']), 'info')
        if info['vm']['state'] != 'running': raise DevelopmentFault('The assigned VM is no longer running.')
        boot = await host.boots.ensure(vm, info['invocationId'])
        record = host.access.record(vm['id'])
        if complete:
            target = job.get('vmStart') or {}
            if (target.get('bootId') != boot['bootId'] or scope.get('bootId') != boot['bootId']
                    or target.get('accessRevision') != record['revision'] or not record['enabled']):
                raise DevelopmentFault('The VM boot or saved access changed during startup.')
            version = request['version']
            if (not isinstance(version, dict) or set(version) != {'release', 'kernel'} or
                    any(not isinstance(v, str) or not re.fullmatch(r'\d+\.\d+\.\d+', v) for v in version.values())):
                raise DevelopmentFault('Invalid authenticated guest version receipt.', 400)
            authorize_job(store, job)
            if store.get(job['id'])['state'] != 'running': raise DevelopmentFault('The VM start was stopped.')
            from access import same_host_image
            if not same_host_image(record, vm) or not record.get('hostKeyFingerprint'):
                raise DevelopmentFault('The authenticated SSH host key has no current VM binding.')
            current = host.boots.values.get(vm['id'], {})
            if current.get('bootId') != boot['bootId'] or not current.get('connected'):
                raise DevelopmentFault('The VM boot changed before SSH readiness was published.')
            checked = now()
            record.pop('lastError', None); record.pop('lastErrorVmRevision', None)
            record['readiness'] = {'checkedAt': checked, 'vmRevision': vm['revision'], 'bootId': boot['bootId'], **version}
            save(host.access.directory(vm['id']) / 'access.json', record)
            target = {**target, 'ready': True, 'checkedAt': checked, 'guestRelease': version['release'], 'guestKernel': version['kernel']}
            save(folder(store.root / 'VmStartWork' / job['id']) / 'ready.json', target)
            return store.update(job['id'], 'completed', phase='ssh_ready', vmStart=target, exitCode=0, error=None)
        target = {'ready': False, 'started': bool((job.get('vmStart') or {}).get('started')), 'vmId': vm['id'],
                  'vmRevision': vm['revision'], 'imageId': vm['imageId'], 'imageSha256': vm['imageSha256'],
                  'bootId': boot['bootId'], 'accessRevision': record['revision']}
        store.update(job['id'], vmStart=target)
        return target
    finally: store.close()


class VmStart:
    def __init__(self, store, job):
        self.store, self.job = store, job
        self.work = folder(store.root / 'VmStartWork' / job['id'])
        self.log = store.evidence(job['id']) / 'output.log'

    def phase(self, value, message):
        self.store.update(self.job['id'], phase=value)
        with self.log.open('ab') as stream: stream.write((message + '\n').encode())

    async def run(self):
        from access import Access, SshTransport, guest_version
        from vm_client import vm_call
        from vm_worker import guard, broker_call
        from queue_lease import reserve
        from quarantine import admission
        store, job, vm = self.store, self.job, self.job['binding']
        scope = {'kind': 'job', 'projectId': store.id, 'projectRevision': job['projectRevision'], 'jobId': job['id'],
                 'vmRevision': vm['revision'], 'imageId': vm['imageId'], 'imageSha256': vm['imageSha256']}
        async with reserve(store, job, scope, timeout=90) as lease:
            guard(store, job, lease)
            info = await vm_call(lease, 'info'); admission(store.projects, vm['id'], info['vm']['state'])
            started = False
            if info['vm']['state'] in ('stopped', 'failed'):
                self.phase('starting_vm', 'Starting the assigned virtual machine.')
                save(self.work / 'start-intent.json', {'jobId': job['id'], 'vmId': vm['id'], 'createdAt': now()})
                try: await vm_call(lease, 'start')
                except DevelopmentFault as error:
                    if error.code < 500: raise
                    raise UnconfirmedGuestEffect('The VM start was not confirmed. ' + str(error) + ' It was not repeated; inspect this job and the VM state.') from None
                started = True
            elif info['vm']['state'] not in ('running', 'starting'):
                raise DevelopmentFault('Wait for the assigned VM to finish stopping before starting it.')
            store.update(job['id'], vmStart={'started': started, 'ready': False})
            self.phase('waiting_for_vm', 'Waiting for the VM process and its boot monitor.')
            deadline = asyncio.get_running_loop().time() + LIMITS['vmReadyTimeoutSeconds']
            while True:
                guard(store, job, lease); info = await vm_call(lease, 'info')
                if info['vm']['state'] == 'running': break
                if info['vm']['state'] in ('stopped', 'failed', 'stopping'): raise DevelopmentFault('The assigned VM stopped before SSH became ready.')
                if asyncio.get_running_loop().time() >= deadline: raise DevelopmentFault('VM startup timed out before its process became ready.')
                await asyncio.sleep(1)
            target = await broker_call({'operation': 'bind_vm_start', 'projectId': store.id, 'jobId': job['id'],
                                        'leaseId': lease.id, 'token': lease.token})
            scope['bootId'] = target['bootId']; save(lease.root / 'leases' / (lease.id + '.json'), lease.value)
            access = Access(store.projects, store.r4os, None)
            self.phase('waiting_for_ssh', 'Waiting for authenticated SSH and the R4OS version response.')
            async with SshTransport(access, vm, lease) as ssh:
                if ssh.record['revision'] != target['accessRevision']:
                    raise DevelopmentFault('Saved VM access changed during startup.')
                while True:
                    guard(store, job, lease)
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0: raise DevelopmentFault('SSH readiness timed out. The VM remains running; check its console and saved access settings.')
                    try:
                        response = await ssh.exec('VER', timeout=min(10, remaining))
                        version = guest_version(response); guard(store, job, lease)
                        ssh.publish_host_key()
                        result = await broker_call({'operation': 'complete_vm_start', 'projectId': store.id, 'jobId': job['id'],
                            'leaseId': lease.id, 'token': lease.token, 'version': version})
                        with self.log.open('ab') as stream: stream.write(b'SSH ready. Authenticated guest version confirmed.\n')
                        return result
                    except SshNotReady:
                        await asyncio.sleep(min(2, max(0, deadline - asyncio.get_running_loop().time())))
