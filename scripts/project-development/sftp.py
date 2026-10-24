"""Bounded create-only transfer with complete byte readback from the guest."""
import asyncio
import os
from pathlib import Path
import re
import uuid

from contracts import DevelopmentFault, UnconfirmedGuestEffect, LIMITS, digest


def quote(value): return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


def remote(path):
    if not re.fullmatch(r'/C/(?:[A-Z0-9_-]{1,8}/)*(?:[A-Z0-9_-]{1,8})(?:\.[A-Z0-9]{1,3})?', path):
        raise DevelopmentFault('Invalid owned guest package path.', 400)
    return path


async def batch(ssh, lines, allow_failure=False):
    payload = ('\n'.join(lines) + '\n').encode()
    if len(payload) > 8192: raise DevelopmentFault('SFTP operation exceeds the frame limit.')
    process = await asyncio.create_subprocess_exec(*ssh.argv(True), '-b', '-', ssh.record['username'] + '@127.0.0.1',
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env=ssh.environment(), start_new_session=True)
    ssh.processes.add(process)
    async def read(stream):
        result = bytearray()
        while data := await stream.read(8192):
            if len(result) + len(data) > 65536: raise DevelopmentFault('SFTP diagnostics exceed the limit.')
            result.extend(data)
        return bytes(result)
    try:
        process.stdin.write(payload); await process.stdin.drain(); process.stdin.close()
        await asyncio.wait_for(asyncio.gather(read(process.stdout), read(process.stderr)), LIMITS['transferTimeoutSeconds'])
        code = await process.wait()
        if code == 255: raise UnconfirmedGuestEffect('The SFTP connection was lost. Inspect the preserved guest files before retrying.')
        if code and not allow_failure: raise DevelopmentFault('The guest file transfer failed. Partial files were preserved.')
        return code == 0
    except asyncio.TimeoutError:
        raise UnconfirmedGuestEffect('The guest transfer timed out without a confirmed receipt.') from None
    finally:
        if process.returncode is None: process.kill(); await process.wait()
        ssh.processes.discard(process)


async def download(ssh, guest, local, maximum=LIMITS['packageBytes'], allow_missing=False):
    local = Path(local)
    if local.exists() or local.is_symlink(): raise DevelopmentFault('The verification destination already exists.')
    ok = await batch(ssh, ['get ' + quote(remote(guest)) + ' ' + quote(local)], allow_failure=allow_missing)
    if not ok: return False
    validate_download(local, maximum)
    return True


def validate_download(path, maximum):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > maximum:
        raise DevelopmentFault('The guest verification file is invalid or oversized.')


async def publish_file(ssh, source, guest, expected_sha256):
    source = Path(source); guest = remote(guest)
    if source.is_symlink() or source.stat().st_size > LIMITS['packageBytes'] or digest(source) != expected_sha256:
        raise DevelopmentFault('The local deployment file changed before transfer.')
    # The guest SFTP server implements create-only writes. Never request rename
    # over an existing path or use OpenSSH's ordinary overwrite assumptions.
    verify = ssh.runtime / ('verify-' + uuid.uuid4().hex)
    if verify.exists() or verify.is_symlink(): raise DevelopmentFault('The verification destination already exists.')
    try:
        # One authenticated SFTP session, with close/publication before readback.
        await batch(ssh, ['put ' + quote(source) + ' ' + quote(guest),
                          'get ' + quote(guest) + ' ' + quote(verify)])
        validate_download(verify, LIMITS['packageBytes'])
        if verify.stat().st_size != source.stat().st_size or digest(verify) != expected_sha256:
            raise DevelopmentFault('Guest bytes do not match the deployment package. No start was authorized.')
    finally: verify.unlink(missing_ok=True)
    return {'path': guest, 'sha256': expected_sha256, 'bytes': source.stat().st_size, 'fullReadbackVerified': True}
