"""Fixed native status/metadata observation under the existing project/VM lease."""
import json
import re
from pathlib import Path
import stat
import uuid
from contracts import DevelopmentFault, encode, hash_value, identity, digest
from jobs import folder, now
from layout import save
from package_jobs import artifact
from sysupd_text import parse, release_file, inventory, ownership

COMMANDS = [('ver', 'VER'), ('status', 'SYSUPD STATUS'),
    ('version', r'TYPE C:\R4OS\CONFIG\VERSION.R4S'), ('inventory', r'TYPE C:\R4OS\CONFIG\MODULES.JSON')]


def admit(store, request, owner, binding, kind="update_probe"):
    if kind not in ("update_probe", "update_transfer"): raise DevelopmentFault("Unsupported update job.", 400)
    if not isinstance(request, dict) or set(request) != {'requestId', 'projectRevision', 'packageArtifactId'}:
        raise DevelopmentFault('Unexpected update preflight fields.', 400)
    key = identity(request['requestId']); identity(request['packageArtifactId'])
    owner = owner or {'sessionId': None, 'agentRunId': None}
    fingerprint = hash_value({'kind': kind, 'request': request, 'owner': owner})
    previous = store.db.execute('SELECT id,request_hash FROM jobs WHERE request_id=?', (key,)).fetchone()
    if previous:
        if previous['request_hash'] != fingerprint: raise DevelopmentFault('This request ID belongs to another update preflight.')
        return store.get(previous['id']), False
    if type(request['projectRevision']) is not int or request['projectRevision'] != store.project['revision']:
        raise DevelopmentFault('Project settings changed. Reload before checking the VM.')
    if not binding or binding['id'] != store.project['vmId']:
        raise DevelopmentFault('Assign a VM explicitly before checking update support.')
    package = artifact(store, request['packageArtifactId'])
    if package['projectId'] != store.id or package['plan']['pins'] != store.project['pins']: raise DevelopmentFault('The package belongs to different project pins.')
    store.db.execute('BEGIN IMMEDIATE')
    try:
        if store.db.execute('SELECT id FROM jobs WHERE busy=1').fetchone(): raise DevelopmentFault('This project already has an active development job.')
        job = {'id': str(uuid.uuid4()), 'projectId': store.id, 'kind': kind, 'state': 'queued', 'revision': 1,
            **owner, 'artifactId': None, 'deploymentId': None, 'packageArtifactId': package['id'], 'updatePackage': package,
            'target': None, 'process': None, 'exitCode': None, 'error': None, 'phase': 'queued', 'check': None,
            'createdAt': now(), 'completedAt': None, 'source': None, 'projectRevision': store.project['revision'],
            'settingsRevision': store.settings()['revision'], 'pins': store.project['pins'], 'settings': store.settings(), 'binding': binding}
        store.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,1,1,?)', (job['id'], key, fingerprint, kind, 'queued', encode(job)))
        store.db.commit(); return job, True
    except BaseException: store.db.rollback(); raise


def owned_record(store, vm, package):
    path = store.projects / '.studio/development/UpdateOwners' / (vm['id'] + '.json')
    if not path.exists() and not path.is_symlink(): return None
    info = path.lstat()
    if path.resolve(strict=True) != path or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536:
        raise DevelopmentFault('The durable VM update ownership record is unavailable. Existing data was preserved.')
    value = json.loads(path.read_text())
    if (value.get('schema') != 1 or value.get('vmId') != vm['id'] or value.get('systemGeneration') != vm.get('systemGeneration')):
        raise DevelopmentFault('The durable VM update record belongs to a different system generation.')
    if value.get('projectId') != store.id or package['id'] not in value.get('packageArtifactIds', []): return None
    return value


class Probe:
    def __init__(self, store, job):
        self.store, self.job = store, job
        self.work = folder(store.root / 'UpdateProbeWork' / job['id'])
        self.value = {'adapterSha256': digest(Path(__file__).resolve().parents[2] / 'shared/r4os/sysupd-adapter.json'), 'schema': 1, 'state': 'capturing', 'mayUpload': False, 'captures': {}, 'statusCreatesDirectories': True}
        self.log = store.evidence(job['id']) / 'output.log'

    def persist(self):
        save(self.work / 'observation.json', self.value)
        self.store.update(self.job['id'], updateProbe=self.value)

    async def run(self, after_ready=None):
        from access import Access, SshTransport, transport_profile, guest_version
        from vm_worker import guard, broker_call
        from vm_client import vm_call
        from queue_lease import reserve
        from sftp import download_update_metadata
        store, job, vm = self.store, self.job, self.job['binding']
        transport_profile()
        scope = {'kind': 'job', 'projectId': store.id, 'projectRevision': job['projectRevision'],
            'vmRevision': vm['revision'], 'imageId': vm['imageId'], 'imageSha256': vm['imageSha256'], 'jobId': job['id']}
        async with reserve(store, job, scope) as lease:
            guard(store, job)
            info = await vm_call(lease, 'info')
            if info['vm']['state'] != 'running':
                raise DevelopmentFault('Start the assigned VM explicitly before checking updates. Preflight cannot start it.', reason_code='vm_start_required')
            target = await broker_call({'operation': 'bind_update_target', 'projectId': store.id, 'jobId': job['id'], 'leaseId': lease.id, 'token': lease.token})
            scope['bootId'] = target['bootId']; save(lease.root / 'leases' / (lease.id + '.json'), lease.value)
            self.value['target'] = target; self.persist()
            access = Access(store.projects, store.r4os, None)
            if not vm.get('networkEnabled') or not access.record(vm['id'])['enabled']:
                raise DevelopmentFault('Enable Network and development access for the selected VM.')
            async with SshTransport(access, vm, lease) as ssh:
                for name, command in COMMANDS:
                    guard(store, job, lease)
                    store.update(job['id'], phase='sysupd_' + name)
                    captured = await ssh.exec(command, complete=True, limit=131072)
                    self.value['captures'][name] = {key: value for key, value in captured.items() if key != 'output'}
                    self.persist()
                    if sum(len((value['stdout'] + value['stderr']).encode()) for value in self.value['captures'].values()) > 262144:
                        raise DevelopmentFault('The combined native update observation exceeds256 KiB.')
                    if captured.get('truncated') or captured.get('timedOut') or captured.get('transportUncertain'):
                        raise DevelopmentFault('The native update observation is incomplete; inspect the preserved channels.')
                    if name == 'ver':
                        self.value['version'] = guest_version(captured)
                    elif name == 'status':
                        parsed = parse('STATUS', captured)
                        if parsed['kind'] != 'status' or not parsed['success']: raise DevelopmentFault('The guest did not confirm SYSUPD STATUS.')
                        self.value['status'] = parsed
                    elif name == 'version':
                        if captured['exitCode'] != 0: raise DevelopmentFault('The guest VERSION.R4S could not be read.')
                        self.value['installedRelease'] = release_file(captured['stdout'])
                console = self.value['captures']['inventory']
                loss = bool(console['exitCode'] == 3 and re.search(r'SSHD: console output lost [1-9][0-9]* bytes; command output incomplete\.', (console['stdout']+'\n'+console['stderr'])))
                if console['exitCode'] != 0 and not loss:
                    raise DevelopmentFault('The guest inventory command failed; no later update effect was authorized.')
                # Two fixed read-only SFTP reads also bind bytes when TYPE's console hook loses output.
                reads = []
                for name in ('inventory-first.json', 'inventory-second.json'):
                    guard(store, job, lease)
                    reads.append(await download_update_metadata(ssh, 'inventory', self.work / name))
                if reads[0]['sha256'] != reads[1]['sha256'] or reads[0]['bytes'] != reads[1]['bytes']:
                    raise DevelopmentFault('The observed inventory changed between complete reads.')
                raw = (self.work / 'inventory-first.json').read_text(encoding='utf8')
                self.value['inventory'] = inventory(raw)
                self.value['inventoryRead'] = {'method': 'fixed-sftp-after-console-loss' if loss else 'fixed-sftp-confirmation', 'reads': reads, 'consoleIncomplete': loss}
                if not loss and inventory(console['stdout']) != self.value['inventory']:
                    raise DevelopmentFault('Console and full inventory reads disagree.')
                guard(store, job, lease)
                # Close the observation interval with a fresh status snapshot; no native writer lock is claimed.
                end = await ssh.exec('SYSUPD STATUS', complete=True, limit=131072)
                self.value['captures']['statusAfter'] = {key: value for key, value in end.items() if key != 'output'}
                self.persist()
                if sum(len((value['stdout'] + value['stderr']).encode()) for value in self.value['captures'].values()) > 262144:
                    raise DevelopmentFault('The combined native update observation exceeds256 KiB.')
                after = parse('STATUS', end)
                if after['status'] != self.value['status']['status']: raise DevelopmentFault('Native update state changed during preflight.')
                ssh.publish_host_key()
                record = access.record(vm['id'])
                self.value['hostKeyFingerprint'] = record.get('hostKeyFingerprint')
                record.pop('lastError', None)
                record['readiness'] = {'checkedAt': now(), 'vmRevision': vm['revision'], 'bootId': target['bootId'], **self.value['version']}
                access.save_record(vm['id'], record)
            guard(store, job, lease)
            own = owned_record(store, vm, job['updatePackage'])
            self.value['ownership'] = ownership(self.value['status'], own)
            self.value.update(state='ready' if self.value['ownership']['mayUpload'] else 'blocked',
                mayUpload=self.value['ownership']['mayUpload'], checkedAt=now(), nativeVerificationRequired=True,
                requestedTargetRelease=job['updatePackage']['plan']['metadata']['targetRelease'],
                baseImageId=vm['imageId'], baseImageSha256=vm['imageSha256'], activeKernel=self.value['version']['kernel'])
            self.persist()
            with self.log.open('ab') as stream:
                stream.write(('SYSUPD preflight: ' + self.value['state'] + '\n' + self.value['status']['rawLine'] +
                    '\nInventory: ' + str(self.value['inventory']['count']) + ' components; full SFTP SHA-256 ' + reads[0]['sha256'] +
                    ('\nTYPE console was incomplete; complete fixed-path SFTP evidence retained.' if loss else '') + '\n').encode())
            if after_ready is not None:
                if not self.value['mayUpload']:
                    raise DevelopmentFault('Active or recoverable native update state blocks a new Inbox transfer.')
                return await after_ready(lease, target, self.value)
            return store.update(job['id'], 'completed', phase='sysupd_ready' if self.value['mayUpload'] else 'sysupd_blocked', exitCode=0)
