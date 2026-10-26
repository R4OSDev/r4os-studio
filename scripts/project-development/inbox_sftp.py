"""Bounded SFTP v3 over the pinned SSH client; only short Inbox transport paths."""
import asyncio
import hashlib
import os
import re
import stat
import struct
from contracts import DevelopmentFault, UnconfirmedGuestEffect, LIMITS

CHUNK = 16384
PREFIX = '/C/R4OS/UPDATE/INBOX/'


def inbox_path(value, extension=None):
    if not isinstance(value, str) or not re.fullmatch(r'/C/R4OS/UPDATE/INBOX/U[A-F0-9]{7}\.(TMP|R4U)', value):
        raise DevelopmentFault('Use only the reserved short update Inbox transport path.', 400)
    if extension and not value.endswith('.' + extension): raise DevelopmentFault('Invalid update transport phase/path.', 400)
    return value


def u32(value): return struct.pack('>I', value)
def u64(value): return struct.pack('>Q', value)
def string(value):
    if isinstance(value, str): value = value.encode('utf8')
    return u32(len(value)) + value


class Reader:
    def __init__(self, value): self.value=value;self.offset=0
    def take(self, count):
        if count < 0 or self.offset+count > len(self.value): raise DevelopmentFault('Incomplete SFTP response.', 409)
        result=self.value[self.offset:self.offset+count];self.offset+=count;return result
    def number(self): return struct.unpack('>I',self.take(4))[0]
    def wide(self): return struct.unpack('>Q',self.take(8))[0]
    def text(self, limit=65536):
        size=self.number()
        if size>limit: raise DevelopmentFault('SFTP string exceeds its quota.')
        return self.take(size)
    def end(self):
        if self.offset!=len(self.value): raise DevelopmentFault('Unknown trailing SFTP response fields.')


class RemoteStatus(DevelopmentFault):
    def __init__(self, code, message):
        super().__init__('Native SFTP refused the operation ('+str(code)+'): '+message[:300])
        self.remote_code=code


class InboxSftp:
    def __init__(self, ssh, guard=lambda:None):
        self.ssh=ssh;self.guard=guard;self.process=None;self.sequence=0;self.stderr=bytearray();self.overflow=False
        self.events=[];self.counts={};self.exit_code=None;self.pending_write=False

    async def __aenter__(self):
        try:
            self.process=await asyncio.create_subprocess_exec(*self.ssh.argv(),'-s',self.ssh.record['username']+'@127.0.0.1','sftp',
                stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,
                env=self.ssh.environment(),start_new_session=True)
            self.ssh.processes.add(self.process)
            async def diagnostic():
                while data:=await self.process.stderr.read(8192):
                    remaining=65536-len(self.stderr);self.stderr.extend(data[:max(0,remaining)])
                    if len(data)>remaining:
                        self.overflow=True;self.process.kill();return
            self.diagnostics=asyncio.create_task(diagnostic())
            await self.send(bytes([1])+u32(3))
            response=await self.packet()
            if len(response)<5 or response[0]!=2 or struct.unpack('>I',response[1:5])[0]!=3:
                raise DevelopmentFault('The guest does not expose supported SFTP v3.')
            extensions=Reader(response[5:])
            while extensions.offset<len(extensions.value):extensions.text(1024);extensions.text(1024)
            return self
        except BaseException:
            await self.__aexit__(None,None,None);raise

    async def __aexit__(self,*args):
        if self.process:
            if self.process.stdin and not self.process.stdin.is_closing():self.process.stdin.close()
            try:await asyncio.wait_for(self.process.wait(),3)
            except asyncio.TimeoutError:
                self.process.kill();await self.process.wait()
            self.exit_code=self.process.returncode
            if hasattr(self,'diagnostics'):
                await asyncio.gather(self.diagnostics,return_exceptions=True)
            self.ssh.processes.discard(self.process)

    async def send(self, value):
        if len(value)>65536:raise DevelopmentFault('SFTP request exceeds its frame quota.')
        self.process.stdin.write(u32(len(value))+value)
        await asyncio.wait_for(self.process.stdin.drain(),15)

    async def packet(self):
        header=await asyncio.wait_for(self.process.stdout.readexactly(4),15)
        size=struct.unpack('>I',header)[0]
        if not 1<=size<=65536:raise DevelopmentFault('SFTP response exceeds its frame quota.')
        return await asyncio.wait_for(self.process.stdout.readexactly(size),15)

    async def request(self, kind, body, mutating=False):
        self.guard();self.sequence+=1
        if self.sequence>100000:raise DevelopmentFault('SFTP request count exceeds its quota.')
        ident=self.sequence;self.pending_write=mutating
        self.counts[str(kind)]=self.counts.get(str(kind),0)+1
        if len(self.events)>255:del self.events[:-255]
        try:
            await self.send(bytes([kind])+u32(ident)+body)
            response=await self.packet();reader=Reader(response[1:])
            if reader.number()!=ident:raise DevelopmentFault('SFTP response belongs to another request.')
            if self.overflow:raise DevelopmentFault('SFTP diagnostics exceeded their quota.')
            if response[0]==101:
                code=reader.number();message=reader.text(4096).decode('utf8',errors='replace');reader.text(1024);reader.end()
                self.events.append({'request':ident,'operation':kind,'status':code,'message':message[:300]})
                if code:raise RemoteStatus(code,message)
            else:
                self.events.append({'request':ident,'operation':kind,'responseType':response[0]})
            self.pending_write=False
            return response[0],reader
        except RemoteStatus:
            self.pending_write=False;raise
        except BaseException as error:
            if mutating:
                raise UnconfirmedGuestEffect('The Inbox write/close/rename acknowledgement is unconfirmed. Inspect the original recorded paths; no write was replayed.') from error
            if isinstance(error,DevelopmentFault):raise
            raise DevelopmentFault('The complete Inbox read response is unavailable. No publication was authorized.') from error

    async def stat(self,path):
        inbox_path(path)
        try:kind,reader=await self.request(17,string(path))
        except RemoteStatus as error:
            if error.remote_code==2:return None
            raise
        if kind!=105:raise DevelopmentFault('SFTP STAT did not return attributes.')
        flags=reader.number();value={}
        if flags & ~15:raise DevelopmentFault('Unsupported SFTP file attributes.')
        if flags&1:value['bytes']=reader.wide()
        if flags&2:reader.number();reader.number()
        if flags&4:value['mode']=reader.number()
        if flags&8:value['accessed']=reader.number();value['modified']=reader.number()
        reader.end()
        if 'bytes' not in value or 'mode' not in value:raise DevelopmentFault('SFTP file attributes are incomplete.')
        value['regular']=stat.S_ISREG(value['mode'])
        return value

    async def open(self,path,write=False):
        inbox_path(path,'TMP' if write else None)
        kind,reader=await self.request(3,string(path)+u32(58 if write else 1)+u32(0),mutating=write)
        try:
            if kind!=102:raise DevelopmentFault('SFTP OPEN did not return its handle.')
            handle=reader.text(256);reader.end()
            if not handle:raise DevelopmentFault('The SFTP handle is empty.')
        except DevelopmentFault as error:
            if write:raise UnconfirmedGuestEffect('The Inbox OPEN acknowledgement is malformed; inspect the recorded path.') from error
            raise
        return handle

    async def close(self,handle,write=False):
        kind,reader=await self.request(4,string(handle),mutating=write)
        if kind!=101:
            if write:raise UnconfirmedGuestEffect('The Inbox CLOSE acknowledgement is malformed.')
            raise DevelopmentFault('SFTP CLOSE has no native acknowledgement.')

    async def write(self,handle,offset,data):
        if not data or len(data)>CHUNK:raise DevelopmentFault('Invalid sequential Inbox chunk.')
        kind,reader=await self.request(6,string(handle)+u64(offset)+string(data),mutating=True)
        if kind!=101:raise UnconfirmedGuestEffect('The Inbox WRITE acknowledgement is malformed.')

    async def read(self,handle,offset):
        try:kind,reader=await self.request(5,string(handle)+u64(offset)+u32(CHUNK))
        except RemoteStatus as error:
            if error.remote_code==1:return b''
            raise
        if kind!=103:raise DevelopmentFault('SFTP READ did not return data or EOF.')
        data=reader.text(CHUNK);reader.end()
        if not data:raise DevelopmentFault('SFTP READ returned an empty non-EOF response.')
        return data

    async def rename(self,source,destination):
        inbox_path(source,'TMP');inbox_path(destination,'R4U')
        if source.rsplit('.',1)[0]!=destination.rsplit('.',1)[0]:raise DevelopmentFault('Rename only the reserved transport pair.')
        kind,reader=await self.request(18,string(source)+string(destination),mutating=True)
        if kind!=101:raise UnconfirmedGuestEffect('The Inbox RENAME acknowledgement is malformed.')

    async def put(self,path,local,expected,progress=lambda value:None,before_close=lambda:None):
        inbox_path(path,'TMP')
        if local.resolve(strict=True)!=local or not local.is_file():raise DevelopmentFault('The frozen package path changed.')
        fd=os.open(local,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as source:
            before=os.fstat(source.fileno())
            signature=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size!=expected['bytes'] or not 64<before.st_size<=LIMITS['packageBytes']:
                raise DevelopmentFault('The frozen package identity changed.')
            if hashlib.file_digest(source,'sha256').hexdigest()!=expected['sha256'] or signature(os.fstat(source.fileno()))!=signature(before):
                raise DevelopmentFault('The frozen package hash changed before upload.')
            source.seek(0);handle=await self.open(path,write=True);offset=0;hashed=hashlib.sha256()
            while data:=source.read(CHUNK):
                if offset+len(data)>expected['bytes'] or offset+len(data)>LIMITS['packageBytes']:raise DevelopmentFault('The frozen package exceeded its accepted size.')
                if signature(os.fstat(source.fileno()))!=signature(before):raise DevelopmentFault('The frozen package changed during transfer.')
                self.guard();await self.write(handle,offset,data);hashed.update(data);offset+=len(data);progress(offset)
            if signature(os.fstat(source.fileno()))!=signature(before):raise DevelopmentFault('The frozen package changed during transfer.')
        if offset!=expected['bytes'] or hashed.hexdigest()!=expected['sha256']:
            raise DevelopmentFault('The frozen local package changed during transfer.')
        before_close()
        await self.close(handle,write=True)
        return {'bytes':offset,'sha256':hashed.hexdigest(),'closeAcknowledged':True}

    async def get_hash(self,path,maximum=LIMITS['packageBytes']):
        info=await self.stat(path)
        if info is None:return None
        if not info['regular']:raise DevelopmentFault('The transport path is not a regular file.')
        if info['bytes']>maximum:raise DevelopmentFault('The Inbox file exceeds its accepted readback quota.')
        handle=await self.open(path);offset=0;hashed=hashlib.sha256()
        while True:
            data=await self.read(handle,offset)
            if not data:break
            offset+=len(data)
            if offset>info['bytes'] or offset>maximum:raise DevelopmentFault('The Inbox file changed or exceeds its readback quota.')
            hashed.update(data)
        await self.close(handle)
        after=await self.stat(path)
        if after is None or after['bytes']!=info['bytes'] or offset!=info['bytes']:raise DevelopmentFault('The complete Inbox file changed during readback.')
        return {'bytes':offset,'sha256':hashed.hexdigest(),'fullReadVerified':True}
