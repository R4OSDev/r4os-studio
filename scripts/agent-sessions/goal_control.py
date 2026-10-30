"""Native paused control outside inference; live commands use the owning worker."""
import asyncio
import fcntl
import json
import socket
import struct
from pathlib import Path
from codex_rpc import CodexRPC
from goal_contract import save_params
from goal_store import Goals
from profile import prepare, PROFILE, SANDBOX_MODE
from owner import open_lock
from store import ProjectFault


def matches(action, text, raw):
    if action == 'save':
        from goal_contract import objective
        text = objective(text, allow_empty=True)
        return raw is None if not text else bool(raw and raw['objective']==text and raw['status']=='paused')
    return raw is None or raw['status'] != 'active'


async def idle_control(store, sid, rid, providers, rpc_factory=CodexRPC):
    if store.get(sid)['engine'].get('api'):
        raise ProjectFault('Native Goal controls are not qualified for this API model.',409)
    goals=Goals(store); row=goals.command(sid,rid); command=json.loads(row['payload'])
    if row['state']!='pending': return goals.receipt(sid,rid)
    if command['action']=='play': raise ProjectFault('Goal execution requires the multi-turn worker.',503)
    lock=open_lock(store.projects,store.owner_type,store.owner_id); client=None; sent=False
    try:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ProjectFault('Another operation is using this workspace.',409) from None
        if store.db.execute('SELECT 1 FROM runs WHERE busy=1').fetchone(): raise ProjectFault('The owning worker must handle this Goal command.',409)
        session=store.get(sid); thread=store.row(sid)['thread_id']
        if not thread and (command['action']!='save' or not command['objective'].strip()):
            return goals.finish(sid,rid)
        args,_=prepare(Path(store.r4os)/'Toolchains/Codex'/session['engine']['version']/'codex',
                Path(providers)/session['providerId'],store.directory/sid/'Codex',
                json.loads((Path(__file__).parent/'features.json').read_text()),session['model'],session['providerId'],
                session['engine'].get('profile',PROFILE),goals_enabled=True)
        async def notification(method,params):
            # RPC readback is authoritative here. Do not issue another request
            # from the serial notification reader or consume opaque payloads.
            if method=='turn/started': raise RuntimeError('Paused Goal control unexpectedly started a native turn.')
        async def tool(params): raise RuntimeError('A paused Goal controller cannot execute model tools.')
        client=rpc_factory(args,notification,tool);client.version='R4OS Studio Goal control';await client.start()
        if not thread:
            goals.stage(sid,rid,'thread_materialization');sent=True
            from tool_catalog import specifications
            result=await client.request('thread/start',{'cwd':'/workspace','model':session['model'],'ephemeral':False,
                'dynamicTools':specifications(session['engine']['profile']), 'sandbox':SANDBOX_MODE,'approvalPolicy':'never',
                'baseInstructions':'This is a Studio session. Saving a paused Goal grants no permission to start work.'})
            thread=result['thread']['id']
            with store.db: store.db.execute('UPDATE sessions SET thread_id=? WHERE id=? AND thread_id IS NULL',(thread,sid))
        previous=(await client.request('thread/goal/get',{'threadId':thread}))['goal']
        goals.observe(sid,thread,previous)
        if command['action']=='save': method,params=save_params(thread,command['objective'],previous)
        elif previous is not None: method,params='thread/goal/set',{'threadId':thread,'status':'paused','origin':'user'}
        else: return goals.finish(sid,rid)
        goals.stage(sid,rid,'native_mutation');sent=True
        try: await client.request(method,params)
        except Exception:
            # One read of this same native thread may prove an acknowledged
            # state despite a lost response. Never send the mutation again.
            pass
        result=(await client.request('thread/goal/get',{'threadId':thread}))['goal']
        goals.observe(sid,thread,result)
        if not matches(command['action'],command.get('objective'),result):
            return goals.finish(sid,rid,'unknown','The native Goal did not confirm the requested state. It was not submitted again.')
        return goals.finish(sid,rid)
    except BaseException as error:
        goals.finish(sid,rid,'unknown' if sent else 'failed', str(error) if isinstance(error,ProjectFault) else 'The original native Goal command could not be confirmed. It was not repeated.')
        if isinstance(error,asyncio.CancelledError): raise
        return goals.receipt(sid,rid)
    finally:
        if client: await client.close()
        lock.close()


async def live_control(store,sid,rid):
    run=store.db.execute('SELECT * FROM runs WHERE session_id=? AND busy=1',(sid,)).fetchone()
    if not run: raise ProjectFault('The original Goal worker is no longer active. Read its result.',409)
    # Abstract address avoids Linux's108-byte pathname limit for UUID owners.
    # Both peers verify UID; the caller also verifies the original worker PID.
    address='\0r4os-studio-goal-'+run['id']
    reader,writer=await asyncio.wait_for(asyncio.open_unix_connection(address),3)
    try:
        pid,uid,_=struct.unpack('3i',writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        worker=json.loads(run['worker'] or '{}')
        # The coordinator does not import the development worker's modules.
        # Use the local process identity helper in a clean host interpreter too.
        from attachment_store import birth
        if uid != __import__('os').getuid() or pid!=worker.get('pid') or birth(pid)!=worker.get('birth'):
            raise ProjectFault('The original Goal worker identity changed.',403)
        writer.write((json.dumps({'requestId':rid,'runId':run['id'],'sessionId':sid})+'\n').encode());await writer.drain()
        result=json.loads(await asyncio.wait_for(reader.readline(),20))
        if result.get('error'): raise ProjectFault(result['error'],result.get('code',503))
        return result['result']
    finally: writer.close();await writer.wait_closed()
