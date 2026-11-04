"""Scoped public HTTP proxy; no private/host destinations or request logging."""
import asyncio
import ctypes
import ipaddress
import os
import socket
import struct
from urllib.parse import urlsplit


def host_addresses():
    class Address(ctypes.Structure):pass
    Address._fields_=[('next',ctypes.POINTER(Address)),('name',ctypes.c_void_p),('flags',ctypes.c_uint),
        ('address',ctypes.c_void_p),('netmask',ctypes.c_void_p),('broadcast',ctypes.c_void_p),('data',ctypes.c_void_p)]
    libc=ctypes.CDLL(None,use_errno=True);head=ctypes.POINTER(Address)()
    if libc.getifaddrs(ctypes.byref(head))!=0:raise OSError('Cannot observe local interface addresses.')
    result=set();current=head
    try:
        for _ in range(16384):
            if not current:return result
            pointer=current.contents.address
            if pointer:
                family=ctypes.c_ushort.from_address(pointer).value
                if family in (socket.AF_INET,socket.AF_INET6):
                    offset,length=(4,4) if family==socket.AF_INET else (8,16)
                    result.add(ipaddress.ip_address(socket.inet_ntop(family,ctypes.string_at(pointer+offset,length))))
            current=current.contents.next
        raise OSError('Too many local interface addresses.')
    finally:libc.freeifaddrs(head)


def public_address(value,local):
    ip=ipaddress.ip_address(value)
    if ip.version==6 and ip.ipv4_mapped:ip=ip.ipv4_mapped
    if not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_unspecified or ip in local:return False
    if ip.version==6 and any(ip in ipaddress.ip_network(prefix) for prefix in ('64:ff9b::/96','64:ff9b:1::/48','2001::/32','2002::/16')):return False
    return True


class Proxy:
    def __init__(self,path,uid,authorized):
        self.path,self.uid,self.authorized=path,uid,authorized
        self.server=None;self.active=set();self.stopped=False

    async def start(self):
        self.server=await asyncio.start_unix_server(self.connection,path=str(self.path),limit=65537)
        self.path.chmod(0o600)

    async def destination(self,host,port):
        if port not in (80,443) or not host or len(host)>253 or any(c in host for c in ('%','/','\\','@','\0')):
            raise ValueError('Only public HTTP/HTTPS destinations are allowed.')
        records=await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host,port,type=socket.SOCK_STREAM),10)
        local=host_addresses()
        if not records or len(records)>64 or any(not public_address(row[4][0],local) for row in records):
            raise ValueError('Host, private and special network destinations are unavailable.')
        # Connect to the checked numeric address, never resolve the name twice.
        for family,_,_,_,address in records:
            try:return await asyncio.wait_for(asyncio.open_connection(address[0],port,family=family,flags=socket.AI_NUMERICHOST),15)
            except OSError:continue
        raise OSError('The checked public destination is unavailable.')

    async def connection(self,reader,writer):
        task=asyncio.current_task();self.active.add(task);upstream=None
        try:
            if self.stopped or len(self.active)>32:raise ValueError('This run has no active skill web grant.')
            _,uid,_=struct.unpack('3i',writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if uid!=self.uid:raise ValueError('Invalid private proxy peer.')
            raw=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),15)
            if len(raw)>65536:raise ValueError('HTTP headers exceed their complete limit.')
            if not self.authorized():raise ValueError('This run has no active skill web grant.')
            lines=raw[:-4].split(b'\r\n');method,target,version=lines[0].decode('ascii').split(' ')
            if not method.isascii() or not method.isalpha() or method!=method.upper() or version not in ('HTTP/1.0','HTTP/1.1'):
                raise ValueError('Invalid HTTP request line.')
            if method=='CONNECT':
                url=urlsplit('https://'+target)
                if url.path or url.query or url.fragment or url.username or url.password:raise ValueError('Invalid CONNECT destination.')
                host,port=url.hostname,url.port or 443
            else:
                url=urlsplit(target)
                if url.scheme!='http' or url.username or url.password or url.fragment:raise ValueError('Invalid public HTTP proxy URL.')
                host,port=url.hostname,url.port or 80
            if not self.authorized():raise ValueError('The original web grant ended during admission.')
            remote,upstream=await self.destination(host,port)
            if not self.authorized():raise ValueError('The original web grant ended during connection.')
            if method=='CONNECT':writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            else:
                headers=[]
                for line in lines[1:]:
                    name,sep,value=line.partition(b':')
                    if not sep or not name or any(c<=32 or c>=127 or c in b'()<>@,;:\\"/[]?={}' for c in name):raise ValueError('Invalid HTTP header.')
                    if any(c<32 and c!=9 or c==127 for c in value):raise ValueError('Invalid HTTP header value.')
                    if name.lower() not in (b'host',b'proxy-authorization',b'proxy-connection',b'connection',b'keep-alive'):
                        headers.append(name+b':'+value)
                authority=('['+host+']') if ':' in host else host
                if port!=80:authority+=':'+str(port)
                path=(url.path or '/')+('?' +url.query if url.query else '')
                upstream.write((method+' '+path+' '+version+'\r\n').encode('ascii')+
                    b'Host: '+authority.encode('ascii')+b'\r\nConnection: close\r\n'+b'\r\n'.join(headers)+b'\r\n\r\n')
                await upstream.drain()
            await writer.drain()
            async def pump(source,destination):
                while block:=await asyncio.wait_for(source.read(65536),300):
                    if self.stopped or not self.authorized():return
                    destination.write(block);await destination.drain()
                if destination.can_write_eof():destination.write_eof()
            copies=[asyncio.create_task(pump(reader,upstream)),asyncio.create_task(pump(remote,writer))]
            try:
                await asyncio.gather(*copies)
            finally:
                for copy in copies:copy.cancel()
                await asyncio.gather(*copies,return_exceptions=True)
        except (OSError,ValueError,TimeoutError,asyncio.IncompleteReadError,asyncio.LimitOverrunError):
            try:writer.write(b'HTTP/1.1 403 Skill web destination unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n');await writer.drain()
            except (OSError,ConnectionError):pass
        finally:
            for stream in (upstream,writer):
                if stream:
                    stream.close()
                    try:await stream.wait_closed()
                    except (OSError,ConnectionError):pass
            self.active.discard(task)

    async def revoke(self):
        tasks=list(self.active)
        for task in tasks:task.cancel()
        if tasks:await asyncio.gather(*tasks,return_exceptions=True)

    async def close(self):
        self.stopped=True
        if self.server:self.server.close();await self.server.wait_closed()
        await self.revoke()
        self.path.unlink(missing_ok=True)
