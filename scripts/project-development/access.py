"""Fixed R4OS guest login, private SSH trust and authenticated readiness checks."""
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket

from contracts import APP, DevelopmentFault, SshNotReady, digest, identity
from jobs import folder, now
from layout import save
from profiles import runner
from lease import VmLease
from vm_client import vm_call

DEFAULT_USERNAME = 'r4os'
DEFAULT_PASSWORD = 'rosebud'
CREDENTIAL_POLICY = 'r4os-default-v1'


def vm_config(r4os, vm_id):
    path = Path(r4os) / 'Instances' / identity(vm_id) / 'vm.json'
    try:
        if path.resolve(strict=True) != path: raise ValueError()
        value = json.loads(path.read_text())
        if value['id'] != vm_id: raise ValueError()
        value.setdefault('revision', value['imageSha256'])
        return value
    except (OSError, ValueError, KeyError): raise DevelopmentFault('The selected VM metadata is unavailable.', 404) from None


def transport_profile():
    result = runner()
    for path, field in (('/usr/bin/ssh', 'clientSha256'), ('/usr/bin/sftp', 'sftpSha256')):
        try: current = digest(path)
        except OSError: raise DevelopmentFault('The SSH/SFTP clients are missing from this host.', 503) from None
        if current != result['transport'][field]: raise DevelopmentFault('The installed SSH client differs from the pinned transport tool.', 503)
    return result


def guest_version(result):
    release = re.search(r'R4OS Release\s+(\d+\.\d+\.\d+)', result['output'])
    kernel = re.search(r'Kernel active\s+(\d+\.\d+\.\d+)', result['output'])
    if result['exitCode'] != 0 or not release or not kernel:
        raise DevelopmentFault('The authenticated guest did not return the R4OS version interface.')
    return {'release': release[1], 'kernel': kernel[1]}


def same_host_image(record, vm):
    # These legacy image fields scope host-key trust and readiness only.
    # The fixed login is independent of VM image and system generation.
    return ((record.get('imageId'), record.get('imageSha256')) == (vm['imageId'], vm['imageSha256'])
            and record.get('systemGeneration') == vm.get('systemGeneration'))


class Access:
    def __init__(self, projects, r4os, boots):
        self.projects, self.r4os, self.boots = Path(projects), Path(r4os), boots
        self.root = folder(self.projects / '.studio/development/Access'); self.locks = {}

    def directory(self, vm_id): return folder(self.root / identity(vm_id))

    def record(self, vm_id):
        path = self.directory(vm_id) / 'access.json'
        if not path.exists():
            record = {'schema': 1, 'vmId': vm_id, 'revision': 0, 'enabled': True, 'imageId': None, 'imageSha256': None}
        else:
            if path.resolve(strict=True) != path: raise DevelopmentFault('Invalid guest access storage.', 503)
            record = json.loads(path.read_text())
        if record.get('schema') != 1: raise DevelopmentFault('Guest access maintenance is required.', 503)
        if record.get('vmId', vm_id) != vm_id: raise DevelopmentFault('Guest access does not belong to this VM.', 503)
        record.setdefault('vmId', vm_id)
        if record.get('credentialPolicy') != CREDENTIAL_POLICY:
            # A result obtained using configurable credentials cannot attest the
            # fixed login. Keep VM-bound host-key trust and explicit disablement.
            for field in ('readiness', 'lastError', 'lastErrorVmRevision'): record.pop(field, None)
        record.update(username=DEFAULT_USERNAME, password=DEFAULT_PASSWORD, credentialPolicy=CREDENTIAL_POLICY)
        return record

    def save_record(self, vm_id, record):
        # Preserve schema-1 fields for pinned workers and rollback releases, but
        # always write the fixed login, never legacy configurable credentials.
        value = {**record, 'username': DEFAULT_USERNAME, 'password': DEFAULT_PASSWORD,
                 'credentialPolicy': CREDENTIAL_POLICY}
        save(self.directory(vm_id) / 'access.json', value)

    def public(self, vm_id):
        vm = vm_config(self.r4os, vm_id); record = self.record(vm_id); reason = None
        try:
            transport_profile()
            if not vm.get('networkEnabled'): raise DevelopmentFault('Network is disabled in VM settings.')
            if not record['enabled']: raise DevelopmentFault('Development access is disabled.')
        except DevelopmentFault as error: reason = str(error)
        same = same_host_image(record, vm)
        readiness = record.get('readiness') if same else None; boot = self.boots.values.get(vm_id)
        current = bool(not reason and readiness and boot and boot['connected'] and readiness['bootId'] == boot['bootId']
            and readiness['vmRevision'] == vm['revision'])
        return {'revision': record['revision'], 'vmRevision': vm['revision'], 'enabled': record['enabled'],
            'username': DEFAULT_USERNAME, 'credentialPolicy': CREDENTIAL_POLICY,
            'hostKeyFingerprint': record.get('hostKeyFingerprint') if same else None, 'imageId': vm['imageId'],
            'available': not bool(reason), 'ready': current, 'reason': reason or (None if current else
                (record.get('lastError') if record.get('lastErrorVmRevision') == vm['revision'] else None) or 'Access has not been checked for the current boot.'),
            'lastCheckedAt': readiness.get('checkedAt') if readiness else None,
            'guestRelease': readiness.get('release') if readiness else None,
            'guestKernel': readiness.get('kernel') if readiness else None}

    def configure(self, vm_id, request):
        if not isinstance(request, dict) or set(request) - {'revision', 'vmRevision', 'enabled', 'resetHostKey'}:
            raise DevelopmentFault('Unexpected development access fields.', 400)
        vm = vm_config(self.r4os, vm_id); old = self.record(vm_id)
        if type(request.get('revision')) is not int: raise DevelopmentFault('Invalid development access revision.', 400)
        if request.get('revision') != old['revision'] or request.get('vmRevision') != vm['revision']:
            raise DevelopmentFault('VM or development access settings changed. Reload before saving.')
        if type(request.get('enabled')) is not bool or type(request.get('resetHostKey', False)) is not bool:
            raise DevelopmentFault('Invalid development access setting.', 400)
        same = same_host_image(old, vm)
        if request['enabled']:
            transport_profile()
            if not vm.get('networkEnabled'): raise DevelopmentFault('Enable Network in VM settings first.')
        value = {'schema': 1, 'vmId': vm_id, 'revision': old['revision'] + 1, 'enabled': request['enabled'],
            'imageId': vm['imageId'], 'imageSha256': vm['imageSha256'], 'systemGeneration': vm.get('systemGeneration')}
        if same and not request.get('resetHostKey'):
            value['hostKeyFingerprint'] = old.get('hostKeyFingerprint')
        else: (self.directory(vm_id) / 'known_hosts').unlink(missing_ok=True)
        self.save_record(vm_id, value)
        return self.public(vm_id)

    async def check(self, vm_id):
        lock = self.locks.setdefault(identity(vm_id), asyncio.Lock())
        if lock.locked(): raise DevelopmentFault('A development access check is already running for this VM.')
        async with lock:
            try: return await self.check_once(vm_id)
            except DevelopmentFault as error:
                record = self.record(vm_id); record['readiness'] = None; record['lastError'] = str(error)
                record['lastErrorVmRevision'] = vm_config(self.r4os, vm_id)['revision']
                self.save_record(vm_id, record)
                raise

    async def check_once(self, vm_id):
        vm = vm_config(self.r4os, vm_id); status = self.public(vm_id)
        if not status['available']: raise DevelopmentFault(status['reason'])
        scope = {'kind': 'access', 'vmRevision': vm['revision'], 'imageId': vm['imageId'], 'imageSha256': vm['imageSha256']}
        with VmLease(self.projects, vm_id, scope) as lease:
            info = await vm_call(lease, 'info')
            if info['vm']['state'] != 'running': raise DevelopmentFault('Start the VM before checking development access.')
            boot = await self.boots.ensure(vm, info['invocationId'])
            scope['bootId'] = boot['bootId']; save(lease.root / 'leases' / (lease.id + '.json'), lease.value)
            async with SshTransport(self, vm, lease) as ssh:
                result = await ssh.exec('VER')
                version = guest_version(result)
                if not self.boots.values[vm_id]['connected'] or self.boots.values[vm_id]['bootId'] != boot['bootId']:
                    raise DevelopmentFault('The VM restarted during its access check.')
                ssh.publish_host_key()
                record = self.record(vm_id); record.pop('lastError', None); record['readiness'] = {'checkedAt': now(), 'vmRevision': vm['revision'],
                    'bootId': boot['bootId'], **version}
                self.save_record(vm_id, record)
        return self.public(vm_id)

class SshTransport:
    def __init__(self, access, vm, lease):
        self.access, self.vm, self.lease = access, vm, lease
        self.profile = transport_profile(); self.record = access.record(vm['id']); self.port = None; self.processes = set(); self.forward_opened = False
        if not same_host_image(self.record, vm): self.record.pop('hostKeyFingerprint', None)
        self.runtime = folder(Path('/run/r4os-studio-development/auth') / lease.id)

    async def __aenter__(self):
        try:
            from forwards import cleanup
            await cleanup(self.lease)
            if not self.record['enabled']:
                raise DevelopmentFault('Development access is disabled.')
            secret = self.runtime / 'password'; secret.write_text(self.record['password']); secret.chmod(0o600)
            known = self.access.directory(self.vm['id']) / 'known_hosts'
            if known.is_symlink() or (known.exists() and not known.is_file()):
                raise DevelopmentFault('Invalid guest host-key storage.', 503)
            if known.exists() and same_host_image(self.record, self.vm):
                if known.resolve(strict=True) != known: raise DevelopmentFault('Invalid guest host-key storage.', 503)
                shutil.copyfile(known, self.runtime / 'known_hosts')
            with socket.socket() as port:
                port.bind(('127.0.0.1', 0)); self.port = port.getsockname()[1]
            self.forward_record = folder(self.lease.root / 'Forwards') / (self.lease.id + '.json')
            self.forward_value = {'schema': 1, 'leaseId': self.lease.id, 'vmId': self.vm['id'], 'port': self.port,
                'scope': self.lease.scope, 'state': 'intent', 'createdAt': now()}
            save(self.forward_record, self.forward_value)
            await vm_call(self.lease, 'forward_open', port=self.port)
            self.forward_opened = True; self.forward_value['state'] = 'open'; save(self.forward_record, self.forward_value)
            return self
        except BaseException:
            await self.__aexit__(None, None, None); raise

    async def __aexit__(self, *args):
        for process in self.processes:
            if process.returncode is None: process.kill(); await process.wait()
        if self.forward_opened:
            try:
                await vm_call(self.lease, 'forward_close', port=self.port)
                self.forward_value['state'] = 'closed'; save(self.forward_record, self.forward_value)
            except Exception: pass  # A stopped QEMU also removes its forwarding.
        shutil.rmtree(self.runtime, ignore_errors=True)

    def argv(self, sftp=False):
        # Quote config values inside the -o argument; filesystem roots may contain spaces.
        known = '"' + str(self.runtime / 'known_hosts').replace('\\', '\\\\').replace('"', '\\"') + '"'
        pinned = bool(self.record.get('hostKeyFingerprint'))
        args = ['/usr/bin/sftp' if sftp else '/usr/bin/ssh', '-F', '/dev/null', '-P' if sftp else '-p', str(self.port),
            '-o', 'ControlMaster=no', '-o', 'HostKeyAlias=studio-' + self.vm['id'] + '-' + self.vm['imageId'],
            '-o', 'StrictHostKeyChecking=' + ('yes' if pinned else 'accept-new'), '-o', 'UserKnownHostsFile=' + known,
            '-o', 'NumberOfPasswordPrompts=1', '-o', 'LogLevel=ERROR', '-o', 'ConnectTimeout=5',
            '-o', 'ServerAliveInterval=2', '-o', 'ServerAliveCountMax=3']
        if sftp: args += ['-o', 'BatchMode=no']
        return args

    def environment(self):
        return {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': str(self.runtime),
            'SSH_ASKPASS': str(APP / 'scripts/project-development/askpass.py'), 'SSH_ASKPASS_REQUIRE': 'force',
            'DISPLAY': ':0', 'STUDIO_ACCESS_REQUEST': self.lease.id}

    async def exec(self, command, timeout=10, *, complete=False, limit=65536):
        if type(limit) is not int or not 1 <= limit <= 131072:
            raise DevelopmentFault('Invalid guest response quota.', 400)
        buffers = {'stdout': bytearray(), 'stderr': bytearray()}
        truncated = False
        def captured(code, **flags):
            return {'exitCode': code, 'output': buffers['stdout'].decode('utf-8', errors='replace'),
                'stdout': buffers['stdout'].decode('utf-8', errors='replace'),
                'stderr': buffers['stderr'].decode('utf-8', errors='replace'),
                'stdoutBytes': len(buffers['stdout']), 'stderrBytes': len(buffers['stderr']),
                'truncated': truncated, 'timedOut': False, **flags}
        process = await asyncio.create_subprocess_exec(*self.argv(), self.record['username'] + '@127.0.0.1', command,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=self.environment(), start_new_session=True)
        self.processes.add(process)
        async def read(stream, channel):
            nonlocal truncated
            result = buffers[channel]
            while data := await stream.read(8192):
                if len(result) + len(data) > limit:
                    result.extend(data[:max(0,limit-len(result))]); truncated = True
                    raise DevelopmentFault('Guest access output exceeds the limit.')
                result.extend(data)
            return bytes(result)
        try:
            out, error = await asyncio.wait_for(asyncio.gather(read(process.stdout, 'stdout'), read(process.stderr, 'stderr')), timeout)
            code = await asyncio.wait_for(process.wait(), 2)
            if code == 255 and complete:
                return captured(code, transportUncertain=True)
            if code == 255:
                if b'HOST IDENTIFICATION HAS CHANGED' in error or b'Host key verification failed' in error:
                    raise DevelopmentFault('The guest host key does not match the saved VM identity.')
                if b'Permission denied' in error: raise DevelopmentFault('The guest rejected the R4OS default login.')
                raise SshNotReady('The guest SSH service is not ready or the connection was lost.')
            return captured(code) if complete else {'exitCode': code, 'output': out.decode('utf-8', errors='replace')}
        except asyncio.TimeoutError:
            if complete: return captured(None, timedOut=True, transportUncertain=True)
            raise SshNotReady('The authenticated guest did not respond in time.') from None
        except DevelopmentFault:
            if complete and truncated: return captured(None, transportUncertain=True)
            raise
        finally:
            if process.returncode is None: process.kill(); await process.wait()
            self.processes.discard(process)

    def publish_host_key(self):
        path = self.runtime / 'known_hosts'
        try:
            rows = [line.split() for line in path.read_text().splitlines() if line and not line.startswith('#')]
            if len(rows) != 1: raise ValueError()
            key = base64.b64decode(rows[0][2], validate=True)
            fingerprint = 'SHA256:' + base64.b64encode(hashlib.sha256(key).digest()).decode().rstrip('=')
            old = self.record.get('hostKeyFingerprint')
            if old and old != fingerprint: raise ValueError()
            known = self.access.directory(self.vm['id']) / 'known_hosts'
            if known.is_symlink() or (known.exists() and not known.is_file()): raise ValueError()
            shutil.copyfile(path, known)
            record = self.access.record(self.vm['id'])
            if not same_host_image(record, self.vm):
                for field in ('readiness', 'lastError', 'lastErrorVmRevision'): record.pop(field, None)
            record.update(hostKeyFingerprint=fingerprint, imageId=self.vm['imageId'], imageSha256=self.vm['imageSha256'], systemGeneration=self.vm.get('systemGeneration'))
            self.access.save_record(self.vm['id'], record)
            self.record.update(hostKeyFingerprint=fingerprint, imageId=self.vm['imageId'], imageSha256=self.vm['imageSha256'], systemGeneration=self.vm.get('systemGeneration'))
        except (OSError, ValueError, IndexError): raise DevelopmentFault('The guest host-key receipt could not be confirmed.') from None
