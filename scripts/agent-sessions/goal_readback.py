"""Read an existing native Goal without resume, credentials, network or a turn."""
import asyncio
import json
from pathlib import Path
from codex_rpc import CodexRPC
from goal_store import Goals
from profile import prepare, PROFILE
from store import ProjectFault


async def readback(store, sid, rpc_factory=CodexRPC):
    if store.get(sid)['engine'].get('api'):
        raise ProjectFault('Native Goal readback is not qualified for this API model.',409)
    goals=Goals(store);before=goals.snapshot(sid);thread=before['threadId']
    if not thread: return {'goal':before,'nativeRead':False,'superseded':False}
    session=store.get(sid);state=store.directory/sid/'Codex';client=None
    # A previous Studio run materialized both the thread and qualified catalog.
    # Never rebuild a missing catalog from an account or create another thread.
    if not (state/'models.json').is_file():
        raise ProjectFault('The saved native catalog is unavailable. Existing Goal data was preserved.',503)
    try:
        args,_=prepare(Path(store.r4os)/'Toolchains/Codex'/session['engine']['version']/'codex',
            state/'ReadbackHome',state,json.loads((Path(__file__).parent/'features.json').read_text()),
            selected_profile=session['engine'].get('profile',PROFILE),goals_enabled=True)
        args.insert(1,'--unshare-net')
        async def notification(method,params):
            if method=='turn/started': raise RuntimeError('A Goal readback cannot start a native turn.')
        async def tool(params): raise RuntimeError('A Goal readback cannot execute model tools.')
        client=rpc_factory(args,notification,tool);client.version='R4OS Studio Goal readback'
        await asyncio.wait_for(client.start(),5)
        value=(await client.request('thread/goal/get',{'threadId':thread},timeout=5))['goal']
        current=goals.snapshot(sid)
        # Concurrent control/worker observations supersede this earlier read.
        if current['revision']!=before['revision']:
            return {'goal':current,'nativeRead':True,'superseded':True}
        if current['goal'] and value and current['goal']['createdAt']==value.get('createdAt'):
            if any(current['goal'][key]>value.get(key,-1) for key in ('updatedAt','tokensUsed','timeUsedSeconds')):
                return {'goal':current,'nativeRead':True,'superseded':True}
        phase=current['phase']
        busy=store.db.execute('SELECT 1 FROM runs WHERE session_id=? AND busy=1',(sid,)).fetchone()
        if (value and value['status']=='active' and not busy) or (phase=='pausing' and not busy):phase='unknown'
        snapshot=goals.observe(sid,thread,value,phase=phase)
        return {'goal':snapshot,'nativeRead':True,'superseded':False}
    except Exception as error:
        if isinstance(error,ProjectFault):raise
        raise ProjectFault('Native Goal status could not be read. The saved state was preserved.',503) from None
    finally:
        if client:await client.close()
