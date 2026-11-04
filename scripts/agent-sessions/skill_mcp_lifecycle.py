"""Exact original analysis instances participate in confirmed owner deletion."""
from pathlib import Path
import shutil

from owner import skills_root
from skill_mcp_client import strict,atomic,encoded
from skill_session_state import identity, paths,birth
from store import ProjectFault


def instances(projects,**scope):
    root=skills_root(projects)/'.mcp'
    if not root.exists():return []
    if root.resolve(strict=True)!=root:raise ProjectFault('Analysis registry is linked.',503)
    result=[]
    for folder in sorted(root.iterdir()):
        if folder.name=='Bindings':continue
        identity(folder.name)
        file=folder/'Launch.json'
        if file.resolve(strict=True)!=file:raise ProjectFault('Original analysis identity is linked.',503)
        launch=strict(file.read_bytes())
        if launch.get('schema')!=1 or launch.get('serviceId')!=folder.name:
            raise ProjectFault('Original analysis registry needs reconciliation.',503)
        if any(launch.get(key)!=value for key,value in scope.items()):continue
        result.append((folder,launch))
    return result


def pending(state):
    end=state/'ServiceEnd.json'
    if end.exists():
        value=strict(end.read_bytes())
        if not value.get('processEndConfirmed') or value.get('unresolved'):
            return 'An original analysis effect is unconfirmed. Preserve and reconcile its receipt first.'
    for file in (state/'Transport/Calls').glob('*.json'):
        if file.name.endswith(('.response.json','.owner.json')):continue
        value=strict(file.read_bytes())
        if value.get('phase') not in ('complete','late_result'):
            return 'An original analysis call is active or unconfirmed. Finish or reconcile it first.'
    return None


async def stop_run(worker):
    """Stop only launch intents still attributed to this original worker run."""
    from skill_session_client import stop_unit
    root=skills_root(worker.store.projects)/'.mcp'
    for file in (root/'Bindings').glob('*.json'):
        value=strict(file.read_bytes())
        if value.get('lastRunId',value.get('createdRunId'))!=worker.run_id:continue
        launch=strict((root/identity(value['serviceId'])/'Launch.json').read_bytes())
        if any(launch.get(k)!=v for k,v in dict(ownerType=worker.store.owner_type,
                ownerId=worker.store.owner_id,sessionId=worker.session_id).items()):
            raise ProjectFault('The original analysis launch intent changed owner.',503)
        await stop_unit('r4os-studio-skill-mcp@'+launch['serviceId']+'.service')


def blockers(projects,**scope):
    result=[]
    for _,launch in instances(projects,**scope):
        reason=pending(paths(projects,launch)[3])
        if reason:result.append(reason)
    return result


async def reconcile_end(projects,launch):
    """Confirm the ended original unit, never invent a missing analysis reply."""
    from skill_session_client import systemctl
    state=paths(projects,launch)[3];end=state/'ServiceEnd.json'
    if end.exists():return strict(end.read_bytes())
    unit='r4os-studio-skill-mcp@'+identity(launch['serviceId'])+'.service'
    raw=await systemctl('show',unit,'--property=ActiveState','--property=MainPID',
        '--property=InvocationID','--property=ExecMainCode','--property=ExecMainStatus')
    observed=dict(line.split('=',1) for line in raw.splitlines() if '=' in line)
    if observed.get('MainPID')!='0' or observed.get('ActiveState') not in ('inactive','failed'):return None
    process=state/'ServiceProcess.json'
    if not process.exists():return None
    original=strict(process.read_bytes())
    if (original.get('serviceId')!=launch['serviceId'] or birth(original.get('pid'))==original.get('birth')
            or observed.get('InvocationID') not in ('',original.get('invocationId'))):return None
    native_file=state/'Transport/process.json'
    native=strict(native_file.read_bytes()) if native_file.exists() else None
    if native and native.get('pid') and birth(native['pid'])==native.get('birth'):return None
    unresolved=[]
    for file in (state/'Transport/Calls').glob('*.json'):
        if file.name.endswith(('.response.json','.owner.json')):continue
        receipt=strict(file.read_bytes())
        if receipt['phase'] not in ('complete','late_result'):unresolved.append(receipt['requestId'])
    result=dict(launch,processEndConfirmed=True,outcome='unknown',reason='original_unit_ended_without_controller_receipt',
        reconciled=True,replayed=False,nativeReplyReconstructed=False,unresolved=unresolved,unitState=observed)
    atomic(end,encoded(result));return result


async def stop_owned(projects,**scope):
    from skill_session_client import systemctl,stop_unit
    selected=instances(projects,**scope)
    for _,launch in selected:
        state=paths(projects,launch)[3]
        reason=pending(state)
        if reason:raise ProjectFault(reason,409)
        unit='r4os-studio-skill-mcp@'+launch['serviceId']+'.service'
        end=state/'ServiceEnd.json'
        if not end.exists():await stop_unit(unit)
        if not end.exists():await reconcile_end(projects,launch)
        observed=await systemctl('show',unit,'--property=MainPID','--property=ActiveState')
        if 'MainPID=0' not in observed or not end.exists():
            raise ProjectFault('The original analysis process end is unconfirmed. Its data was preserved.',409)
        reason=pending(state)
        if reason:raise ProjectFault(reason,409)
    return selected


def forget(projects,selected):
    """Only after the caller has confirmed ends and admitted owner retirement."""
    root=skills_root(projects)/'.mcp';retired={launch['serviceId'] for _,launch in selected}
    for file in (root/'Bindings').glob('*.json'):
        if file.resolve(strict=True)!=file:raise ProjectFault('Analysis binding is linked.',503)
        if strict(file.read_bytes()).get('serviceId') in retired:
            lock=file.with_suffix('.lock')
            if lock.is_symlink():raise ProjectFault('Analysis lifetime lock is linked.',503)
            file.unlink();lock.unlink(missing_ok=True)
    for folder,launch in selected:
        if folder!=root/launch['serviceId'] or folder.resolve(strict=True)!=folder:
            raise ProjectFault('Analysis cleanup identity changed.',503)
        shutil.rmtree(folder)


if __name__=='__main__':
    import asyncio
    import sys
    if len(sys.argv)!=3:raise SystemExit('Use an exact projects root and project UUID.')
    async def retire():
        selected=await stop_owned(Path(sys.argv[1]),ownerType='project',ownerId=identity(sys.argv[2]))
        forget(Path(sys.argv[1]),selected)
    asyncio.run(retire())
