"""One original free guest command, on the assigned VM, without effect replay."""
import asyncio
import os
from pathlib import Path

from contracts import DevelopmentFault, UnconfirmedGuestEffect, LIMITS, digest
from jobs import folder, now
from layout import save

COMMAND_BYTES = 112  # SSHD's 127-byte Terminal args minus /NOAUTOEXEC /C .
CHANNEL_BYTES = LIMITS['outputBytes'] // 2


def command(value):
    try:
        valid = (isinstance(value, str) and bool(value.strip()) and len(value.encode('utf-8')) <= COMMAND_BYTES
            and not any(ord(c) < 32 or ord(c) == 127 for c in value))
    except UnicodeError:
        valid = False
    if not valid:
        raise DevelopmentFault('Use one nonempty R4OS command, at most 112 UTF-8 bytes, without control characters. Nothing was submitted or shortened.', 400,
            reason_code='ssh_command_invalid')
    return value


def supported():
    """Long commands require the dedicated worker without a total time limit."""
    import re
    unit = Path('/etc/systemd/system/r4os-studio-development-ssh@.service')
    try:
        text = unit.read_text()
        return (not False and re.findall('^RuntimeMaxSec=(.*)$', text, re.M) == ['infinity'])
    except OSError:
        return False


class SshCommand:
    def __init__(self, store, job):
        self.store, self.job = store, job
        self.work = folder(store.root / 'SshWork' / job['id'])
        self.evidence = store.evidence(job['id'])
        self.process = None
        self.intent = None
        self.claimed = False
        self.stats = {key: {'bytesReceived': 0, 'bytesCaptured': 0, 'truncated': False}
            for key in ('stdout', 'stderr')}
        self.scan_tail = {key: b'' for key in self.stats}
        self.value = {'version': 1, 'command': job['sshCommand'], 'commandBytes': len(job['sshCommand'].encode()),
            'commandLimitBytes': COMMAND_BYTES, 'channelLimitBytes': CHANNEL_BYTES,
            'sshExitCode': None, 'commandExitCode': None, 'commandReturnConfirmed': False,
            'sshClientEndConfirmed': False, 'guestProcessEndConfirmed': False,
            'guestDescendantsEndConfirmed': False, 'outputComplete': False,
            'outputCompletenessScope': 'received-ssh-streams', 'nativeOutputComplete': None,
            'nativeOutputLossReported': False, 'channels': self.stats}

    def persist(self, **fields):
        self.value.update(fields)
        self.store.observe(self.job['id'], ssh=dict(self.value), captureTruncated=any(v['truncated'] for v in self.stats.values()))

    async def run(self):
        from access import Access, SshTransport, guest_version
        from vm_worker import guard, broker_call
        from vm_client import vm_call
        from queue_lease import reserve
        from quarantine import admission, claim, release
        store, job, vm = self.store, self.job, self.job['binding']
        command(job['sshCommand'])
        scope = {'kind': 'job', 'projectId': store.id, 'projectRevision': job['projectRevision'],
            'vmRevision': vm['revision'], 'imageId': vm['imageId'], 'imageSha256': vm['imageSha256'], 'jobId': job['id']}
        try:
            async with reserve(store, job, scope) as lease:
                info = await vm_call(lease, 'info'); guard(store, job)
                admission(store.projects, vm['id'], info['vm']['state'])
                if info['vm']['state'] != 'running':
                    raise DevelopmentFault('Start the assigned VM explicitly before using SSH. No command was submitted.', reason_code='vm_start_required')
                access = Access(store.projects, store.r4os, None)
                if not vm.get('networkEnabled') or not access.record(vm['id'])['enabled']:
                    raise DevelopmentFault('Enable Network and development access for the assigned VM. No command was submitted.', reason_code='development_access_unavailable')
                target = await broker_call({'operation': 'bind_ssh_target', 'projectId': store.id, 'jobId': job['id'],
                    'leaseId': lease.id, 'token': lease.token})
                scope['bootId'] = target['bootId']; save(lease.root / 'leases' / (lease.id + '.json'), lease.value)
                store.update(job['id'], phase='authenticating')
                async with SshTransport(access, vm, lease) as ssh:
                    # Read-only readiness/authentication before the command intent.
                    # These positively pre-command failures never quarantine the VM.
                    version = guest_version(await ssh.exec('VER'))
                    ssh.publish_host_key(); guard(store, job, lease)
                    self.value.update(target=target, guestRelease=version['release'], guestKernel=version['kernel'])
                    self.intent = {'schema': 1, 'jobId': job['id'], 'requestId': job['requestId'],
                        'projectId': store.id, 'sessionId': job['sessionId'], 'agentRunId': job['agentRunId'],
                        'command': job['sshCommand'], 'target': target, 'createdAt': now()}
                    save(self.work / 'intent.json', self.intent)
                    claim(store.projects, vm['id'], {'jobId': job['id'], 'projectId': store.id, 'target': target,
                        'reason': 'Original free SSH command; no terminal receipt yet.'})
                    self.claimed = True
                    try:
                        self.process = await asyncio.create_subprocess_exec(*ssh.argv(), '-T', '-n',
                            ssh.record['username'] + '@127.0.0.1', job['sshCommand'],
                            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                            env=ssh.environment(), start_new_session=True)
                    except OSError:
                        release(store.projects, vm['id'], job['id']); self.claimed = False
                        save(self.work / 'not-started.json', {**self.intent, 'reason': 'Local SSH spawn failed; no SSH client created.'})
                        raise DevelopmentFault('The local SSH client could not start. No guest command was submitted.', 503) from None
                    ssh.processes.add(self.process)
                    self.value.update(startedAt=now(), sshClientPid=self.process.pid)
                    save(self.work / 'started.json', {**self.intent, 'sshClientPid': self.process.pid})
                    store.update(job['id'], phase='ssh_running'); self.persist()
                    reads = [asyncio.create_task(self.drain(getattr(self.process, key), key)) for key in self.stats]
                    try:
                        # Output quotas bound capture, never command lifetime. Continue
                        # draining both streams even after capture is full.
                        while self.process.returncode is None or not all(t.done() for t in reads):
                            pending = [t for t in reads if not t.done()]
                            if pending: await asyncio.wait(pending, timeout=.5)
                            else: await asyncio.sleep(.5)
                            for read_task in reads:
                                if read_task.done(): read_task.result()
                            guard(store, job, lease)
                            self.persist()
                        await asyncio.gather(*reads)
                        code = await self.process.wait()
                        self.value.update(sshExitCode=code, sshClientEndConfirmed=True, endedAt=now(),
                            commandReturnConfirmed=code >= 0 and code != 255,
                            commandExitCode=code if code >= 0 and code != 255 else None,
                            outputComplete=not any(v['truncated'] for v in self.stats.values()) and not self.value['nativeOutputLossReported'])
                        self.value['guestProcessEndConfirmed'] = self.value['commandReturnConfirmed']
                        # SSH returns the command-shell status. It attests neither
                        # detached child completion nor successful app behavior.
                        save(self.work / 'result.json', {**self.intent, 'ssh': self.value,
                            'output': {key: {'sha256': digest(self.evidence / (key + '.log')),
                                'bytes': self.stats[key]['bytesCaptured']} for key in self.stats}})
                        self.persist()
                        if not self.value['commandReturnConfirmed']:
                            raise UnconfirmedGuestEffect('The SSH client ended without a confirmed guest command return. Inspect this original job; no command was repeated.')
                        release(store.projects, vm['id'], job['id']); self.claimed = False
                        return store.update(job['id'], 'completed' if code == 0 else 'failed',
                            phase='ssh_completed', exitCode=code, ssh=self.value,
                            error=None if code == 0 else 'The guest command returned a nonzero exit status.')
                    finally:
                        if self.process.returncode is None: self.process.kill()
                        await self.process.wait()
                        await asyncio.gather(*reads, return_exceptions=True)
                        ssh.processes.discard(self.process)
                        self.persist(sshClientEndConfirmed=True, sshExitCode=self.process.returncode)
        except BaseException as error:
            if self.claimed:
                self.persist(sshClientEndConfirmed=bool(self.process and self.process.returncode is not None),
                    sshExitCode=self.process.returncode if self.process else None)
                if isinstance(error, UnconfirmedGuestEffect): raise
                raise UnconfirmedGuestEffect('SSH observation stopped without a confirmed guest return. Stopping the local client does not confirm guest process end. Read this original job; do not replay the command.') from error
            raise

    async def drain(self, stream, channel):
        stats = self.stats[channel]
        with (self.evidence / (channel + '.log')).open('xb') as original:
            while data := await stream.read(8192):
                stats['bytesReceived'] += len(data)
                observed = self.scan_tail[channel] + data
                if b'SSHD: console output lost ' in observed:
                    self.value.update(nativeOutputLossReported=True, nativeOutputComplete=False)
                self.scan_tail[channel] = observed[-256:]
                captured = data[:max(0, CHANNEL_BYTES - stats['bytesCaptured'])]
                original.write(captured); original.flush()
                stats['bytesCaptured'] += len(captured)
                stats['truncated'] = stats['bytesReceived'] > stats['bytesCaptured']
                log = self.evidence / 'output.log'
                room = max(0, LIMITS['outputBytes'] - (log.stat().st_size if log.exists() else 0))
                if captured and room:
                    with log.open('ab') as combined: combined.write((('[' + channel + ']\n').encode() + captured)[:room])
            original.flush(); os.fsync(original.fileno())


def local(store, job):
    """Reconcile the original private result only; never reconnect or execute."""
    from recovery import read, receipt
    from quarantine import resolve
    work = store.root / 'SshWork' / job['id']
    path = work / 'result.json'
    if not path.exists(): return None
    intent, saved = read(work / 'intent.json'), read(path)
    expected = {key: job[key] for key in ('projectId', 'sessionId', 'agentRunId', 'requestId')}
    expected.update(schema=1, jobId=job['id'], command=job['sshCommand'], target=job['target'])
    if any(intent.get(k) != v or saved.get(k) != v for k, v in expected.items()):
        raise DevelopmentFault('The original SSH result differs from its command/owner/target.')
    value = saved['ssh']; code = value.get('sshExitCode')
    if (type(code) is not int or code < 0 or code == 255 or value.get('commandReturnConfirmed') is not True
            or value.get('sshClientEndConfirmed') is not True or value.get('commandExitCode') != code): return None
    for channel in ('stdout', 'stderr'):
        path = store.evidence(job['id']) / (channel + '.log'); proof = saved['output'][channel]
        if path.stat().st_size != proof['bytes'] or digest(path) != proof['sha256']:
            raise DevelopmentFault('The original SSH output receipt differs from its saved bytes.')
    result = store.recovered(job['id'], 'completed' if code == 0 else 'failed',
        receipt('original-ssh-result', guestEndConfirmed=True), ssh=value, exitCode=code,
        error=None if code == 0 else 'The guest command returned a nonzero exit status.')
    resolve(store.projects, job['binding']['id'], job['id'], 'original-ssh-result')
    return result


async def reconcile(store, job):
    from access import vm_config
    from lease import VmLease
    from vm_client import vm_call
    from quarantine import resolve
    from recovery import receipt
    result = local(store, job)
    if result: return result
    vm = vm_config(store.r4os, job['binding']['id'])
    scope = {'kind': 'recovery', 'vmRevision': vm['revision'], 'imageId': vm['imageId'], 'imageSha256': vm['imageSha256']}
    with VmLease(store.projects, vm['id'], scope) as lease:
        from forwards import cleanup
        await cleanup(lease)
        info = await vm_call(lease, 'info')
        target = job.get('target') or {}
        replaced = bool(target.get('vmInvocationId') and info['invocationId'] and target['vmInvocationId'] != info['invocationId'])
        ended = info['vm']['state'] == 'stopped' or replaced
        if ended: resolve(store.projects, vm['id'], job['id'], 'VM stopped or replaced after original SSH command')
        return store.recovered(job['id'], 'interrupted' if ended else 'unknown',
            receipt('ssh-vm-ended' if ended else 'unconfirmed-ssh', guestEndConfirmed=ended,
                reason='VM end confirmed; original command exit status unavailable.' if ended else
                    'No original guest return receipt. SSH client end alone cannot confirm guest end. Nothing was replayed.'),
            exitCode=None, error='Original SSH command result unavailable.')
