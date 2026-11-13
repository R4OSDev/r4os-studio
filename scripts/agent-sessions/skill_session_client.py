"""A Studio worker grant to an independent, original session MCP service."""
import asyncio
import fcntl
import os
from pathlib import Path
import uuid

from skill_mcp_client import McpFault, atomic, directory, encoded, strict
from skill_session_state import launch_record, registry, service_id, paths


class SessionClient:
    def __init__(self,worker,launch,unit=None):
        self.worker,self.launch=worker,launch
        self.unit=unit
        self.socket=Path('/run/r4os-studio-skill-mcp')/launch['serviceId']/'host.sock'
        self.capabilities={};self.receipts={};self.closed=None

    async def rpc(self,operation,**parameters):
        request=dict(operation=operation,runId=self.worker.run_id,**parameters)
        ident=parameters.get('requestId')
        writer=None
        try:
            reader,writer=await asyncio.wait_for(asyncio.open_unix_connection(str(self.socket),limit=34*1024*1024+1),10)
            writer.write(encoded(request)+b'\n');await writer.drain()
            raw=await asyncio.wait_for(reader.readline(),parameters.get('timeout',120)+30)
            if not raw.endswith(b'\n'):raise OSError('The original analysis service reply was lost.')
            value=strict(raw)
            if 'error' in value:
                error = McpFault(value['error'],value.get('requestId'),value.get('state'))
                error.request_not_sent = value.get('requestNotSent') is True
                raise error
            return value['result']
        except McpFault:raise
        except (OSError,ValueError,TimeoutError):
            raise McpFault('The original session analysis response is unavailable. It was not repeated.',ident,
                           dict(phase='unknown',providerEndConfirmed=False,serviceId=self.launch['serviceId'])) from None
        finally:
            if writer:
                writer.close()
                try:await writer.wait_closed()
                except (OSError,ConnectionError):pass

    async def acquire(self):
        value=await self.rpc('acquire');self.capabilities=value['capabilities'];self.receipts=value['receipts']
        return self

    async def call(self,name,arguments,request_id=None,timeout=120):
        value=await self.rpc('call',name=name,arguments=arguments,requestId=request_id or str(uuid.uuid4()),timeout=timeout)
        self.receipts=value['receipts'];return value['value']

    async def request(self,method,parameters,timeout=120,request_id=None):
        value=await self.rpc('request',method=method,arguments=parameters,requestId=request_id or str(uuid.uuid4()),timeout=timeout)
        self.receipts=value['receipts'];return value['value']

    async def listing(self,method,key):
        value=await self.rpc('listing',method=method,key=key)
        self.receipts=value['receipts'];return value['value']

    async def release(self,retain=False):
        if self.closed is None or not retain and self.closed.get('sessionRetained'):
            if self.unit and not retain:await ensure_thawed(self.unit)
            try:self.closed=await self.rpc('release' if retain else 'close')
            except McpFault:
                self.closed=self.observed_release(retain)
                if self.closed is None:raise
            if self.unit and retain and self.closed.get('sessionRetained'):
                try:
                    await systemctl('freeze',self.unit)
                    frozen=await systemctl('show',self.unit,'--property=FreezerState','--value')
                    if frozen.strip()!='frozen':raise McpFault('The native session did not confirm suspension.')
                    self.closed['executionSuspended']=True
                except BaseException:
                    # Never release the project lease while a supposedly idle
                    # native target can still execute in the background.
                    await stop_unit(self.unit)
                    confirmed=self.observed_release(False)
                    if confirmed:
                        self.closed=dict(confirmed,retentionFailed=True);return self.closed
                    raise McpFault('The analysis unit could not be parked. Its own unit was stopped; inspect its original end before resuming.') from None
        return self.closed

    def observed_release(self,retain):
        """A lost close response can only be resolved by its original receipt."""
        from skill_runtime import runtime_spec
        state=paths(self.worker.store.projects,self.launch)[3]
        end=state/'ServiceEnd.json'
        if end.exists():
            value=strict(runtime_spec.read(end))
            if (all(value.get(k)==v for k,v in self.launch.items())
                    and value.get('processEndConfirmed') and not value.get('unresolved')):return value
        release=state/('Release-'+self.worker.run_id+'.json')
        if retain and release.exists():
            value=strict(runtime_spec.read(release))
            if value.get('serviceId')==self.launch['serviceId'] and value.get('sessionRetained') and value.get('grantClosed'):return value
        return None

    async def close(self):return await self.release(False)


async def systemctl(*arguments):
    process=await asyncio.create_subprocess_exec('/usr/bin/systemctl',*arguments,stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
    output,error=await asyncio.wait_for(process.communicate(),30)
    if process.returncode:raise McpFault('The original managed analysis unit could not be observed or started.')
    return output.decode()


async def ensure_thawed(unit):
    import re
    if not re.fullmatch(r'r4os-studio-skill-mcp@[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}\.service',unit):
        raise McpFault('Invalid original managed analysis unit.')
    frozen=await systemctl('show',unit,'--property=FreezerState','--value')
    if frozen.strip() in ('frozen','freezing'):await systemctl('thaw',unit)


async def stop_unit(unit):
    # systemd257 rejects StopUnit while frozen. Thaw only this positively
    # attributed instance before waiting for its original stop.
    await ensure_thawed(unit)
    await systemctl('stop',unit)


async def retire_changed(worker,entry):
    wanted=launch_record(worker,entry,str(uuid.uuid4()))
    root=registry(worker.store.projects,wanted['serviceId']).parent
    if not root.exists():return
    from skill_session_state import identity
    for candidate in sorted(root.iterdir()):
        if candidate.name=='Bindings':continue
        identity(candidate.name)
        launch=strict((candidate/'Launch.json').read_bytes())
        if (launch.get('schema')!=1 or launch.get('serviceId')!=candidate.name):
            raise McpFault('An original analysis registry entry changed; preserve it for reconciliation.')
        if any(launch.get(k)!=wanted[k] for k in ('ownerType','ownerId','sessionId','skillId')):continue
        if launch['namespaceHash']==wanted['namespaceHash']:continue
        from skill_mcp_lifecycle import stop_controller
        from store import ProjectFault
        try:await stop_controller(worker.store.projects,launch)
        except ProjectFault as error:raise McpFault(str(error)) from None


async def start(worker,entry):
    projects=worker.store.projects
    await retire_changed(worker,entry)
    stable=service_id(worker.session_id,worker.config,entry)
    bindings=directory(registry(projects,stable).parent/'Bindings')
    lock=os.open(bindings/(stable+'.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    fresh=False
    try:
        fcntl.flock(lock,fcntl.LOCK_EX)
        index=bindings/(stable+'.json');binding=strict(index.read_bytes()) if index.exists() else None
        if binding:
            launch=strict((registry(projects,binding['serviceId'])/'Launch.json').read_bytes())
            end=paths(projects,launch)[3]/'ServiceEnd.json'
            if not end.exists():
                from skill_mcp_lifecycle import reconcile_end
                await reconcile_end(projects,launch)
            if end.exists():
                previous=strict(end.read_bytes())
                if (not previous.get('processEndConfirmed') or previous.get('unresolved')
                        or binding.get('lastRunId',binding['createdRunId'])==worker.run_id):
                    raise McpFault('The original analysis service ended or has unconfirmed effects. Its state was preserved; no replacement was started.')
                binding=None
        if binding is None:
            launch=launch_record(worker,entry,str(uuid.uuid4()));location=directory(registry(projects,launch['serviceId']))
            atomic(location/'Launch.json',encoded(launch))
            binding=dict(serviceId=launch['serviceId'],createdRunId=worker.run_id,lastRunId=worker.run_id)
            atomic(index,encoded(binding));fresh=True
        elif binding.get('lastRunId')!=worker.run_id:
            binding['lastRunId']=worker.run_id;atomic(index,encoded(binding))
    finally:os.close(lock)
    unit='r4os-studio-skill-mcp@'+launch['serviceId']+'.service'
    if fresh:
        # Only this newly persisted intent starts its unit. An existing original
        # intent is observed, including after a lost start reply.
        await systemctl('start','--no-block',unit)
    else:await systemctl('thaw',unit)
    client=SessionClient(worker,launch,unit)
    for _ in range(150):
        if client.socket.exists():return await client.acquire()
        state=await systemctl('show',unit,'--property=ActiveState','--property=MainPID','--property=Result')
        if 'ActiveState=failed' in state or 'ActiveState=inactive' in state:
            raise McpFault('The original session analysis unit is not running. Read its original end before another preparation.')
        await asyncio.sleep(0.2)
    raise McpFault('The original analysis service has not confirmed its socket. Its start intent was retained without replacement.')
