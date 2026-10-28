"""Bounded SFTP v3 for canonical R4OS drives; create-only, no shell or FTP."""
import asyncio
import hashlib
import os
import re
import signal
import stat
from catalog import CatalogFault
from inbox_sftp import Reader, string, u32, u64
from contracts import DevelopmentFault

CHUNK = 16384
MAX_FILE = 8 * 1024 * 1024


def path(value):
    if not isinstance(value, str): raise CatalogFault('Use an absolute R4OS SFTP path such as /C/TEMP/file.bin.', 400)
    try: raw = value.encode('utf8')
    except UnicodeError: raise CatalogFault('Use valid UTF-8 R4OS filenames.', 400) from None
    if not re.match(r'^/[A-Z]/', value) or len(raw) > 1023:
        raise CatalogFault('Use /C/, /D/ or another actual R4OS drive, within1023 UTF-8 bytes.', 400)
    names = value[3:].split('/') if value[3:] else []
    if any(not n or n in ('.', '..') or len(n.encode('utf-16-le')) // 2 > 255
           or any(ord(c) < 32 or ord(c) == 127 or c in '<>:"\\|?*' for c in n) for n in names):
        raise CatalogFault('Use native R4OS path components, without traversal, controls or reserved characters.', 400)
    return value


class NativeStatus(CatalogFault):
    def __init__(self, code):
        self.native_code = code
        super().__init__('The R4OS SFTP server does not support this operation.' if code == 8 else 'R4OS SFTP refused this operation (status ' + str(code) + ').', 409)


def attributes(reader):
    flags = reader.number(); value = {}
    if flags & ~15: raise CatalogFault('Unsupported native SFTP attributes.', 409)
    if flags & 1: value['bytes'] = reader.wide()
    if flags & 2: reader.number(); reader.number()
    if flags & 4: value['mode'] = reader.number()
    if flags & 8: value['accessed'] = reader.number(); value['modified'] = reader.number()
    return value


class RemoteSftp:
    def __init__(self, ssh, guard=lambda: None):
        self.ssh = ssh; self.guard = guard; self.sequence = 0; self.process = None; self.diagnostics = None

    async def __aenter__(self):
        try:
            self.process = await asyncio.create_subprocess_exec(*self.ssh.argv(), '-s', '--', self.ssh.destination(), 'sftp',
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                env=self.ssh.environment(), start_new_session=True)
            self.ssh.processes.add(self.process)
            async def diagnostics():
                size = 0
                while data := await self.process.stderr.read(4096):
                    size += len(data)
                    if size > 16384: self.process.kill(); return
                # Raw SSH diagnostics, which can contain credentials, are not receipts.
            self.diagnostics = asyncio.create_task(diagnostics())
            await self.send(bytes([1]) + u32(3)); response = await self.packet()
            if len(response) < 5 or response[:5] != bytes([2]) + u32(3): raise CatalogFault('This host does not expose supported SFTP v3.', 409)
            reader = Reader(response[5:])
            while reader.offset < len(reader.value): reader.text(1024); reader.text(1024)
            return self
        except BaseException:
            await self.__aexit__(None, None, None); raise

    async def __aexit__(self, *args):
        if self.process:
            if self.process.returncode is None:
                try: os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
            await self.process.wait(); self.ssh.processes.discard(self.process)
        if self.diagnostics: await asyncio.gather(self.diagnostics, return_exceptions=True)

    async def send(self, value):
        self.guard()
        if len(value) > 65536: raise CatalogFault('SFTP request exceeds its frame quota.', 413)
        self.process.stdin.write(u32(len(value)) + value); await asyncio.wait_for(self.process.stdin.drain(), 10)

    async def packet(self):
        import struct
        size = struct.unpack('>I', await asyncio.wait_for(self.process.stdout.readexactly(4), 10))[0]
        if not 1 <= size <= 65536: raise CatalogFault('SFTP response exceeds its frame quota.', 413)
        return await asyncio.wait_for(self.process.stdout.readexactly(size), 10)

    async def request(self, kind, body):
        self.sequence += 1
        if self.sequence > 4096: raise CatalogFault('SFTP request count exceeds its quota.', 413)
        try:
            await self.send(bytes([kind]) + u32(self.sequence) + body); response = await self.packet()
            reader = Reader(response[1:])
            if reader.number() != self.sequence: raise CatalogFault('SFTP response belongs to another request.', 409)
            if response[0] == 101:
                code = reader.number(); reader.text(4096); reader.text(1024); reader.end()
                if code: raise NativeStatus(code)
            return response[0], reader
        except DevelopmentFault: raise CatalogFault('The native SFTP response is incomplete or unsupported.', 409) from None

    async def close(self, handle):
        kind, reader = await self.request(4, string(handle))
        if kind != 101: raise CatalogFault('SFTP CLOSE acknowledgement is unavailable.', 409)

    async def handle(self, kind, body):
        reply, reader = await self.request(kind, body)
        if reply != 102: raise CatalogFault('SFTP did not return a native handle.', 409)
        handle = reader.text(256); reader.end()
        if not handle: raise CatalogFault('The SFTP handle is empty.', 409)
        return handle

    async def stat(self, name):
        try: kind, reader = await self.request(7, string(path(name)))  # LSTAT: never follow a link.
        except NativeStatus as error:
            if error.native_code == 2: return None
            raise
        if kind != 105: raise CatalogFault('SFTP did not return file attributes.', 409)
        value = attributes(reader); reader.end()
        if 'mode' not in value or 'bytes' not in value: raise CatalogFault('SFTP file identity is incomplete.', 409)
        return value

    async def listing(self, name):
        handle = await self.handle(11, string(path(name))); entries = []; total = 0; limited = False
        try:
            while True:
                try: kind, reader = await self.request(12, string(handle))
                except NativeStatus as error:
                    if error.native_code == 1: break
                    raise
                if kind != 104: raise CatalogFault('SFTP READDIR did not return names.', 409)
                count = reader.number()
                if not 1 <= count <= 128: raise CatalogFault('SFTP directory page exceeds its quota.', 413)
                for _ in range(count):
                    filename = reader.text(1023).decode('utf8'); reader.text(4096); info = attributes(reader)
                    if filename in ('.', '..'): continue
                    path(name.rstrip('/') + '/' + filename)
                    if '/' in filename: raise CatalogFault('Invalid native SFTP directory name.', 409)
                    value = {'name': filename, 'bytes': info.get('bytes'), 'kind': 'directory' if stat.S_ISDIR(info.get('mode', 0)) else 'file' if stat.S_ISREG(info.get('mode', 0)) else 'unsupported'}
                    total += len(filename.encode()) + 128
                    if len(entries) < 128 and total <= 90000: entries.append(value)
                    else: limited = True
                reader.end()
                if limited: break
        finally: await self.close(handle)
        return {'path': name, 'entries': entries, 'truncated': limited, 'maximumEntries': 128}

    async def get(self, name, maximum=MAX_FILE):
        info = await self.stat(name)
        if info is None: raise CatalogFault('The remote file does not exist.', 404)
        if not stat.S_ISREG(info['mode']) or info['bytes'] > maximum: raise CatalogFault('Read a regular remote file within the requested byte limit.', 413)
        handle = await self.handle(3, string(path(name)) + u32(1) + u32(0)); content = bytearray()
        try:
            while True:
                try: kind, reader = await self.request(5, string(handle) + u64(len(content)) + u32(CHUNK))
                except NativeStatus as error:
                    if error.native_code == 1: break
                    raise
                if kind != 103: raise CatalogFault('SFTP READ has no data or EOF.', 409)
                data = reader.text(CHUNK); reader.end()
                if not data or len(content) + len(data) > min(maximum, info['bytes']): raise CatalogFault('The remote file changed or exceeds its byte limit.', 409)
                content.extend(data)
        finally: await self.close(handle)
        after = await self.stat(name)
        if after is None or any(after.get(k) != info.get(k) for k in ('bytes', 'mode', 'modified')) or len(content) != info['bytes']:
            raise CatalogFault('The complete remote file changed during readback.', 409)
        return bytes(content)

    async def put(self, name, content, before_write=lambda: None, progress=lambda value: None):
        if await self.stat(name) is not None: raise CatalogFault('The remote destination already exists. Choose an unused path; no overwrite is supported.', 409)
        before_write()
        handle = await self.handle(3, string(path(name)) + u32(58) + u32(0))  # WRITE|CREAT|TRUNC|EXCL, native create-only.
        progress({'openAcknowledged': True, 'stagedBytesAcknowledged': 0, 'publicationCloseAcknowledged': False})
        for offset in range(0, len(content), CHUNK):
            kind, reader = await self.request(6, string(handle) + u64(offset) + string(content[offset:offset + CHUNK]))
            if kind != 101: raise CatalogFault('The native SFTP WRITE acknowledgement is unavailable.', 409)
            end = min(offset + CHUNK, len(content))
            if end % 262144 == 0 or end == len(content):
                progress({'openAcknowledged': True, 'stagedBytesAcknowledged': end, 'publicationCloseAcknowledged': False})
        await self.close(handle)  # Native publication is on CLOSE, not OPEN.
        progress({'openAcknowledged': True, 'stagedBytesAcknowledged': len(content), 'publicationCloseAcknowledged': True})
        readback = await self.get(name)
        if readback != content: raise CatalogFault('The uploaded bytes could not be fully verified. No upload was repeated.', 409)
        return {'path': name, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(), 'closeAcknowledged': True, 'fullReadbackVerified': True, 'createOnly': True}
