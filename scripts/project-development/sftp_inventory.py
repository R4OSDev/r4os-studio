"""One read-only SFTP v3 channel for a bounded, typed Exchange inventory.

Uses SSH subsystem transport and public SFTP v3 packets implemented by R4OS
SSHD; does not parse localized OpenSSH ls output or expose a guest shell.
"""
import asyncio
import re
import struct
import stat
from contracts import DevelopmentFault
from exchange_policy import EXCHANGE_LIMITS


def u32(value): return struct.pack('>I', value)
def string(value):
    data = value.encode() if isinstance(value, str) else value
    return u32(len(data)) + data

class Packet:
    def __init__(self, data): self.data = data; self.offset = 0
    def take(self, size):
        if size < 0 or self.offset + size > len(self.data): raise DevelopmentFault('Truncated guest SFTP metadata.')
        value = self.data[self.offset:self.offset + size]; self.offset += size; return value
    def number(self): return struct.unpack('>I', self.take(4))[0]
    def text(self): return self.take(self.number())
    def attrs(self):
        flags = self.number(); size = None; mode = None
        if flags & ~15: raise DevelopmentFault('Unsupported SFTP metadata attributes.')
        if flags & 1: size = struct.unpack('>Q', self.take(8))[0]
        if flags & 2: self.take(8)
        if flags & 4: mode = self.number()
        if flags & 8: self.take(8)
        if size is None or mode is None or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise DevelopmentFault('Exchange contains unsupported or untyped guest files.')
        return size, stat.S_ISDIR(mode)

async def inventory(ssh, exchange):
    process = await asyncio.create_subprocess_exec(*ssh.argv(), '-s', ssh.record['username'] + '@127.0.0.1', 'sftp',
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env=ssh.environment(), start_new_session=True)
    ssh.processes.add(process)
    async def errors():
        total = 0
        while data := await process.stderr.read(4096):
            total += len(data)
            if total > 65536: process.kill(); return
    drain = asyncio.create_task(errors()); sequence = 0
    async def send(data):
        process.stdin.write(u32(len(data)) + data); await process.stdin.drain()
    async def receive():
        size = struct.unpack('>I', await process.stdout.readexactly(4))[0]
        if not 1 <= size <= 65536: raise DevelopmentFault('Oversized SFTP inventory packet.')
        return Packet(await process.stdout.readexactly(size))
    async def request(kind, payload):
        nonlocal sequence
        sequence += 1; await send(bytes([kind]) + u32(sequence) + payload)
        packet = await receive(); response = packet.take(1)[0]
        if packet.number() != sequence: raise DevelopmentFault('The SFTP inventory reply belongs to another request.')
        return response, packet
    async def scan():
        await send(b'\x01' + u32(3)); version = await receive()
        if version.take(1) != b'\x02' or version.number() != 3: raise DevelopmentFault('The guest does not support SFTP v3 inventory.')
        result = []; queue = ['']; seen = set(); files = directories = total_bytes = 0
        while queue:
            parent = queue.pop(0); path = '/' + exchange['drive'] + '/' + parent
            kind, packet = await request(11, string(path))
            if kind != 102: raise DevelopmentFault('The Exchange directory could not be inspected. No upload was started.')
            handle = packet.text()
            if len(handle) > 256: raise DevelopmentFault('Invalid SFTP directory handle.')
            while True:
                kind, packet = await request(12, string(handle))
                if kind == 101:
                    if packet.number() != 1: raise DevelopmentFault('Exchange directory enumeration failed. No upload was started.')
                    break
                if kind != 104: raise DevelopmentFault('Unexpected SFTP directory reply.')
                count = packet.number()
                if not 1 <= count <= 256: raise DevelopmentFault('Invalid SFTP directory entry count.')
                for _ in range(count):
                    try: name = packet.text().decode('ascii')
                    except UnicodeError: raise DevelopmentFault('Exchange filenames must be ASCII.') from None
                    packet.text(); size, directory = packet.attrs()
                    if name in ('.', '..'): continue
                    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', name) or name.endswith('.'):
                        raise DevelopmentFault('Exchange contains unsupported filenames. Preserve and resolve them before deploying.')
                    relative = parent + '/' + name if parent else name
                    if relative.count('/') >= EXCHANGE_LIMITS['depth'] or relative.lower() in seen: raise DevelopmentFault('Exchange paths exceed the supported depth or collide.')
                    seen.add(relative.lower()); result.append({'path': relative, 'directory': directory, 'bytes': size})
                    if directory:
                        if relative.split('/')[0].lower() != 'build': raise DevelopmentFault('Exchange contains a folder outside Build. No upload was started.')
                        queue.append(relative)
                        directories += 1
                    else:
                        files += 1; total_bytes += size
                    if files > EXCHANGE_LIMITS['files'] or directories > EXCHANGE_LIMITS['directories'] or total_bytes > EXCHANGE_LIMITS['bytes']:
                        raise DevelopmentFault('Exchange quota is exceeded. Existing files were preserved.')
                if packet.offset != len(packet.data): raise DevelopmentFault('Unexpected SFTP directory metadata.')
            kind, packet = await request(4, string(handle))
            if kind != 101 or packet.number() != 0: raise DevelopmentFault('The Exchange directory handle could not be closed.')
        return result
    try: return await asyncio.wait_for(scan(), EXCHANGE_LIMITS['syncSeconds'])
    except (asyncio.TimeoutError, asyncio.IncompleteReadError, OSError, ConnectionError):
        raise DevelopmentFault('The read-only Exchange inventory did not complete. No upload was started.') from None
    finally:
        if process.returncode is None: process.kill()
        await process.wait(); ssh.processes.discard(process)
        drain.cancel(); await asyncio.gather(drain, return_exceptions=True)
