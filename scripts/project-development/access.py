"""Explicit private SSH access configuration and authenticated readiness checks."""
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket

from contracts import APP, DevelopmentFault, digest, identity
from jobs import folder, now
from layout import save
from profiles import runner
from lease import VmLease
from vm_client import vm_call


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
    # Credentials belong to the VM directory and survive image replacement.
    return (record.get('imageId'), record.get('imageSha256')) == (vm['imageId'], vm['imageSha256'])


class Access:
    def __init__(self, projects, r4os, boots):
        self.projects, self.r4os, self.boots = Path(projects), Path(r4os), boots
        self.root = folder(self.projects / '.studio/development/Access'); self.locks = {}

    def directory(self, vm_id): return folder(self.root / identity(vm_id))

    def record(self, vm_id):
        path = self.directory(vm_id) / 'access.json'
        if not path.exists(): return {'schema': 1, 'vmId': vm_id, 'revision': 0, 'enabled': False, 'username': '', 'password': '', 'imageId': None, 'imageSha256': None}
        if path.resolve(strict=True) != path: raise DevelopmentFault('Invalid guest credential storage.', 503)
        record = json.loads(path.read_text())
        if record.get('schema') != 1: raise DevelopmentFault('Guest access maintenance is required.', 503)
        if record.get('vmId', vm_id) != vm_id: raise DevelopmentFault('Guest credentials do not belong to this VM.', 503)
        record.setdefault('vmId', vm_id)  # Existing per-VM records need no credential migration.
        return record

    def public(self, vm_id):
        vm = vm_config(self.r4os, vm_id); record = self.record(vm_id); reason = None
        try:
            transport_profile()
            if not vm.get('networkEnabled'): raise DevelopmentFault('Network is disabled in VM settings.')
            if not record['enabled']: raise DevelopmentFault('Development access is disabled.')
            if not record['password']: raise DevelopmentFault('Guest credentials are missing.')
        except DevelopmentFault as error: reason = str(error)
        same = same_host_image(record, vm)
        readiness = record.get('readiness') if same else None; boot = self.boots.values.get(vm_id)
        current = bool(not reason and readiness and boot and boot['connected'] and readiness['bootId'] == boot['bootId']
            and readiness['vmRevision'] == vm['revision'])
        return {'revision': record['revision'], 'vmRevision': vm['revision'], 'enabled': record['enabled'],
            'username': record['username'], 'credentialsStored': bool(record['password']),
            'hostKeyFingerprint': record.get('hostKeyFingerprint') if same else None, 'imageId': vm['imageId'],
            'available': not bool(reason), 'ready': current, 'reason': reason or (None if current else
                (record.get('lastError') if record.get('lastErrorVmRevision') == vm['revision'] else None) or 'Access has not been checked for the current boot.'),
            'lastCheckedAt': readiness.get('checkedAt') if readiness else None,
            'guestRelease': readiness.get('release') if readiness else None,
            'guestKernel': readiness.get('kernel') if readiness else None}

    def configure(self, vm_id, request):
        if not isinstance(request, dict) or set(request) - {'revision', 'vmRevision', 'enabled', 'username', 'password', 'resetHostKey'}:
            raise DevelopmentFault('Unexpected development access fields.', 400)
        vm = vm_config(self.r4os, vm_id); old = self.record(vm_id)
        if type(request.get('revision')) is not int: raise DevelopmentFault('Invalid development access revision.', 400)
        if request.get('revision') != old['revision'] or request.get('vmRevision') != vm['revision']:
            raise DevelopmentFault('VM or development access settings changed. Reload before saving.')
        if type(request.get('enabled')) is not bool or type(request.get('resetHostKey', False)) is not bool:
            raise DevelopmentFault('Invalid development access setting.', 400)
        name = request.get('username', '')
        if not isinstance(name, str) or (request['enabled'] and not re.fullmatch(r'[A-Za-z0-9_.-]{1,32}', name)):
            raise DevelopmentFault('Enter a valid guest username.', 400)
        password = request.get('password', '')
        if not isinstance(password, str) or len(password.encode()) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in password):
            raise DevelopmentFault('Invalid guest password.', 400)
        same = same_host_image(old, vm)
        if request['enabled']:
            transport_profile()
            if not vm.get('networkEnabled'): raise DevelopmentFault('Enable Network explicitly in VM settings first.')
            if not password: password = old['password']
            if not password: raise DevelopmentFault('Enter the guest password for this VM.', 400)
        value = {'schema': 1, 'vmId': vm_id, 'revision': old['revision'] + 1, 'enabled': request['enabled'],
            'username': name, 'password': password if request['enabled'] else '',
            'imageId': vm['imageId'], 'imageSha256': vm['imageSha256']}
        if same and not request.get('resetHostKey'):
            value['hostKeyFingerprint'] = old.get('hostKeyFingerprint')
        else: (self.directory(vm_id) / 'known_hosts').unlink(missing_ok=True)
        save(self.directory(vm_id) / 'access.json', value)
        return self.public(vm_id)

    async def check(self, vm_id):
        lock = self.locks.setdefault(identity(vm_id), asyncio.Lock())
        if lock.locked(): raise DevelopmentFault('A development access check is already running for this VM.')
        async with lock:
            try: return await self.check_once(vm_id)
            except DevelopmentFault as error:
                record = self.record(vm_id); record['readiness'] = None; record['lastError'] = str(error)
                record['lastErrorVmRevision'] = vm_config(self.r4os, vm_id)['revision']
                save(self.directory(vm_id) / 'access.json', record)
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
                save(self.directory(vm_id) / 'access.json', record)
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
            if not self.record['enabled'] or not self.record['password']:
                raise DevelopmentFault('Development access is disabled or guest credentials are missing.')
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

    async def exec(self, command, timeout=10):
        process = await asyncio.create_subprocess_exec(*self.argv(), self.record['username'] + '@127.0.0.1', command,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=self.environment(), start_new_session=True)
        self.processes.add(process)
        async def read(stream, limit):
            result = bytearray()
            while data := await stream.read(8192):
                if len(result) + len(data) > limit: raise DevelopmentFault('Guest access output exceeds the limit.')
                result.extend(data)
            return bytes(result)
        try:
            out, error = await asyncio.wait_for(asyncio.gather(read(process.stdout, 65536), read(process.stderr, 65536)), timeout)
            code = await asyncio.wait_for(process.wait(), 2)
            if code == 255:
                if b'HOST IDENTIFICATION HAS CHANGED' in error or b'Host key verification failed' in error:
                    raise DevelopmentFault('The guest host key does not match the saved VM identity.')
                if b'Permission denied' in error: raise DevelopmentFault('Guest authentication failed. Check the saved credentials.')
                raise DevelopmentFault('The guest SSH service is not ready or the connection was lost.')
            return {'exitCode': code, 'output': out.decode('utf-8', errors='replace')}
        except asyncio.TimeoutError: raise DevelopmentFault('The authenticated guest did not respond in time.') from None
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
            record.update(hostKeyFingerprint=fingerprint, imageId=self.vm['imageId'], imageSha256=self.vm['imageSha256'])
            save(self.access.directory(self.vm['id']) / 'access.json', record)
            self.record.update(hostKeyFingerprint=fingerprint, imageId=self.vm['imageId'], imageSha256=self.vm['imageSha256'])
        except (OSError, ValueError, IndexError): raise DevelopmentFault('The guest host-key receipt could not be confirmed.') from None
