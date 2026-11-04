"""Public-address guards and actual scoped proxy streams without remote effects."""
import asyncio
import ipaddress
import os
from pathlib import Path
import tempfile
import unittest

from skill_egress import Proxy,public_address,host_addresses


class PublicAddresses(unittest.TestCase):
    def test_private_host_transition_and_mapped_addresses_are_denied(self):
        local={ipaddress.ip_address('93.184.216.34')}
        for value in ('127.0.0.1','10.0.0.2','172.16.1.1','192.168.1.1','100.64.0.1','169.254.169.254','0.0.0.0',
                      '224.0.0.1','::1','fc00::1','fe80::1','ff02::1','::ffff:10.0.0.2','64:ff9b::a00:2','2002:0a00:0002::','93.184.216.34'):
            self.assertFalse(public_address(value,local),value)
        self.assertTrue(public_address('8.8.8.8',local));self.assertTrue(public_address('2606:4700:4700::1111',local))
        self.assertIn(ipaddress.ip_address('127.0.0.1'),host_addresses())


class ProxyStreams(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.enabled=True
        self.received=[]
        async def target(reader,writer):
            raw=await reader.readuntil(b'\r\n\r\n');self.received.append(raw)
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 16\r\nConnection: close\r\n\r\nowned-proxy-body');await writer.drain();writer.close();await writer.wait_closed()
        self.target=await asyncio.start_server(target,'127.0.0.1',0);port=self.target.sockets[0].getsockname()[1]
        class OwnedTarget(Proxy):
            async def destination(self,host,requested_port):
                if host=='own-public.example' and requested_port==80:return await asyncio.open_connection('127.0.0.1',port)
                return await super().destination(host,requested_port)
        self.proxy=OwnedTarget(self.root/'p.sock',os.getuid(),lambda:self.enabled);await self.proxy.start()

    async def asyncTearDown(self):
        await self.proxy.close();self.target.close();await self.target.wait_closed();self.temp.cleanup()

    async def request(self,value):
        reader,writer=await asyncio.open_unix_connection(str(self.proxy.path));writer.write(value);await writer.drain()
        result=await asyncio.wait_for(reader.read(),5);writer.close();await writer.wait_closed();return result

    async def test_forwarding_rewrites_authority_and_excludes_proxy_credentials(self):
        value=await self.request(b'GET http://own-public.example/path?x=1 HTTP/1.1\r\nHost: untrusted.invalid\r\nProxy-Authorization: own-test-secret\r\n\r\n')
        self.assertIn(b'owned-proxy-body',value);self.assertEqual(len(self.received),1)
        self.assertIn(b'GET /path?x=1 HTTP/1.1',self.received[0]);self.assertIn(b'Host: own-public.example',self.received[0]);self.assertNotIn(b'own-test-secret',self.received[0])

    async def test_private_destinations_and_revoked_run_cannot_connect(self):
        for value in (b'CONNECT 127.0.0.1:443 HTTP/1.1\r\n\r\n',b'GET http://169.254.169.254/ HTTP/1.1\r\n\r\n',b'CONNECT own-public.example:5010 HTTP/1.1\r\n\r\n'):
            self.assertIn(b'403',await self.request(value))
        self.enabled=False
        self.assertIn(b'403',await self.request(b'GET http://own-public.example/ HTTP/1.1\r\n\r\n'))
        self.assertEqual(self.received,[])


if __name__=='__main__':unittest.main()
