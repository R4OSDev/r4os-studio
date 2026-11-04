"""One credential-free MCP controller per frozen session analysis namespace."""
import asyncio
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import struct
import sys

from skill_mcp_client import Client, McpFault, atomic, directory, encoded, strict
from skill_session_state import identity, original, paths, registry, birth, RIGHTS

MAX_REPLY=34*1024*1024


class Service:
    def __init__(self,config,launch):
        self.config,self.launch=config,launch
        self.client=None;self.grant=None;self.lock=asyncio.Lock();self.stopped=asyncio.Event();self.proxy=None
        self.connections=set();self.finished=None;self.finish_task=None;self.namespace_permissions=None
        self.state=paths(config['projects'],launch)[3]

    def snapshot(self):
        return dict(serviceId=self.launch['serviceId'],capabilities=self.client.capabilities if self.client else {},
                    receipts=self.pending(),grant=self.grant,
                    process=self.client.owner if self.client else None)

    def pending(self):
        return {key:{k:value.get(k) for k in ('method','phase','providerEndConfirmed')} for key,value in self.client.receipts.items()
                if value['phase'] not in ('complete','late_result')} if self.client else {}

    async def start(self,worker):
        if self.client:return
        if self.stopped.is_set():raise McpFault('The original analysis service is closing.')
        import skill_runtime
        root,manifest,_=await asyncio.to_thread(skill_runtime.load,worker,worker.entry,True)
        if self.stopped.is_set():raise McpFault('The original run stopped during runtime verification; no MCP process was started.')
        directory(self.state/'Data')
        client=Client(self.state/'Transport',dict(self.launch,servicePid=os.getpid(),serviceBirth=birth(os.getpid())))
        self.client=client
        self.namespace_permissions={key:worker.config['permissions'].get(key) is True for key in RIGHTS}
        try:
            if worker.config['permissions'].get('studio.skill_network'):
                from skill_egress import Proxy
                runtime=Path(self.config.get('runtimeDirectory','/run/r4os-studio-skill-mcp/'+self.launch['serviceId']))
                socket_path=directory(runtime)/'web.sock'
                self.proxy=Proxy(socket_path,self.config['uid'],lambda:bool(self.grant) and not self.stopped.is_set())
                await self.proxy.start()
            await client.start(skill_runtime.namespace(worker,root,manifest,self.state,self.proxy.path if self.proxy else None),env={'LANG':'C.UTF-8'})
            tools=await client.discover()
            if hashlib.sha256(encoded(tools)).hexdigest()!=worker.entry['mcp']['toolsHash']:
                raise McpFault('The actual session MCP catalogue differs from its frozen contracts.')
        except BaseException:
            await self.finish();raise

    async def finish(self,reason='controller_closed'):
        if self.finish_task is None:
            async def once():
                self.stopped.set();self.grant=None
                self.finished=await self.client.close() if self.client else dict(processEndConfirmed=True,neverStarted=True)
                if self.proxy:await self.proxy.close()
                atomic(self.state/'ServiceEnd.json',encoded(dict(self.launch,reason=reason,**self.finished)))
                return self.finished
            self.finish_task=asyncio.create_task(once())
        return await asyncio.shield(self.finish_task)

    async def handle(self,request,peer):
        if not isinstance(request,dict) or set(request)-{'operation','runId','name','arguments','method','key','requestId','timeout','retain'}:
            raise McpFault('Invalid analysis service request.')
        op=request.get('operation');effects=op not in ('close','release','observe')
        worker=original(self.config['projects'],self.launch,request.get('runId'),peer,self.config['uid'],effects)
        try:
            if op=='close':
                if self.grant and self.grant['runId']!=worker.run_id:
                    return dict(grantClosed=True,ownershipTransferred=True,processEndConfirmed=False)
                return await self.finish()
            if op=='release':
                if self.grant and self.grant['runId']!=worker.run_id:raise McpFault('Another original run owns the current grant.')
                unresolved=self.client and [k for k,v in self.client.receipts.items() if v['phase'] not in ('complete','late_result')]
                if self.lock.locked() or unresolved:raise McpFault('Original analysis effects remain unconfirmed; the session cannot be retained as idle.')
                self.grant=None
                if self.proxy:await self.proxy.revoke()
                value=dict(sessionRetained=True,grantClosed=True,serviceId=self.launch['serviceId'],processEndConfirmed=False)
                atomic(self.state/('Release-'+worker.run_id+'.json'),encoded(value));return value
            if op=='observe':
                if not self.client:raise McpFault('No original analysis process was started.')
                return self.client.observe(identity(request.get('requestId')))
            if self.stopped.is_set():raise McpFault('The original analysis service has ended; read its retained state before starting another.')
            if (self.state/('Release-'+worker.run_id+'.json')).exists():
                raise McpFault('This original run closed its analysis grant. A new accepted run is required to resume the session state.')
            async with self.lock:
                if self.grant and self.grant['runId']!=worker.run_id:
                    raise McpFault('A previous Studio run still owns the analysis grant.')
                self.grant=dict(runId=worker.run_id,pid=peer[0],birth=birth(peer[0]))
                await self.start(worker)
                if op=='acquire':return self.snapshot()
                for request_id,receipt in self.client.receipts.items():
                    if receipt['method']=='tools/call' and receipt['phase'] in ('unknown','cancel_requested'):
                        raise McpFault('An original analysis effect remains unconfirmed. Observe its original receipt before another effect.',request_id,receipt)
                permission='studio.skill_discover' if op=='listing' else 'studio.skill_call'
                if not worker.config['permissions'].get(permission):raise McpFault('This analysis operation is disabled in its original accepted run.')
                timeout=request.get('timeout',120)
                if type(timeout) not in (int,float) or not 1<=timeout<=3600:raise McpFault('Invalid analysis deadline.')
                rid=identity(request.get('requestId')) if op in ('call','request') else None
                if op=='call':result=await self.client.call(request.get('name'),request.get('arguments'),request_id=rid,timeout=timeout)
                elif op=='request':
                    method=request.get('method');parameters=request.get('arguments')
                    required={'prompts/get':'prompts','resources/read':'resources','completion/complete':'completions'}.get(method)
                    if required is None or required not in self.client.capabilities:raise McpFault('The native server does not advertise that protocol operation.')
                    result=await self.client.request(method,parameters,timeout=timeout,request_id=rid)
                elif op=='listing':
                    allowed={'resources/list':'resources','resources/templates/list':'resourceTemplates'}
                    if allowed.get(request.get('method'))!=request.get('key') or 'resources' not in self.client.capabilities:
                        raise McpFault('Invalid native analysis catalogue operation.')
                    result=await self.client.listing(request['method'],request['key'])
                else:raise McpFault('Unknown analysis service operation.')
                return dict(value=result,receipts=self.pending())
        finally:worker.store.db.close()

    async def connection(self,reader,writer):
        task=asyncio.current_task();self.connections.add(task)
        try:
            if len(self.connections)>8:raise McpFault('This analysis service already has eight connected requests.')
            peer=struct.unpack('3i',writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            raw=await asyncio.wait_for(reader.readline(),10)
            if not raw.endswith(b'\n') or len(raw)>131072:raise McpFault('The analysis request exceeds its complete frame limit.')
            value=await self.handle(strict(raw),peer)
            response=encoded(dict(result=value))
            if len(response)>MAX_REPLY:raise McpFault('The complete analysis response exceeds the service frame limit; its native result remains retained.')
            writer.write(response+b'\n')
        except McpFault as error:
            writer.write(encoded(dict(error=str(error),requestId=error.request_id,state=error.state))+b'\n')
        except Exception:
            writer.write(b'{"error":"The original analysis service is unavailable. Observe its original state before another request."}\n')
        finally:
            try:await writer.drain()
            except (OSError,ConnectionError):pass
            writer.close()
            try:await writer.wait_closed()
            except (OSError,ConnectionError):pass
            self.connections.discard(task)

    async def watch(self):
        while not self.stopped.is_set():
            try:
                if self.grant:
                    grant=self.grant
                    try:
                        worker=original(self.config['projects'],self.launch,grant['runId'],(grant['pid'],self.config['uid'],0),self.config['uid'])
                        worker.store.db.close()
                    except Exception:
                        self.grant=None
                        if self.client is None or not self.client.tools or any(v['phase'] not in ('complete','late_result') for v in self.client.receipts.values()):
                            await self.finish('original_worker_lost')
                        elif self.proxy:await self.proxy.revoke()
                # A deleted session or revoked idle permission must close the
                # namespace even when the following run never invokes REA.
                if not self.grant:
                    import sqlite3
                    from session_lifetime import state as retired
                    from skill_preferences import read
                    from skill_lifecycle import api as package_lifecycle
                    from owner import skills_root
                    if package_lifecycle.deleted(skills_root(self.config['projects']),self.launch['skillId']):
                        await self.finish('skill_deleted');return
                    _,sessions,database,_=paths(self.config['projects'],self.launch)
                    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as db:
                        row=db.execute('SELECT settings FROM sessions WHERE id=?',(self.launch['sessionId'],)).fetchone()
                        if row is None or retired(db,self.launch['sessionId']):await self.finish('session_retired');return
                        settings=json.loads(row[0])
                    if read(self.config['projects'],self.launch['ownerType'],self.launch['ownerId'],self.launch['sessionId']).get(self.launch['skillId']) is False:
                        await self.finish('skill_disabled');return
                    if any(settings.get('permissions',{}).get(k) is False for k in ('studio.exec_command','studio.read_file')):
                        await self.finish('permissions_revoked');return
                    if self.namespace_permissions:
                        import types
                        from tool_defaults import effective
                        store=types.SimpleNamespace(projects=Path(self.config['projects']),owner_type=self.launch['ownerType'],
                            owner_id=self.launch['ownerId'],selected_profile=self.launch['ownerType'])
                        current=effective(store,settings.get('permissions',{}))
                        if any((current.get(key) is True)!=self.namespace_permissions[key] for key in RIGHTS):
                            await self.finish('permissions_changed');return
            except Exception as error:
                try:atomic(self.state/'ObservationFailure.json',encoded(dict(kind=type(error).__name__,message=str(error)[:1000])))
                except OSError:pass
                await self.finish('owner_observation_lost');return
            try:await asyncio.wait_for(self.stopped.wait(),1)
            except TimeoutError:pass


async def main(ident):
    config=json.loads(Path('/etc/r4os-studio-agents/config.json').read_text())
    if os.getuid()!=config['uid']:raise RuntimeError('Use the configured private analysis owner.')
    from skill_runtime import runtime_spec
    launch=strict(runtime_spec.read(registry(config['projects'],ident)/'Launch.json',131072))
    if launch.get('schema')!=1 or launch.get('serviceId')!=ident:raise RuntimeError('Invalid analysis service registry.')
    service=Service(config,launch);loop=asyncio.get_running_loop()
    atomic(service.state/'ServiceProcess.json',encoded(dict(launch,pid=os.getpid(),birth=birth(os.getpid()),
        release=str(Path(__file__).resolve().parents[2]),invocationId=os.environ.get('STUDIO_MCP_INVOCATION',''))))
    for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,lambda:asyncio.create_task(service.finish()))
    socket_path=directory(Path('/run/r4os-studio-skill-mcp')/ident)/'host.sock'
    if socket_path.exists():raise RuntimeError('The original analysis socket still exists; reconcile its original service.')
    server=await asyncio.start_unix_server(service.connection,path=str(socket_path),limit=131073);socket_path.chmod(0o600)
    monitor=asyncio.create_task(service.watch())
    try:
        async with server:await service.stopped.wait()
    finally:
        await service.finish();monitor.cancel();await asyncio.gather(monitor,return_exceptions=True)
        if service.connections:await asyncio.gather(*service.connections,return_exceptions=True)
        socket_path.unlink(missing_ok=True)


if __name__=='__main__':asyncio.run(main(identity(sys.argv[1])))
