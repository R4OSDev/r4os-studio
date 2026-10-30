#!/usr/bin/env python3
"""Private fixed-operation coordinator. It never replays a queued effect."""
import asyncio
import json
import os
from pathlib import Path
import re
import signal
import socket
import sqlite3
import struct

from contracts import APP, ACTIVE, DevelopmentFault, UnconfirmedGuestEffect, LIMITS, encode, identity, protocol
from jobs import Jobs, folder
from layout import save
from profiles import eligible
from store import ProjectFault, connect

UNIT = 'r4os-studio-development@{}.service'
VM_UNIT = 'r4os-studio-development-vm@{}.service'


def job_unit(job_id, kind='build'): return (UNIT if kind in ('build', 'package') else VM_UNIT).format(identity(job_id))


async def systemctl(*args):
    process = await asyncio.create_subprocess_exec('/usr/bin/systemctl', '--no-ask-password', *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    output, _ = await asyncio.wait_for(process.communicate(), 20)
    if process.returncode: raise DevelopmentFault('The development worker service could not be controlled.', 503)
    return output.decode().strip()


class Host:
    def __init__(self, config):
        self.config = config; self.lock = asyncio.Lock(); self.active = {}; self.unbound = set(); self.connections = set()
        self.git_validation = asyncio.Semaphore(1); self.git_validating = 0
        self.root = folder(Path(config['projects']) / '.studio/development')
        from boot import BootWatch
        from access import Access
        self.boots = BootWatch(config['projects']); self.access = Access(config['projects'], config['r4os'], self.boots)

    def store(self, project_id): return Jobs(self.config['projects'], self.config['r4os'], project_id)

    async def alive(self, job_id, kind='build'):
        return await systemctl('show', job_unit(job_id, kind), '--property=ActiveState', '--value') in ('active', 'activating', 'deactivating', 'reloading')

    def metadata(self, path):
        if path.resolve(strict=True) != path.absolute(): raise ValueError('Invalid worker metadata.')
        value = json.loads(path.read_text())
        for key in ('jobId', 'projectId'): identity(value[key])
        if value['schema'] != 1 or path.parent.name != value['jobId']: raise ValueError('Invalid worker identity.')
        if any(value[k] != self.config[k] for k in ('projects', 'r4os')): raise ValueError('Invalid worker storage.')
        release = Path(value['releaseRoot']).resolve(strict=True)
        if not release.is_relative_to('/opt/r4os-studio/releases'): raise ValueError('Invalid original worker release.')
        protocol(release); info = json.loads((release / 'release.json').read_text())
        if (info['id'], info['version']) != (value['release'], value['version']): raise ValueError('The worker release identity changed.')
        return value

    async def recover(self):
        manifests = {}
        for path in self.root.glob('*/worker.json'):
            try:
                value = self.metadata(path); manifests[value['jobId']] = value
            except Exception: continue
        db = connect(Path(self.config['projects']))
        try: projects = [row[0] for row in db.execute("SELECT id FROM projects WHERE state='ready'")]
        finally: db.close()
        for project_id in projects:
            if not (Path(self.config['projects']) / project_id / 'Development/Development.sqlite').is_file(): continue
            store = self.store(project_id)
            try:
                for row in store.db.execute('SELECT id FROM jobs WHERE busy=1').fetchall():
                    meta = manifests.get(row['id'])
                    if meta and meta['projectId'] == project_id and await self.alive(row['id'], meta.get('kind', 'build')): self.active[row['id']] = meta
                    else: store.update(row['id'], 'unknown', phase='recovery', error='The job ended without a confirmed result. It was not restarted.')
                from recovery import local
                for row in store.db.execute("SELECT id FROM jobs WHERE state='unknown'").fetchall():
                    meta = manifests.get(row['id'])
                    if not meta or meta['projectId'] != project_id: continue
                    if meta and await self.alive(row['id'], meta.get('kind', 'build')): continue
                    try: local(store, store.get(row['id']))
                    except Exception: pass  # Preserve damaged/incomplete records; never replay a job.
            finally: store.close()
        await self.refresh()

    async def refresh(self):
        for job_id, meta in list(self.active.items()):
            if await self.alive(job_id, meta.get('kind', 'build')): continue
            try: store = self.store(meta['projectId'])
            except ProjectFault as error:
                if error.code != 404: raise
                self.active.pop(job_id, None); continue
            try: store.update(job_id, 'unknown', phase='recovery', error='The worker ended without a confirmed result. It was not restarted.')
            finally: store.close()
            self.active.pop(job_id, None)
        raw = await systemctl('list-units', '--all', '--state=active,activating,deactivating,reloading', '--plain', '--no-legend', '--no-pager', 'r4os-studio-development@*.service', 'r4os-studio-development-vm@*.service')
        units = set()
        for line in raw.splitlines():
            match = re.match(r'^r4os-studio-development(?:-vm)?@([a-f0-9-]{36})\.service\s', line.strip())
            if match: units.add(identity(match[1]))
        self.unbound = units - set(self.active)

    def options(self, store):
        from contracts import hash_value
        project = store.project; image = None; vm = None
        if project['vmId']:
            try:
                path = store.r4os / 'Instances' / identity(project['vmId']) / 'vm.json'
                if path.resolve(strict=True) != path: raise ValueError()
                vm = json.loads(path.read_text()); image = {'id': vm['imageId'], 'sha256': vm['imageSha256']}
            except (OSError, ValueError, KeyError): pass
        match = eligible(project, image)
        access = self.access.public(project['vmId']) if image else None
        unavailable = {'available': False, 'reason': 'The guest deployment adapter is not installed yet.'}
        if not match['available']: unavailable = {'available': False, 'reason': match['reason']}
        elif access and not access['available']: unavailable = {'available': False, 'reason': access['reason']}
        if project['vmId'] and not image:
            unavailable = {'available': False, 'reason': 'Assigned VM metadata is unavailable. Development host maintenance is required.'}
        deploy = unavailable
        if image and access and access['available']:
            deploy = {'available': True}
        from profiles import runner
        evidence_capabilities = runner().get('evidenceCapabilities', {}).get(project['template'])
        from desktop_budget import options as desktop_budget
        launch_budget = desktop_budget(store,vm)
        return {'revision': hash_value({'project': project['revision'], 'settings': store.settings()['revision'], 'image': image,
                    'evidenceCapabilities': evidence_capabilities,'desktopLaunchBudget':launch_budget}),
            'evidenceCapabilities': evidence_capabilities,'desktopLaunchBudget':launch_budget,
            'startVm': ({'available': True} if image and access and access['available'] else
                {'available': False, 'reason': access['reason'] if access else 'Assign an available virtual machine.'}),
            'build': {'available': True}, 'deploy': deploy, 'execute': ({'available': True} if match['available'] and deploy['available'] else {'available': False, 'reason': match.get('reason') or deploy.get('reason'), 'reasonCode': match.get('reasonCode')}),
            'capture': deploy, 'input': ({'available': True} if match['available'] and deploy['available'] and project['template'] in ('terminal', 'desktop') else {'available': False, 'reason': match.get('reason') or 'This module has no interactive target adapter.'}), 'profileId': match['profileId'],
            'runner': match, 'transport': {'available': bool(access and access['available']),
                'ready': bool(access and access['ready']), 'reason': access['reason'] if access else 'Assign an available virtual machine.'},
            'assignedVm': {'id': vm['id'], 'name': vm['name'],
                'imageId': image['id'], 'ready': bool(access and access['ready'])} if vm and image else None}

    async def handle(self, request, peer_pid=None):
        op = request.get('operation')
        if op in ('github_import_finish', 'github_pull_validate'):
            if set(request) != {'operation', 'projectId', 'input'} or not isinstance(request.get('input'), dict): raise DevelopmentFault('Invalid GitHub SDK validation request.', 400)
            project_id = identity(request['projectId'])
            helper = 'github_import' if op == 'github_import_finish' else 'github_pull'
            payload = {'operation': 'finish', 'id': project_id, 'input': request['input']} if helper == 'github_import' else {'operation': 'validate', 'id': project_id, 'requestId': identity(request['input'].get('requestId'))}
            if helper == 'github_pull' and set(request['input']) != {'requestId'}: raise DevelopmentFault('Unexpected pull validation fields.', 400)
            async with self.git_validation:
                self.git_validating += 1
                try:
                    process = await asyncio.create_subprocess_exec('/usr/bin/python3', '-B', str(APP / 'scripts/projects' / (helper + '.py')), self.config['projects'], self.config['r4os'],
                        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}, start_new_session=True)
                    try: output, _ = await asyncio.wait_for(process.communicate(encode(payload).encode()), 180)
                    except BaseException:
                        try: os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError: pass
                        await process.wait(); raise
                    if len(output) > 2 * 1024**2: raise DevelopmentFault('GitHub SDK response exceeded its limit.', 503)
                    value = json.loads(output)
                    if 'error' in value: raise DevelopmentFault(value['error'], value.get('code', 503))
                    return value['result']
                finally: self.git_validating -= 1
        if op in ('reset_admission', 'reset_completed'):
            if set(request) != ({'operation', 'vmId'} | ({'revision'} if op == 'reset_completed' else set())):
                raise DevelopmentFault('Invalid VM reset admission.', 400)
            from lease import maintenance_active
            from access import vm_config
            vm_id = identity(request['vmId'])
            from update_state import idle
            idle(self.config['projects'],vm_id)
            if not maintenance_active(self.config['projects'], vm_id):
                raise DevelopmentFault('An exclusive VM reset reservation is required.', 409)
            async with self.lock:
                await self.refresh()
                if self.unbound: raise DevelopmentFault('Reconcile unbound development workers before resetting a VM.', 409)
                db = connect(Path(self.config['projects']))
                try: projects = [row[0] for row in db.execute("SELECT id FROM projects WHERE state='ready'")]
                finally: db.close()
                from contextlib import closing
                from project_maintenance import database
                for project_id in projects:
                    path = Path(self.config['projects']) / project_id / 'Development/Development.sqlite'
                    if not path.exists() and not path.is_symlink(): continue
                    with closing(database(path)) as state:
                        for row in state.execute('SELECT payload FROM jobs WHERE busy=1'):
                            job = json.loads(row[0])
                            if (job.get('binding') or {}).get('id') == vm_id:
                                raise DevelopmentFault('Wait for VM development jobs to finish before resetting it.', 409)
                if op == 'reset_completed':
                    if vm_config(self.config['r4os'], vm_id)['revision'] != request['revision']:
                        raise DevelopmentFault('The reset VM revision changed.', 409)
                    state = await systemctl('show', 'r4os-studio-vm@' + vm_id + '.service', '--property=ActiveState', '--value')
                    if state not in ('inactive', 'failed'): raise DevelopmentFault('The reset VM is no longer stopped.', 409)
                    from quarantine import admission
                    admission(self.config['projects'], vm_id, 'stopped')
                return {'allowed': True}
        if op in ('access_read', 'access_save', 'access_check'):
            allowed = {'operation', 'vmId'} | ({'input'} if op == 'access_save' else set())
            if set(request) != allowed: raise DevelopmentFault('Unexpected guest access fields.', 400)
            vm_id = identity(request['vmId'])
            if op == 'access_read': return self.access.public(vm_id)
            if op == 'access_save': return self.access.configure(vm_id, request['input'])
            return await self.access.check(vm_id)
        if op in ('bind_vm_start', 'complete_vm_start'):
            from vm_start import bind
            return await bind(self, request, peer_pid)
        if op in ('bind_target', 'bind_execution'):
            if set(request) != {'operation', 'projectId', 'jobId', 'leaseId', 'token', 'helperSha256'}:
                raise DevelopmentFault('Invalid private target binding request.', 400)
            from lease import inspect
            from access import vm_config, transport_profile
            from vm_client import vm_call
            from types import SimpleNamespace
            lease = inspect(self.config['projects'], request['leaseId'], request['token'], check_boot=False)
            if lease['pid'] != peer_pid or lease['scope'].get('projectId') != request['projectId']:
                raise DevelopmentFault('The target reservation does not belong to this worker.', 403)
            store = self.store(request['projectId'])
            try:
                job = store.get(request['jobId']); vm = vm_config(self.config['r4os'], lease['vmId'])
                if job['kind'] not in ('deploy', 'execution') or job['state'] != 'running' or job['binding']['id'] != vm['id']:
                    raise DevelopmentFault('This job has no active target admission.')
                if op == 'bind_execution' and (job['kind'] != 'execution' or lease['scope'].get('jobId') != job['id']):
                    raise DevelopmentFault('This reservation has no matching execution job.', 403)
                if not re.fullmatch('[a-f0-9]{64}', request['helperSha256']): raise DevelopmentFault('Invalid helper identity.', 400)
                info = await vm_call(SimpleNamespace(id=request['leaseId'], token=request['token']), 'info')
                if op == 'bind_execution':
                    from quarantine import admission
                    admission(self.config['projects'], vm['id'], info['vm']['state'])
                    from update_epoch import require_deployment
                    require_deployment(store,store.deployment_metadata(job['deploymentId']))
                if info['vm']['state'] != 'running': raise DevelopmentFault('The target VM is not running.')
                boot = await self.boots.ensure(vm, info['invocationId']); profile = transport_profile()
                target = {'vmId': vm['id'], 'vmRevision': vm['revision'], 'imageId': vm['imageId'],
                    'imageSha256': vm['imageSha256'], 'bootId': boot['bootId'], 'profileId': profile['id'],
                    'helperSha256': request['helperSha256'], 'helperProtocol': 1}
                from update_epoch import epoch
                target['updateEpoch']=epoch(store.projects,vm['id'])
                store.update(job['id'], target=target)
                return {'target': target, 'vmInvocationId': info['invocationId'], 'exchangeInfo': {key: info.get(key) for key in ('exchange', 'exchangeWorker')}} if op == 'bind_execution' else target
            finally: store.close()
        if op == 'bind_update_target':
            if set(request) != {'operation', 'projectId', 'jobId', 'leaseId', 'token'}:
                raise DevelopmentFault('Invalid update target binding.', 400)
            from lease import inspect
            from access import vm_config
            from vm_client import vm_call
            from types import SimpleNamespace
            lease = inspect(self.config['projects'], request['leaseId'], request['token'], check_boot=False)
            if lease['pid'] != peer_pid or lease['scope'].get('projectId') != request['projectId'] or lease['scope'].get('jobId') != request['jobId']:
                raise DevelopmentFault('This update target reservation belongs to another worker.', 403)
            store = self.store(request['projectId'])
            try:
                job = store.get(request['jobId']); vm = vm_config(self.config['r4os'], lease['vmId'])
                if job['kind'] not in ('update_probe', 'update_transfer', 'update_install', 'update_commit', 'update_verify', 'update_recovery') or job['state'] != 'running' or job['binding']['id'] != vm['id']:
                    raise DevelopmentFault('This job has no active update target admission.')
                info = await vm_call(SimpleNamespace(id=request['leaseId'], token=request['token']), 'info')
                if info['vm']['state'] != 'running': raise DevelopmentFault('Start the assigned VM explicitly before checking updates.')
                boot = await self.boots.ensure(vm, info['invocationId'])
                target = {'vmId': vm['id'], 'vmRevision': vm['revision'], 'imageId': vm['imageId'], 'imageSha256': vm['imageSha256'],
                    'bootId': boot['bootId'], 'systemGeneration': vm.get('systemGeneration'), 'vmInvocationId': info['invocationId']}
                store.update(job['id'], target=target); return target
            finally: store.close()
        if op in ('update_list', 'update_job_list', 'read_update', 'update_options', 'update_plan', 'read_update_plan', 'update_batch_preview'):
            fields={'operation','projectId'} | ({'input'} if op in ('update_plan','update_batch_preview') else {'id'} if op in ('read_update','read_update_plan') else set())
            if set(request)-{'owner'}!=fields:raise DevelopmentFault('Unexpected update metadata fields.',400)
            store=self.store(identity(request['projectId']));owner=request.get('owner')
            try:
                if owner is not None:
                    from authorization import authorize
                    authorize(store,owner,op,peer_pid)
                from update_authorization import parent,filtered_options
                from update_state import read as read_state,listing
                from update_plans import options,create,read,batch
                async with self.lock:
                    if op=='update_options':return filtered_options(store,options(store),owner)
                    if op=='update_plan':return {'plan':create(store,request['input'],owner)}
                    if op=='read_update_plan':
                        parent(store,'plan',request['id'],owner)
                        return {'plan':read(store,identity(request['id']))}
                    if op=='read_update':
                        parent(store,'update',request['id'],owner)
                        return {'update':read_state(store,identity(request['id']))}
                    if op=='update_job_list':
                        rows=store.db.execute("SELECT payload FROM jobs WHERE kind IN ('package','update_probe','update_transfer','update_install','update_commit','update_verify','update_recovery') ORDER BY rowid DESC LIMIT 100").fetchall()
                        values=[json.loads(row[0]) for row in rows]
                        fields=('id','requestId','agentRunId','kind','state','phase','createdAt','completedAt','updateId','packageArtifactId','error')
                        return {'jobs':[{key:value[key] for key in fields if key in value} for value in values if owner is None or value.get('sessionId')==owner['sessionId']]}
                    if op=='update_list':
                        values=listing(store)
                        return {'updates':[value for value in values if owner is None or value.get('sessionId')==owner['sessionId']]}
                    value=request['input']
                    if not isinstance(value,dict) or set(value)!={'planIds'}:raise DevelopmentFault('Supply package plan identities.',400)
                    for ident in value['planIds']:parent(store,'plan',ident,owner)
                    return batch(store,value['planIds'])
            finally:store.close()
        if op == 'capabilities' and set(request) == {'operation'}:
            from package_support import available
            return {'enabled': not self.unbound, 'protocol': 1, 'projectDeletionLocks': 1, 'maxActiveJobs': LIMITS['activeHostJobs'],
                    'features': {'stopReceipts': 1, 'updateAgentTools': 1, 'updateRecovery': 1, 'updateVerification': 1, 'updateInstallation': 1, 'updateInbox': 1, 'updatePreflight': 1, 'packageJobs': int(available()), 'updatePlans': 1, 'agentTools': 2, 'reconciliation': 1, 'leaseQueue': 1, 'vmReset': 1, 'vmStart': 1, 'jobWait': 1, 'checkCompletion': 1},
                    'version': json.loads((APP / 'shared/version.json').read_text())['version']}
        allowed = {'operation', 'projectId', 'owner'}
        if op in ('read_job', 'wait_update', 'wait_vm_start', 'wait_build', 'wait_deploy', 'wait_execution', 'stop_job', 'artifact', 'package_artifact', 'deployment', 'capture', 'input', 'complete_check', 'evidence', 'evidence_history', 'assess', 'cancel_owned', 'reconcile'): allowed.add('id')
        if op == 'evidence_history': allowed.add('before')
        if op == 'read_job': allowed.update(('offset', 'metadataOnly'))
        if op in ('build', 'package', 'update_probe', 'update_transfer', 'update_install', 'update_commit', 'update_verify', 'update_recovery', 'deploy', 'execution', 'vm_start'): allowed.update(('input', 'owner'))
        if op in ('save_settings', 'capture', 'input', 'complete_check', 'assess', 'reconcile'): allowed.add('input')
        if op == 'evidence': allowed.update(('evidenceId', 'presentationSessionId'))
        if set(request) - allowed or op not in ('options', 'settings', 'jobs', 'read_job', 'wait_update', 'wait_vm_start', 'wait_build', 'wait_deploy', 'wait_execution', 'stop_job', 'artifact', 'package_artifact', 'deployment', 'build', 'package', 'update_probe', 'update_transfer', 'update_install', 'update_commit', 'update_verify', 'update_recovery', 'deploy', 'execution', 'vm_start', 'save_settings', 'capture', 'input', 'complete_check', 'evidence', 'evidence_history', 'assess', 'cancel_owned', 'reconcile'):
            raise DevelopmentFault('Unsupported development coordinator operation.', 400)
        store = self.store(identity(request['projectId']))
        try:
            owner = request.get('owner'); authorization = None
            if op == 'vm_start' and owner is None: raise DevelopmentFault('VM start requires an active agent owner.', 403)
            if owner is not None:
                from authorization import authorize
                bound = None
                if op == 'artifact': bound = store.get(store.artifact_metadata(request['id'])['buildId'])
                elif op == 'deployment': bound = store.get(store.deployment_metadata(request['id'])['jobId'])
                elif op in ('read_job', 'wait_update', 'wait_vm_start', 'wait_build', 'wait_deploy', 'wait_execution', 'stop_job', 'capture', 'input', 'complete_check', 'evidence', 'evidence_history', 'assess'): bound = store.get(request['id'])
                authorization = authorize(store, owner, op, peer_pid, bound, stopping=op == 'cancel_owned', recovery_action=request.get('input',{}).get('action') if op=='update_recovery' else None)
                if op in ('deploy', 'execution'):
                    artifact = store.artifact_metadata(request['input']['artifactId']) if op == 'deploy' else store.deployment_metadata(request['input']['deploymentId'])
                    parent = store.get(artifact['buildId'] if op == 'deploy' else artifact['jobId'])
                    if parent.get('sessionId') != owner['sessionId']: raise DevelopmentFault('This input belongs to another session.', 403)
            if op == 'cancel_owned':
                if owner is None: raise DevelopmentFault('An active agent owner is required.', 403)
                stopped = []
                for row in store.db.execute('SELECT payload FROM jobs WHERE busy=1').fetchall():
                    job = json.loads(row[0])
                    if job.get('agentRunId') == owner['agentRunId'] and job.get('sessionId') == owner['sessionId']:
                        store.update(job['id'], 'stopping', phase='stopping')
                        await systemctl('stop', '--no-block', job_unit(job['id'], job['kind'])); stopped.append(job['id'])
                return {'stopping': stopped}
            if op == 'options': return self.options(store)
            if op == 'package_artifact':
                from update_authorization import parent
                parent(store,'package',request['id'],owner)
                from package_jobs import artifact
                return {'artifact': artifact(store, request['id'])}
            if op=='wait_update':
                from authorization import authorize
                from update_authorization import PERMISSIONS
                job=store.get(request['id'])
                if owner is None or job['kind'] not in PERMISSIONS or job.get('agentRunId')!=owner['agentRunId']:
                    raise DevelopmentFault('Wait only for the original update job in this active run.',403)
                deadline=asyncio.get_running_loop().time()+12
                while job['state'] in ACTIVE and asyncio.get_running_loop().time()<deadline:
                    authorize(store,owner,op,peer_pid,job)
                    await asyncio.sleep(.5);job=store.get(job['id'])
                authorize(store,owner,op,peer_pid,job)
                return store.page(job['id'])
            if op == 'wait_vm_start':
                from authorization import authorize
                job = store.get(request['id'])
                if owner is None or job['kind'] != 'vm_start' or job.get('agentRunId') != owner['agentRunId']:
                    raise DevelopmentFault('Wait only for this run\'s own VM start job.', 403)
                deadline = asyncio.get_running_loop().time() + 12
                while job['state'] in ACTIVE and asyncio.get_running_loop().time() < deadline:
                    authorize(store, owner, op, peer_pid, job)
                    await asyncio.sleep(.5); job = store.get(job['id'])
                authorize(store, owner, op, peer_pid, job)
                return job
            if op in ('wait_build', 'wait_deploy', 'wait_execution'):
                from authorization import authorize
                job = store.get(request['id']); expected = {'wait_build': 'build', 'wait_deploy': 'deploy', 'wait_execution': 'execution'}[op]
                if owner is None or job['kind'] != expected or job.get('agentRunId') != owner['agentRunId']:
                    raise DevelopmentFault('Wait only for this active run\'s original development job.', 403)
                deadline = asyncio.get_running_loop().time() + 12
                while job['state'] in ACTIVE and asyncio.get_running_loop().time() < deadline:
                    authorize(store, owner, op, peer_pid, job)
                    # GUI content readiness and service readiness release the
                    # pending native call. Lifecycle monitoring stays in the
                    # worker; DESKRUN terminal is never the application's exit.
                    if expected == 'execution' and job['state'] == 'running' and ((job.get('readiness') or {}).get('state') == 'ready'
                        or (job.get('readiness') or {}).get('reasonCode') == 'desktop_content_unconfirmed'):
                        break
                    await asyncio.sleep(.25); job = store.get(job['id'])
                authorize(store, owner, op, peer_pid, job)
                return {'job': job} if job['state'] in ACTIVE and expected != 'execution' else store.page(job['id'])
            if op == 'reconcile':
                from actions import admit, finish
                from recovery import reconcile
                if not isinstance(request['input'], dict) or set(request['input']) != {'requestId'}: raise DevelopmentFault('Unexpected recovery fields.', 400)
                job = store.get(request['id'])
                if await self.alive(job['id'], job['kind']): raise DevelopmentFault('This worker is still active. Reconnect to its current job instead.')
                try:
                    meta = self.metadata(self.root / job['id'] / 'worker.json')
                    if meta['projectId'] != store.id: raise ValueError()
                except Exception: raise DevelopmentFault('The original worker release binding is missing or damaged. Existing receipts were preserved.', 409) from None
                previous = admit(store, job['id'], {'operation': 'reconcile', **request['input']})
                if previous is not None: return previous
                if job['state'] != 'unknown':
                    result = {'job': store.page(job['id'])['job'], 'reconciled': False}
                else:
                    try: await reconcile(store, job, self)
                    except DevelopmentFault as error:
                        finish(store, request['input']['requestId'], {'error': str(error), 'code': error.code}); raise
                    result = {'job': store.page(job['id'])['job'], 'reconciled': True}
                return finish(store, request['input']['requestId'], result)
            if op == 'settings': return store.settings()
            if op == 'save_settings':
                from settings import update
                return update(store, request['input'])
            if op == 'jobs': return store.list()
            if op == 'read_job': return store.page(request['id'], request.get('offset', 0), metadata_only=request.get('metadataOnly', False))
            if op == 'artifact': return store.artifact(request['id'])
            if op == 'deployment': return store.deployment(request['id'])
            if op == 'assess':
                from assessment import record
                if owner is not None:
                    from evidence import read
                    image = read(store, request['id'], request['input'].get('evidenceId'))['metadata']
                    if (image.get('observer') or {}).get('agentRunId') != owner['agentRunId']:
                        raise DevelopmentFault('Capture and inspect an image in this run before assessing it.', 403)
                    if set(request['input']) != {'requestId', 'evidenceId', 'state', 'notes'}: raise DevelopmentFault('Unexpected agent assessment fields.', 400)
                    request['input']['settingsRevision'] = store.get(request['id'])['settingsRevision']
                return record(store, request['id'], request['input'], actor='agent' if owner else 'user',
                    actor_id={'agentRunId': owner['agentRunId'], 'model': authorization['model']} if owner else None)
            if op == 'evidence':
                from evidence import read
                if 'presentationSessionId' in request:
                    session_id = identity(request['presentationSessionId'])
                    if store.get(request['id']).get('sessionId') != session_id:
                        raise DevelopmentFault('This screenshot belongs to another session.', 403)
                image = read(store, request['id'], request['evidenceId'])
                if 'presentationSessionId' in request and (image['metadata']['kind'] != 'screenshot' or
                    image['metadata'].get('projectId') != store.id or image['metadata'].get('jobId') != request['id']):
                    raise DevelopmentFault('This reference is not a session screenshot.', 403)
                return image
            if op == 'evidence_history':
                from evidence import history
                return history(store, request['id'], request.get('before'))
            if op in ('capture', 'input', 'complete_check'):
                from actions import previous, admit, finish
                from evidence import read
                from observation import capture
                from job_control import call
                job = store.get(request['id']); message = {'operation': op, **request['input']}
                expected = {'operation', 'requestId'} | ({'input'} if op == 'input' else set())
                if set(message) != expected: raise DevelopmentFault('Unexpected execution action fields.', 400)
                identity(message['requestId'])
                if owner is not None: message.update(owner=owner, peerPid=peer_pid)
                recorded = previous(store, job['id'], message)
                if recorded is not None:
                    if recorded.get('error'): raise DevelopmentFault(recorded['error'], recorded.get('code', 409))
                    if op == 'input' and recorded.get('observationId'):
                        if owner is not None: authorize(store, owner, 'evidence', peer_pid, job)
                        return {**recorded, 'observation': read(store, job['id'], recorded['observationId'])}
                    return read(store, job['id'], recorded['evidenceId']) if op == 'capture' else (store.page(job['id']) if op == 'complete_check' else recorded)
                if op == 'complete_check' and job.get('checkCompletion'):
                    raise UnconfirmedGuestEffect('This check completion already has an original receipt or pending close. Inspect the saved job without another close.')
                if job['kind'] == 'execution' and job['state'] == 'running':
                    result = await call(job['id'], message)
                elif op == 'capture' and job['state'] in ('completed', 'failed', 'interrupted', 'unknown'):
                    admit(store, job['id'], message); result = await capture(store, job, observer={**owner, 'model': authorization['model']} if owner else None,
                        origin={'requestId':message['requestId'],'operation':'capture'} if owner else None)
                    finish(store, message['requestId'], {'evidenceId': result['metadata']['id']})
                else: raise DevelopmentFault('This job has no active guest input target.')
                if result.get('error'): raise DevelopmentFault(result['error'], result.get('code', 409))
                if op == 'complete_check': return store.page(job['id'])
                if op == 'capture' and owner is not None:
                    # Replace the authorization formerly performed by a second
                    # evidence fetch after capture. Older agents ignore the hint.
                    authorize(store, owner, op, peer_pid, job)
                    result = {**result, 'authorizedForAgentOutput': True}
                if op == 'input' and result.get('observationId'):
                    if owner is not None: authorize(store, owner, 'evidence', peer_pid, job)
                    result = {**result, 'observation': read(store, job['id'], result['observationId'])}
                return result
            async with self.lock:
                await self.refresh()
                if self.unbound: raise DevelopmentFault('A development worker has no confirmed binding. Restore host support.', 503)
                if op == 'stop_job':
                    job_id = identity(request['id']); job = store.get(job_id)
                    if owner is not None: authorize(store, owner, op, peer_pid, job)
                    requested = job['state'] in ACTIVE or await self.alive(job_id, job['kind'])
                    if requested:
                        store.update(job_id, 'stopping', phase='stopping')
                        try: await systemctl('stop', job_unit(job_id, job['kind']))
                        except (DevelopmentFault, asyncio.TimeoutError, OSError) as error:
                            raise UnconfirmedGuestEffect('The Stop command has no confirmed worker receipt. Inspect the original job; it was not repeated.') from error
                        if store.get(job_id)['state'] in ACTIVE:
                            local = job['kind'] in ('build', 'package')
                            store.update(job_id, 'interrupted' if local else 'unknown', phase='stopped' if local else 'recovery',
                                error='Job stopped.' if local else 'The worker ended without a confirmed effect or cleanup receipt.')
                    active = await self.alive(job_id, job['kind'])
                    if not active: self.active.pop(job_id, None)
                    from stopping import receipt
                    job = store.get(job_id)
                    return {**job, 'stopReceipt': receipt(store, job, requested, active)}
                previous = store.db.execute('SELECT id FROM jobs WHERE request_id=?', (request['input'].get('requestId'),)).fetchone()
                if owner is not None: authorize(store, owner, op, peer_pid, recovery_action=request.get('input',{}).get('action') if op=='update_recovery' else None)
                if not previous:
                    if op in ('update_probe', 'update_transfer', 'update_install', 'update_commit', 'update_verify', 'update_recovery'):
                        target = Path(self.config.get('workerReleaseRoot', '/opt/r4os-studio/current')).resolve(strict=True)
                        if not all((target / ('scripts/project-development/' + name + '.py')).is_file() for name in (('update_probe', 'update_transfer', 'inbox_sftp', 'update_install', 'update_state', 'update_jobs', 'update_verify', 'installed_sftp', 'update_epoch', 'update_recovery') if op != 'update_probe' else ('update_probe',))):
                            raise DevelopmentFault('A compatible update preflight worker must be adopted first.', 503)
                    if op == 'package':
                        from package_support import available
                        release = Path(self.config.get('workerReleaseRoot', '/opt/r4os-studio/current')).resolve(strict=True)
                        if not available() or not (release / 'scripts/project-development/packager.py').is_file():
                            raise DevelopmentFault('Package worker host maintenance or compatible worker adoption is required.', 503)
                    if len(self.active) >= LIMITS['activeHostJobs']: raise DevelopmentFault('The host is already running its maximum number of development jobs.')
                    if op == 'build' and not owner and store.agent_busy(): raise DevelopmentFault('The workspace is owned by an active agent. Request a build through that agent or wait for it to finish.')
                binding = None
                if op in ('deploy', 'execution', 'vm_start', 'update_probe', 'update_transfer', 'update_install', 'update_commit', 'update_verify', 'update_recovery') and not previous:
                    from access import vm_config
                    if not store.project['vmId']: raise DevelopmentFault('Assign a VM in Project settings first.')
                    from lease import maintenance_active
                    if maintenance_active(self.config['projects'], store.project['vmId']):
                        raise DevelopmentFault('This VM is being reset. Wait for maintenance to finish.', 409)
                    binding = vm_config(self.config['r4os'], store.project['vmId'])
                    if op == 'execution':
                        from profiles import require_profile
                        require_profile(store.project, {'id': binding['imageId'], 'sha256': binding['imageSha256']})
                        deployed = store.deployment_metadata(request['input'].get('deploymentId'))
                        if deployed.get('helperCapabilities', {}).get('controlVersion') != 2 or deployed.get('helperCapabilities', {}).get('watchdogVersion') != 1:
                            raise DevelopmentFault('This deployment has an older guest helper. Deploy the artifact again before running.')
                    if op in ('deploy', 'execution', 'vm_start', 'update_transfer', 'update_install'):
                        from update_state import idle
                        idle(store.projects, binding['id'])
                    for active_id, meta in self.active.items():
                        if meta['kind'] in ('build','package'):continue
                        peer=self.store(meta['projectId'])
                        try: peer_job=peer.get(active_id)
                        finally: peer.close()
                        same=(peer_job.get('binding') or {}).get('id')==binding['id']
                        if same and peer_job['state'] in ACTIVE and (op in ('update_install','update_commit','update_recovery') or meta['kind'] in ('update_install','update_commit','update_recovery')):
                            raise DevelopmentFault('Wait for the existing VM job to finish before another update/VM mutation.')
                    status = self.access.public(binding['id'])
                    if not status['available']: raise DevelopmentFault(status['reason'])
                job, fresh = store.admit(op, request['input'], owner, binding)
                if not fresh: return job
                try:
                    release = Path(self.config.get('workerReleaseRoot', '/opt/r4os-studio/current')).resolve(strict=True)
                    if not release.is_relative_to('/opt/r4os-studio/releases'): raise DevelopmentFault('Invalid development release.', 503)
                    protocol(release); info = json.loads((release / 'release.json').read_text())
                    meta = {'schema': 1, 'jobId': job['id'], 'projectId': store.id, 'kind': op,
                        'projects': self.config['projects'], 'r4os': self.config['r4os'],
                        'releaseRoot': str(release), 'release': info['id'], 'version': info['version']}
                    save(folder(self.root / job['id']) / 'worker.json', meta)
                    self.active[job['id']] = meta
                    await systemctl('start', '--no-block', job_unit(job['id'], op))
                except BaseException:
                    try: alive = await self.alive(job['id'], op)
                    except Exception: alive = True
                    if not alive:
                        store.update(job['id'], 'failed', phase='failed', error='The development worker could not start.')
                        self.active.pop(job['id'], None)
                    raise
                return job
        finally: store.close()

    async def connection(self, reader, writer):
        task = asyncio.current_task(); self.connections.add(task)
        try:
            sock = writer.get_extra_info('socket')
            peer_pid, uid, _ = struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid not in (0, self.config['uid']): raise DevelopmentFault('Development coordinator access denied.', 403)
            raw = await asyncio.wait_for(reader.readline(), 10)
            if len(raw) > 131072: raise DevelopmentFault('Development request too large.', 400)
            result = await self.handle(json.loads(raw), peer_pid); writer.write((encode({'result': result}) + '\n').encode())
        except (DevelopmentFault, ProjectFault) as error:
            writer.write((encode({'error': str(error), 'code': error.code, 'reasonCode': getattr(error, 'reason_code', None), 'uncertain': bool(getattr(error, 'uncertain', False))}) + '\n').encode())
        except Exception:
            writer.write(b'{"error":"The development coordinator is unavailable.","code":503}\n')
        finally:
            try: await writer.drain()
            except Exception: pass
            writer.close()
            try: await writer.wait_closed()
            except Exception: pass
            self.connections.discard(task)


async def main():
    os.umask(0o077); protocol(APP)
    config = json.loads(Path('/etc/r4os-studio-development/config.json').read_text())
    if os.getuid() != config['uid']: raise SystemExit('Run the coordinator as its configured service user.')
    host = Host(config); await host.recover(); path = folder('/run/r4os-studio-development') / 'host.sock'
    if path.exists(): path.unlink()
    server = await asyncio.start_unix_server(host.connection, path=str(path), limit=131073); path.chmod(0o600)
    stopped = asyncio.Event(); loop = asyncio.get_running_loop(); replacement = None
    for sig in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(sig, stopped.set)
    async def maintain():
        nonlocal replacement
        while not stopped.is_set():
            try:
                async with host.lock:
                    await host.refresh(); release = Path('/opt/r4os-studio/current').resolve(strict=True)
                    if not host.active and not host.unbound and not host.git_validating and release != APP:
                        protocol(release); script = release / 'scripts/project-development/host.py'
                        if not release.is_relative_to('/opt/r4os-studio/releases') or script.stat().st_uid != 0 or script.stat().st_mode & 0o022: raise ValueError()
                        replacement = script; stopped.set()
            except Exception: pass
            try: await asyncio.wait_for(stopped.wait(), 2)
            except asyncio.TimeoutError: pass
    monitor = asyncio.create_task(maintain())
    async with server: await stopped.wait()
    monitor.cancel(); await asyncio.gather(monitor, return_exceptions=True)
    if host.connections:
        try: await asyncio.wait_for(asyncio.gather(*host.connections, return_exceptions=True), 25)
        except asyncio.TimeoutError: pass
    await host.boots.close()
    if replacement: os.execv('/usr/bin/python3', ['/usr/bin/python3', '-B', str(replacement)])


if __name__ == '__main__': asyncio.run(main())
