#!/usr/bin/env python3
"""One project-bound VM job. Compilers and remote transport have separate roots."""
import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
import signal
import sys
import uuid

from contracts import ACTIVE, APP, DevelopmentFault, LIMITS, digest, encode, protocol
from jobs import Jobs, folder, now
from store import connect, public
from layout import save
from access import Access, SshTransport, transport_profile, guest_version
from lease import VmLease, inspect
from vm_client import vm_call
from helper import prepare_helper
from sftp import batch, download, publish_file, quote


async def broker_call(request):
    reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(os.environ.get('STUDIO_DEVELOPMENT_SOCKET', '/run/r4os-studio-development/host.sock'), limit=2097153), 5)
    try:
        writer.write((encode(request) + '\n').encode()); await writer.drain()
        value = json.loads(await asyncio.wait_for(reader.readline(), 20))
        if value.get('error'):
            from contracts import UnconfirmedGuestEffect
            if value.get('uncertain'): raise UnconfirmedGuestEffect(value['error'])
            raise DevelopmentFault(value['error'], value.get('code', 503), reason_code=value.get('reasonCode'))
        return value['result']
    finally:
        writer.close(); await writer.wait_closed()


def guard(store, job, lease=None, allow_stopping=False):
    if not allow_stopping or store.get(job['id'])['state'] != 'stopping':
        from authorization import authorize_job
        authorize_job(store, job, allow_stopping=allow_stopping)
    if store.get(job['id'])['state'] not in (('running', 'stopping') if allow_stopping else ('running',)): raise DevelopmentFault('The development job is stopping.')
    db = connect(store.projects)
    try: current = public(db.execute("SELECT * FROM projects WHERE id=? AND state='ready'", (store.id,)).fetchone())
    finally: db.close()
    if (current['revision'] != job['projectRevision'] or current['vmId'] != job['binding']['id'] or current['pins'] != job['pins']):
        raise DevelopmentFault('Project settings or its VM assignment changed. No further guest action was authorized.')
    if lease: inspect(store.projects, lease.id, lease.token)


class Deployment:
    def __init__(self, store, job):
        self.store, self.job = store, job; self.log = store.evidence(job['id']) / 'output.log'
        self.work = folder(store.root / 'DeployWork' / job['id'])

    def note(self, text):
        if self.log.exists() and self.log.stat().st_size >= LIMITS['outputBytes']: return
        with self.log.open('ab') as stream: stream.write((text[:2048] + '\n').encode())

    def phase(self, phase):
        self.store.update(self.job['id'], phase=phase); self.note(phase.replace('_', ' ').capitalize())

    async def run(self):
        store, job = self.store, self.job; artifact = store.artifact(job['artifactId']); vm = job['binding']
        profile = transport_profile()
        scope = {'kind': 'job', 'projectId': store.id, 'projectRevision': job['projectRevision'],
            'vmRevision': vm['revision'], 'imageId': vm['imageId'], 'imageSha256': vm['imageSha256'], 'jobId': job['id']}
        from queue_lease import reserve
        async with reserve(store, job, scope) as lease:
            self.phase('preparing_vm'); info = await vm_call(lease, 'info'); guard(store, job)
            from quarantine import admission
            admission(store.projects, vm['id'], info['vm']['state'])
            if info['vm']['state'] != 'running':
                raise DevelopmentFault('Start the assigned VM with Start project VM before deploying. If this session has no VM-start tool, start it in Virtual Machines or create a new session. Deployment does not have VM-start permission.', reason_code='vm_start_required')
            from exchange import require_tree
            require_tree(info)
            access = Access(store.projects, store.r4os, None)
            if not vm.get('networkEnabled') or not access.record(vm['id'])['enabled']:
                raise DevelopmentFault('Enable Network and development access for the assigned VM before deploying.', reason_code='development_access_unavailable')
            self.phase('preparing_helper'); helper = await prepare_helper(store.projects, store.r4os, profile); guard(store, job, lease)
            target = await broker_call({'operation': 'bind_target', 'projectId': store.id, 'jobId': job['id'],
                'leaseId': lease.id, 'token': lease.token, 'helperSha256': helper['sha256']})
            scope['bootId'] = target['bootId']; save(lease.root / 'leases' / (lease.id + '.json'), lease.value)
            guard(store, job, lease); self.phase('authenticating')
            last_error = None
            for attempt in range(36):
                guard(store, job, lease)
                try:
                    async with SshTransport(access, vm, lease) as ssh:
                        version = await ssh.exec('VER')
                        guest_version(version)
                        ssh.publish_host_key(); return await self.transfer(ssh, lease, artifact, helper, target)
                except DevelopmentFault as error:
                    last_error = error
                    # Only pre-transfer readiness failures can be retried. Once
                    # transfer starts, ambiguous effects are always preserved.
                    if self.store.get(job['id'])['phase'] != 'authenticating' or 'not ready' not in str(error): raise
                    if attempt < 35: await asyncio.sleep(2)
            raise last_error or DevelopmentFault('The guest did not become ready.')

    async def transfer(self, ssh, lease, artifact, helper, target):
        store, job = self.store, self.job; guard(store, job, lease); self.phase('resolving_exchange')
        from exchange import resolve, require_tree, directory, inventory, preflight
        info = await vm_call(lease, 'info'); require_tree(info)
        exchange = await resolve(ssh, info, target); target = {**target, 'exchange': exchange}
        store.update(job['id'], target=target)
        guard(store, job, lease); self.phase('checking_exchange_capacity')
        entries = await inventory(ssh, exchange)
        build = next((item for item in entries if item['path'].lower() == 'build'), None)
        if build and not build['directory']: raise DevelopmentFault('Build is an existing file. No guest files were changed.')
        self.phase('preparing_directory')
        project_name = 'P' + hashlib.sha256(store.id.encode()).hexdigest()[:7].upper()
        project_dir = directory(target, project_name); ssh.package_root = project_dir
        project_relative = 'build/' + project_name.lower()
        project_exists = any(item['path'].lower() == project_relative and item['directory'] for item in entries)
        preflight(entries, [artifact['files'][0]['bytes'], helper['bytes'], helper['watchdog']['bytes']],
                  5 + (0 if project_exists else 1), 1 + (0 if project_exists else 1) + (0 if build else 1), len(job['settings'].get('outputFiles', [])))
        if not build:
            guard(store, job, lease); await batch(ssh, ['mkdir ' + quote('/' + exchange['drive'] + '/Build')])
        expected = {'schema': 1, 'interface': 'r4os-studio-project', 'projectId': store.id, 'exchangeGeneration': exchange['generation']}
        owner = self.work / 'OWNER.JSN'; owner.write_text(encode(expected) + '\n')
        existing = self.work / 'existing-owner.json'
        if await download(ssh, project_dir + '/OWNER.JSN', existing, maximum=4096, allow_missing=True):
            try: actual = json.loads(existing.read_text())
            except (OSError, ValueError): raise DevelopmentFault('The guest project ownership receipt is invalid.')
            if actual != expected: raise DevelopmentFault('The guest project directory belongs to another owner. All files were preserved.')
        else:
            if project_exists: raise DevelopmentFault('The existing project folder has no matching ownership receipt. Its files were preserved.')
            guard(store, job, lease)
            await batch(ssh, ['mkdir ' + quote(project_dir)])
            save(self.work / 'project-directory.json', {'path': project_dir, 'created': True, 'owner': expected})
            guard(store, job, lease)
            await publish_file(ssh, owner, project_dir + '/OWNER.JSN', digest(owner))
        deployment_id = str(uuid.uuid4()); guest_dir = directory(target, project_name, 'D' + deployment_id.replace('-', '')[:7].upper())
        save(self.work / 'intent.json', {'deploymentId': deployment_id, 'projectId': store.id, 'guestDirectory': guest_dir,
            'artifactId': artifact['id'], 'target': target, 'helperSha256': helper['sha256']})
        store.update(job['id'], package={'format': 'exchange-build-v1', 'relativeDirectory': '/'.join(guest_dir.split('/')[2:]),
            'guestDirectory': exchange['drive'] + ':' + chr(92) + chr(92).join(guest_dir.split('/')[2:])})
        guard(store, job, lease); await batch(ssh, ['mkdir ' + quote(guest_dir)])
        self.phase('transferring'); receipts = []
        ownership = self.work / 'DEPLOY.JSN'
        ownership.write_text(encode({'interface': 'r4os-studio-deployment-owner', 'schema': 1, 'projectId': store.id, 'deploymentId': deployment_id, 'exchangeGeneration': exchange['generation']}) + '\n')
        guard(store, job, lease)
        receipts.append(await publish_file(ssh, ownership, guest_dir + '/DEPLOY.JSN', digest(ownership)))
        module = artifact['files'][0]
        source = store.root / 'Artifacts' / artifact['id'] / artifact['entry']
        for path, name, checksum in ((source, 'APP.' + artifact['kind'], module['sha256']), (helper['path'], 'STHELP.R4X', helper['sha256']), (helper['watchdog']['path'], 'STWATCH.R4X', helper['watchdog']['sha256'])):
            guard(store, job, lease)
            receipt = await publish_file(ssh, path, guest_dir + '/' + name, checksum); receipts.append(receipt)
            self.note('Verified ' + name + ' · ' + checksum)
        descriptor = {'schema': 1, 'interface': 'r4os-studio-deployment', 'projectId': store.id,
            'deploymentId': deployment_id, 'artifactId': artifact['id'], 'packageSha256': artifact['packageSha256'],
            'sourceSha256': artifact['sourceSha256'], 'manifestSha256': artifact['manifestSha256'],
            'target': target, 'pins': job['pins'], 'helperPins': helper['pins'],
            'watchdogSha256': helper['watchdog']['sha256'], 'files': receipts, 'helperSha256': helper['sha256']}
        package = self.work / 'PACKAGE.JSN'; package.write_text(encode(descriptor) + '\n')
        guard(store, job, lease); receipts.append(await publish_file(ssh, package, guest_dir + '/PACKAGE.JSN', digest(package)))
        self.phase('checking_helper'); instance = str(uuid.uuid4())
        guest_path = exchange['drive'] + ':' + chr(92) + chr(92).join(guest_dir.split('/')[2:])
        response = await ssh.exec(guest_path + chr(92) + 'STHELP.R4X ' + instance)
        try: hello = json.loads(response['output'].strip())
        except ValueError: raise DevelopmentFault('The verified guest helper did not return a valid handshake.')
        if (response['exitCode'] != 0 or hello.get('version') != 1 or hello.get('instance') != instance
            or hello.get('requestId') != instance or hello.get('success') is not True
            or hello.get('result', {}).get('interface') != 'r4os-studio-guest'
            or not hello['result'].get('processHandles') or not hello['result'].get('fileRead')):
            raise DevelopmentFault('The verified guest helper does not expose the required process/file contract.')
        def normalize(path):
            if not isinstance(path, str): return ''
            return re.sub(r'\\+', lambda _: chr(92), path.replace('/', chr(92)).rstrip(chr(0))).upper()
        if normalize(hello['result'].get('modulePath')) != normalize(guest_path + chr(92) + 'STHELP.R4X'):
            raise DevelopmentFault('The helper handshake belongs to another guest module path.')
        guard(store, job, lease); self.phase('publishing')
        record = {'format': 'exchange-build-v1', 'readiness': {'state': 'transferred', 'checkedAt': now()},
            'helperPins': helper['pins'], 'watchdogSha256': helper['watchdog']['sha256'], 'id': deployment_id, 'projectId': store.id, 'jobId': job['id'], 'artifactId': artifact['id'],
            'packageSha256': artifact['packageSha256'], 'sourceSha256': artifact['sourceSha256'],
            'manifestSha256': artifact['manifestSha256'], 'target': target, 'role': artifact['role'], 'kind': artifact['kind'],
            'guestDirectory': guest_path, 'entry': 'APP.' + artifact['kind'], 'helper': 'STHELP.R4X',
            'helperCapabilities': hello['result'], 'helperSourceSha256': helper['sourceSha256'],
            'files': receipts, 'pins': job['pins'], 'createdAt': now()}
        save(self.work / 'deployment.json', record)
        self.note('Deployment verified. No project application was started.')
        return store.publish_deployment(job['id'], record)


async def main():
    os.umask(0o077); protocol(APP)
    meta = json.loads(Path(sys.argv[1]).read_text()); store = Jobs(meta['projects'], meta['r4os'], meta['projectId']); job = store.get(meta['jobId'])
    if len(sys.argv) > 2:
        if job['state'] in ACTIVE: store.update(job['id'], 'unknown', phase='recovery', error='The VM worker ended without a confirmed result. No guest action was replayed.')
        store.close(); return
    task = asyncio.current_task(); interrupted = False; execution = None
    def stop():
        nonlocal interrupted
        interrupted = True; store.update(job['id'], 'stopping', phase='stopping')
        if execution is not None: execution.stop_requested = True
        else: task.cancel()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(sig, stop)
    try:
        if job['state'] not in ('queued', 'starting'): return
        store.update(job['id'], 'running', phase='preparing')
        if job['kind'] == 'vm_start':
            from vm_start import VmStart
            try: await asyncio.wait_for(VmStart(store, job).run(), LIMITS['vmStartTimeoutSeconds'])
            except asyncio.TimeoutError: raise DevelopmentFault('VM start and SSH readiness exceeded the host deadline. Inspect the saved job before retrying.') from None
        elif job['kind'] == 'deploy': await asyncio.wait_for(Deployment(store, job).run(), 600)
        elif job['kind'] == 'execution':
            from execution import Execution
            execution = Execution(store, job)
            await asyncio.wait_for(execution.run(), job['settings']['timeoutSeconds'] + 240)
        else: raise DevelopmentFault('This VM worker does not support this job kind.')
    except BaseException as error:
        message = str(error) if isinstance(error, DevelopmentFault) else 'The VM operation did not complete. Inspect its preserved transfer receipts before retrying.'
        uncertain = bool(getattr(error, 'uncertain', False))
        state = 'unknown' if uncertain else ('interrupted' if interrupted else 'failed')
        if job['kind'] == 'execution':
            from checks import evaluate
            current = store.get(job['id'])
            output = store.evidence(job['id']) / 'output.log'
            check = evaluate(job['settings'], current.get('guestState') or {'state': 'unknown'},
                output.read_bytes() if output.exists() else b'', current.get('outputFiles', []), current.get('visualAssessment'))
            if uncertain:
                check = {**check, 'state': 'not-run' if check['state'] == 'not-run' else 'inconclusive',
                    'findings': [*check['findings'], 'Guest control ended without a confirmed process result.']}
            store.update(job['id'], check=check)
        readiness = store.get(job['id']).get('readiness')
        if job['kind'] == 'execution' and (not readiness or readiness.get('state') != 'unsupported'):
            readiness = {'state': state, 'checkedAt': now(), 'reason': message}
        store.update(job['id'], state, readiness=readiness, phase='stopped' if interrupted else 'failed', error=message,
                     reasonCode=getattr(error, 'reason_code', None),
                     nextStep={'vm_start_required': 'Start the assigned VM with its permitted VM-start tool, or use Virtual Machines, then deploy again.',
                         'exchange_worker_upgrade_required': 'Stop and start the assigned VM in Virtual Machines to adopt its current Exchange worker, then deploy again.',
                         'development_access_unavailable': 'Enable Network and development access in the assigned VM settings before deploying.'}.get(getattr(error, 'reason_code', None)),
                     exitCode=getattr(error, 'exit_code', None))
    finally: store.close()


if __name__ == '__main__': asyncio.run(main())
