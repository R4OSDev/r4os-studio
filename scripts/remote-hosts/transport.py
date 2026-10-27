"""Pinned OpenSSH client with a remote endpoint, never a VM/NAT/lease target."""
import asyncio
import base64
import hashlib
import os
from pathlib import Path
import re
import signal
import shutil
import stat
import sys

APP = Path(__file__).resolve().parents[2]
sys.path.extend([str(APP / 'scripts/project-development'), str(APP / 'scripts/projects')])
from access import transport_profile, guest_version
from contracts import DevelopmentFault
from catalog import CatalogFault, host_address, identity, regular


def private_directory(path):
    path = Path(path).absolute()
    if path.parent.resolve(strict=True) != path.parent: raise CatalogFault('Invalid private remote runtime.', 503)
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.stat()
    if path.resolve(strict=True) != path or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise CatalogFault('Invalid private remote runtime.', 503)
    return path


def key_receipt(path, alias, port):
    if not path.exists() and not path.is_symlink(): return None
    regular(path)
    if path.stat().st_size > 16384: raise CatalogFault('The observed host key exceeds its limit.', 503)
    lines = [line.split() for line in path.read_text().splitlines() if line and not line.startswith('#')]
    if len(lines) != 1 or len(lines[0]) != 3: raise CatalogFault('The observed host key could not be confirmed.', 503)
    name, kind, encoded = lines[0]
    if name not in (alias, '[' + alias + ']:' + str(port)) or kind not in ('ssh-ed25519', 'ssh-rsa', 'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521'):
        raise CatalogFault('The observed key has another target or unsupported type.', 503)
    try:
        raw = base64.b64decode(encoded, validate=True)
        length = int.from_bytes(raw[:4], 'big')
        if not 1 <= length <= 128 or raw[4:4+length].decode('ascii') != kind or not 4+length < len(raw) <= 8192: raise ValueError()
    except (ValueError, UnicodeError): raise CatalogFault('The observed host key is invalid.', 503) from None
    return {'keyType': kind, 'keyData': encoded, 'fingerprint': 'SHA256:' + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')}


class RemoteTransport:
    def __init__(self, target, runtime, request_id):
        # This object is private to the fixed broker. It must never be serialized.
        self.profile = transport_profile(); self.target = target; self.processes = set()
        self.request_id = identity(request_id); self.runtime_root = private_directory(runtime)
        self.auth = private_directory(self.runtime_root / 'auth'); self.runtime = self.auth / self.request_id
        self.alias = 'studio-remote-' + identity(target['id']) + '-' + str(target['endpointRevision'])

    async def __aenter__(self):
        self.runtime.mkdir(mode=0o700)  # A previous attempt is never silently reused.
        try:
            secret = self.runtime / 'password'; secret.write_text(self.target['password']); secret.chmod(0o600)
            known = self.runtime / 'known_hosts'
            key = self.target['key']
            if key['state'] == 'trusted':
                known.write_text(self.alias + ' ' + key['key_type'] + ' ' + key['key_data'] + '\n'); known.chmod(0o600)
                if key_receipt(known, self.alias, self.target['port'])['fingerprint'] != key['fingerprint']:
                    raise CatalogFault('The saved host key needs local maintenance.', 503)
            return self
        except BaseException:
            await self.__aexit__(None, None, None); raise

    async def __aexit__(self, *args):
        for process in tuple(self.processes):
            if process.returncode is None: process.kill(); await process.wait()
        shutil.rmtree(self.runtime)

    def argv(self, sftp=False):
        known = '"' + str(self.runtime / 'known_hosts').replace('\\', '\\\\').replace('"', '\\"') + '"'
        options = ['ControlMaster=no', 'ControlPath=none', 'ProxyCommand=none', 'ProxyJump=none', 'ForwardAgent=no',
                   'ClearAllForwardings=yes', 'PermitLocalCommand=no', 'IdentitiesOnly=yes', 'IdentityAgent=none',
                   'PubkeyAuthentication=no', 'KbdInteractiveAuthentication=no', 'PreferredAuthentications=password',
                   'NumberOfPasswordPrompts=1', 'GlobalKnownHostsFile=/dev/null', 'UserKnownHostsFile=' + known,
                   'StrictHostKeyChecking=' + ('yes' if self.target['key']['state'] == 'trusted' else 'accept-new'),
                   'HostKeyAlias=' + self.alias, 'UpdateHostKeys=no', 'VerifyHostKeyDNS=no', 'HashKnownHosts=no',
                   'CanonicalizeHostname=no', 'AddKeysToAgent=no', 'LogLevel=ERROR', 'ConnectTimeout=5',
                   'ServerAliveInterval=2', 'ServerAliveCountMax=3', 'User=' + self.target['user']]
        if sftp: options.append('BatchMode=no')
        args = ['/usr/bin/sftp' if sftp else '/usr/bin/ssh', '-F', '/dev/null', '-P' if sftp else '-p', str(self.target['port'])]
        for value in options: args.extend(['-o', value])
        return args

    def destination(self, sftp=False):
        address = host_address(self.target['address'])
        return '[' + address + ']' if sftp and ':' in address else address

    def environment(self):
        return {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': str(self.runtime), 'DISPLAY': ':0',
                'SSH_ASKPASS': str(APP / 'scripts/remote-hosts/askpass.py'), 'SSH_ASKPASS_REQUIRE': 'force',
                'STUDIO_REMOTE_REQUEST': self.request_id, 'STUDIO_REMOTE_AUTH_ROOT': str(self.auth)}

    async def execute(self, command, timeout=15, limit=65536):
        process = await asyncio.create_subprocess_exec(*self.argv(), self.destination(), command,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=self.environment(), start_new_session=True)
        self.processes.add(process); buffers = {'stdout': bytearray(), 'stderr': bytearray()}
        async def capture(stream, key):
            while raw := await stream.read(8192):
                if len(buffers[key]) + len(raw) > limit: raise CatalogFault('The SSH response exceeded its quota.', 503)
                buffers[key].extend(raw)
        try:
            await asyncio.wait_for(asyncio.gather(capture(process.stdout, 'stdout'), capture(process.stderr, 'stderr')), timeout)
            code = await asyncio.wait_for(process.wait(), 2)
            return {'exitCode': code, **{k: bytes(v).decode('utf8', errors='replace') for k, v in buffers.items()}}
        finally:
            if process.returncode is None: process.kill(); await process.wait()
            self.processes.discard(process)

    async def check(self):
        try:
            result = await self.execute('VER')
            key = key_receipt(self.runtime / 'known_hosts', self.alias, self.target['port'])
            if result['exitCode'] == 255:
                error = result['stderr']
                status = ('hostkey_changed' if re.search('HOST IDENTIFICATION HAS CHANGED|Host key verification failed', error)
                          else 'authentication_failed' if 'Permission denied' in error
                          else 'timeout' if re.search('Connection timed out|Operation timed out', error)
                          else 'offline' if re.search('Connection refused|No route to host|Could not resolve hostname|Network is unreachable', error)
                          else 'transport_error')
                return {'status': status, 'key': key}
            try: version = guest_version({'exitCode': result['exitCode'], 'output': result['stdout']})
            except DevelopmentFault: return {'status': 'not_r4os', 'key': key}
            if any(not re.fullmatch(r'[0-9]{1,10}\.[0-9]{1,10}\.[0-9]{1,10}', text) for text in version.values()): return {'status': 'not_r4os', 'key': key}
            if key is None: return {'status': 'transport_error', 'key': None}
            return {'status': 'success', 'key': key, 'version': version['release'], 'kernel': version['kernel']}
        except asyncio.TimeoutError: return {'status': 'timeout', 'key': key_receipt(self.runtime / 'known_hosts', self.alias, self.target['port'])}

    async def execute_complete(self, command, timeout, abort, limit=16384):
        """No retry: a local client end cannot attest every remote process end."""
        buffers = {'stdout': bytearray(), 'stderr': bytearray()}; code = None
        flags = {'timedOut': False, 'stoppedLocally': False, 'outputTruncated': False, 'dispatched': False}
        process = None; capture_task = stop_task = None
        async def capture(stream, channel):
            while data := await stream.read(8192):
                remaining = limit - len(buffers[channel]); buffers[channel].extend(data[:max(0, remaining)])
                if len(data) > remaining: flags['outputTruncated'] = True; raise CatalogFault('The remote output limit was reached.', 503)
        try:
            if abort.is_set(): flags['stoppedLocally'] = True
            else:
                process = await asyncio.create_subprocess_exec(*self.argv(), self.destination(), command,
                    stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    env=self.environment(), start_new_session=True)
                self.processes.add(process); flags['dispatched'] = True
                async def collect():
                    await asyncio.gather(capture(process.stdout, 'stdout'), capture(process.stderr, 'stderr'))
                    return await process.wait()
                capture_task = asyncio.create_task(collect()); stop_task = asyncio.create_task(abort.wait())
                done, _ = await asyncio.wait((capture_task, stop_task), timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
                if capture_task in done:
                    try: code = capture_task.result()
                    except Exception: pass
                elif stop_task in done: flags['stoppedLocally'] = True
                else: flags['timedOut'] = True
        except asyncio.CancelledError: flags['stoppedLocally'] = True
        except OSError: pass  # A failed local spawn is not a remote command exit.
        finally:
            if process and process.returncode is None:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                await process.wait()
            for task in (capture_task, stop_task):
                if task and not task.done(): task.cancel()
            await asyncio.gather(*(task for task in (capture_task, stop_task) if task), return_exceptions=True)
            if process: self.processes.discard(process)
        confirmed = bool(flags['dispatched'] and code is not None and 0 <= code < 255 and not any(flags[k] for k in ('timedOut', 'stoppedLocally', 'outputTruncated')))
        def safe(raw): return bytes(raw).decode('utf8', errors='replace').replace(self.target['password'], '[redacted password]')
        return {**{k: safe(v) for k, v in buffers.items()}, **flags, 'sshExitCode': process.returncode if process else None,
                'commandExitCode': code if confirmed else None, 'commandReturnConfirmed': confirmed,
                'localClientEndConfirmed': True, 'remoteProcessEndConfirmed': False,
                'transportUncertain': bool(flags['dispatched'] and not confirmed)}
