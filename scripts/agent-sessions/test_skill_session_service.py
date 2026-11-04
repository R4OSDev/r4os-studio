"""Real native processes, Unix peers and SQLite run grants; no model inference."""
import asyncio
import json
import os
import sqlite3
import types
import unittest
import uuid
from unittest.mock import patch

from test_skill_mcp_tools import ManagedBroker
from skill_session_state import birth,launch_record
from skill_mcp_service import Service
from skill_session_client import SessionClient
from skill_mcp_client import McpFault


class NativeSessionServices(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await ManagedBroker.asyncSetUp(self)
        self.services=[];self.servers=[];self.monitors=[]
        self.database=self.worker.store.directory/'Sessions.sqlite';self.database.parent.mkdir(parents=True)
        self.session_db=sqlite3.connect(self.database)
        self.session_db.executescript('CREATE TABLE sessions(id TEXT PRIMARY KEY,project_id TEXT,settings TEXT);CREATE TABLE runs(id TEXT PRIMARY KEY,session_id TEXT,state TEXT,busy INTEGER,config TEXT,worker TEXT);')
        self.session_db.execute('INSERT INTO sessions VALUES(?,?,?)',(self.session,self.owner,'{}'))
        self.run_row(self.worker)
        self.remote,self.service=await self.server(self.worker)

    def run_row(self,worker):
        self.session_db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)',(worker.run_id,worker.session_id,'running',1,
            json.dumps(worker.config),json.dumps(dict(pid=os.getpid(),birth=birth(os.getpid()),release='explicit-owned-test-controller'))));self.session_db.commit()

    async def server(self,worker):
        launch=launch_record(worker,self.entry,str(uuid.uuid4()))
        service=Service(dict(projects=str(self.projects),uid=os.getuid(),runtimeDirectory=str(self.base)),launch)
        address='\0studio-mcp-owned-test-'+str(uuid.uuid4())
        server=await asyncio.start_unix_server(service.connection,path=address,limit=131073)
        self.services.append(service);self.servers.append(server)
        remote=SessionClient(worker,launch);remote.socket=address
        await remote.acquire()
        return remote,service

    async def asyncTearDown(self):
        for service in self.services:await service.finish()
        for server in self.servers:server.close();await server.wait_closed()
        for task in self.monitors:task.cancel()
        await asyncio.gather(*self.monitors,return_exceptions=True)
        self.session_db.close()
        await ManagedBroker.asyncTearDown(self)

    async def test_same_native_process_and_state_survive_a_new_original_run(self):
        first=await self.remote.call('echo',{'value':'first'},request_id=str(uuid.uuid4()))
        release=await self.remote.release(True)
        self.assertTrue(release['sessionRetained']);self.assertFalse(release['processEndConfirmed'])
        old_worker=types.SimpleNamespace(**vars(self.worker));old=SessionClient(old_worker,self.service.launch);old.socket=self.remote.socket
        self.session_db.execute('UPDATE runs SET busy=0,state=? WHERE id=?',('completed',self.worker.run_id));self.session_db.commit()
        self.worker.run_id=str(uuid.uuid4());self.run_row(self.worker)
        resumed=SessionClient(self.worker,self.service.launch);resumed.socket=self.remote.socket;await resumed.acquire()
        late_stop=await old.close();self.assertTrue(late_stop['ownershipTransferred']);self.assertFalse(late_stop['processEndConfirmed'])
        second=await resumed.call('echo',{'value':'second'},request_id=str(uuid.uuid4()))
        a,b=first['structuredContent'],second['structuredContent']
        self.assertEqual(a['nativePid'],b['nativePid']);self.assertEqual((a['nativeCounter'],b['nativeCounter']),(1,2))
        end=await resumed.close();self.assertTrue(end['processEndConfirmed']);self.assertEqual(end['exit'],0)

    async def test_retained_session_parks_its_own_native_unit(self):
        actions=[]
        async def ctl(*args):
            actions.append(args)
            return 'frozen\n' if args[0]=='show' else ''
        self.remote.unit='r4os-studio-skill-mcp@'+self.service.launch['serviceId']+'.service'
        with patch('skill_session_client.systemctl',side_effect=ctl):
            result=await self.remote.release(True)
        self.assertTrue(result['executionSuspended'])
        self.assertEqual([a[0] for a in actions],['freeze','show'])
        self.assertTrue(all(a[1]==self.remote.unit for a in actions))

    async def test_failed_parking_stops_only_the_own_unit(self):
        actions=[]
        async def ctl(*args):
            actions.append(args)
            if args[0]=='freeze':raise McpFault('explicit failed freezer')
            return ''
        self.remote.unit='r4os-studio-skill-mcp@'+self.service.launch['serviceId']+'.service'
        with patch('skill_session_client.systemctl',side_effect=ctl):
            with self.assertRaises(McpFault):await self.remote.release(True)
        self.assertEqual([a[0] for a in actions],['freeze','stop'])
        self.assertTrue(all(a[1]==self.remote.unit for a in actions))

    async def test_late_original_receipt_is_read_without_another_native_call(self):
        from skill_mcp_tools import SkillTools
        rid=str(uuid.uuid4())
        with self.assertRaises(McpFault):await self.remote.call('echo',{'delay_ms':1350},request_id=rid,timeout=1)
        broker=SkillTools(self.worker)
        before=json.loads(broker.observe_original(self.entry,rid,0)['output'])['payload']
        self.assertFalse(before['providerEndConfirmed'])
        await asyncio.sleep(.6)
        after=json.loads(broker.observe_original(self.entry,rid,0)['output'])['payload']
        self.assertTrue(after['providerEndConfirmed']);self.assertEqual(after['phase'],'late_result')
        self.assertEqual(after['response']['result']['structuredContent']['nativeCounter'],1)
        self.assertEqual(len([v for v in self.service.client.receipts.values() if v['method']=='tools/call']),1)

    async def test_confirmed_own_retirement_forgets_only_exact_registry_without_resurrection(self):
        import shutil
        from skill_mcp_client import atomic,encoded,directory
        from skill_session_state import registry,paths
        from skill_mcp_lifecycle import stop_owned,forget
        launch=self.service.launch;folder=directory(registry(self.projects,launch['serviceId']))
        atomic(folder/'Launch.json',encoded(launch))
        foreign=dict(launch,serviceId=str(uuid.uuid4()),sessionId=str(uuid.uuid4()))
        other=directory(registry(self.projects,foreign['serviceId']));atomic(other/'Launch.json',encoded(foreign))
        actions=[]
        async def ctl(*args):
            actions.append(args)
            if args[0]=='stop':await self.service.finish()
            return 'MainPID=0\nActiveState=inactive\n'
        with patch('skill_session_client.systemctl',side_effect=ctl):
            selected=await stop_owned(self.projects,ownerType=self.worker.store.owner_type,
                ownerId=self.worker.store.owner_id,sessionId=self.session)
        self.assertTrue(self.service.finished['processEndConfirmed']);self.assertEqual(self.service.finished['exit'],0)
        self.assertTrue(all(args[1]=='r4os-studio-skill-mcp@'+launch['serviceId']+'.service' for args in actions))
        forget(self.projects,selected);self.assertFalse(folder.exists());self.assertTrue(other.exists())
        shutil.rmtree(self.service.state)
        self.assertEqual(paths(self.projects,launch)[3],self.service.state)
        self.assertFalse(self.service.state.exists())

    async def test_two_sessions_have_independent_process_state_and_results(self):
        sid=str(uuid.uuid4());run=str(uuid.uuid4());self.session_db.execute('INSERT INTO sessions VALUES(?,?,?)',(sid,self.owner,'{}'))
        worker=types.SimpleNamespace(**vars(self.worker));worker.session_id=sid;worker.run_id=run;self.run_row(worker)
        other,service=await self.server(worker)
        first=await self.remote.call('echo',{},request_id=str(uuid.uuid4()));second=await other.call('echo',{},request_id=str(uuid.uuid4()))
        self.assertNotEqual(self.service.client.owner['pid'],service.client.owner['pid'])
        self.assertEqual(first['structuredContent']['nativeCounter'],1);self.assertEqual(second['structuredContent']['nativeCounter'],1)
        self.assertNotEqual(self.service.state,service.state)

    async def test_wrong_peer_run_and_frozen_namespace_are_rejected(self):
        with self.assertRaises(McpFault):await self.service.handle(dict(operation='acquire',runId=self.worker.run_id),(os.getpid()+100000,os.getuid(),0))
        self.worker.run_id=str(uuid.uuid4())
        with self.assertRaises(McpFault):await self.remote.acquire()
        self.worker.run_id=self.run
        changed=dict(self.worker.config);changed['permissions']=dict(changed['permissions'],**{'studio.write_file':False})
        self.session_db.execute('UPDATE runs SET config=? WHERE id=?',(json.dumps(changed),self.run));self.session_db.commit()
        with self.assertRaises(McpFault):await self.remote.call('echo',{},request_id=str(uuid.uuid4()))
        self.assertEqual(len([r for r in self.service.client.receipts.values() if r['method']=='tools/call']),0)

    async def test_idle_permission_revocation_closes_the_native_namespace(self):
        await self.remote.release(True)
        self.session_db.execute('UPDATE runs SET busy=0,state=? WHERE id=?',('completed',self.run))
        self.session_db.execute('UPDATE sessions SET settings=? WHERE id=?',(json.dumps({'permissions':{'studio.write_file':False}}),self.session));self.session_db.commit()
        monitor=asyncio.create_task(self.service.watch());self.monitors.append(monitor)
        await asyncio.wait_for(self.service.stopped.wait(),5);await self.service.finish()
        self.assertTrue(self.service.finished['processEndConfirmed'])
        diagnostic=self.service.state/'ObservationFailure.json'
        self.assertEqual(json.loads((self.service.state/'ServiceEnd.json').read_bytes())['reason'],'permissions_changed',
                         diagnostic.read_text() if diagnostic.exists() else '')

    async def test_stop_keeps_an_unconfirmed_original_without_replaying_it(self):
        rid=str(uuid.uuid4());pending=asyncio.create_task(self.remote.call('echo',{'delay_ms':30000},request_id=rid,timeout=60))
        for _ in range(100):
            if rid in self.service.client.receipts:break
            await asyncio.sleep(.01)
        end=await self.service.finish()
        self.assertTrue(end['processEndConfirmed']);self.assertIn(rid,end['unresolved'])
        with self.assertRaises(McpFault):await pending
        with self.assertRaises(McpFault):await self.remote.acquire()
        self.assertEqual(sum(r['method']=='tools/call' for r in self.service.client.receipts.values()),1)

    async def test_os_file_network_and_capability_boundaries(self):
        foreign=self.base/'private-provider-canary.txt';foreign.write_text('own-secret-canary')
        (self.worker.store.workspace/'escape').symlink_to(foreign)
        result=await self.remote.call('echo',{'probe':{'read':[str(foreign),'/workspace/escape'],
            'write':['/runtime/catalog.json','/workspace/allowed-output.txt','/session/allowed-evidence.txt']}},request_id=str(uuid.uuid4()))
        probe=result['structuredContent']['probe']
        self.assertIn('error',probe[str(foreign)]);self.assertIn('error',probe['/workspace/escape'])
        self.assertEqual(probe['/runtime/catalog.json']['error'],'EROFS')
        self.assertTrue(probe['/workspace/allowed-output.txt']['written']);self.assertTrue(probe['/session/allowed-evidence.txt']['written'])
        self.assertNotEqual(probe['hostConnection'],'connected');self.assertEqual(probe['loopback'],'private-loopback')
        for value in probe['capabilities']:
            if value.startswith('Cap'):self.assertEqual(int(value.split(':')[1],16),0)
        self.assertIn('NoNewPrivs:\t1',probe['capabilities'])
        await self.remote.release(True)
        worker=types.SimpleNamespace(**vars(self.worker));worker.run_id=str(uuid.uuid4())
        worker.config=dict(worker.config,permissions=dict(worker.config['permissions'],**{'studio.write_file':False}));self.run_row(worker)
        readonly,_=await self.server(worker)
        denied=await readonly.call('echo',{'probe':{'write':['/workspace/forbidden-output.txt','/session/own-cache.txt']}},request_id=str(uuid.uuid4()))
        self.assertEqual(denied['structuredContent']['probe']['/workspace/forbidden-output.txt']['error'],'EROFS')
        self.assertTrue(denied['structuredContent']['probe']['/session/own-cache.txt']['written'])

    async def test_scoped_web_bridge_and_permanent_original_run_release(self):
        from skill_egress import Proxy
        async def page(reader,writer):
            await reader.readuntil(b'\r\n\r\n')
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 19\r\nConnection: close\r\n\r\nowned-namespace-web');await writer.drain();writer.close();await writer.wait_closed()
        target=await asyncio.start_server(page,'127.0.0.1',0);port=target.sockets[0].getsockname()[1]
        class OwnedPublic(Proxy):
            async def destination(proxy,host,requested_port):
                if host=='own-public.example' and requested_port==80:return await asyncio.open_connection('127.0.0.1',port)
                return await super().destination(host,requested_port)
        worker=types.SimpleNamespace(**vars(self.worker));worker.run_id=str(uuid.uuid4())
        worker.config=dict(worker.config,permissions=dict(worker.config['permissions'],**{'studio.skill_network':True}));self.run_row(worker)
        try:
            with patch('skill_egress.Proxy',OwnedPublic):remote,service=await self.server(worker)
            value=await remote.call('echo',{'probe':{'proxy_url':'http://own-public.example/'}},request_id=str(uuid.uuid4()))
            self.assertIn('owned-namespace-web',value['structuredContent']['probe']['webResponse'])
            denied=await remote.call('echo',{'probe':{'proxy_url':'http://127.0.0.1/'}},request_id=str(uuid.uuid4()))
            self.assertIn('403',denied['structuredContent']['probe']['webResponse'])
            await remote.release(True)
            with self.assertRaises(McpFault):await remote.acquire()
            self.assertEqual(len(service.proxy.active),0)
        finally:target.close();await target.wait_closed()


if __name__=='__main__':unittest.main()
