"""Use the coordinator's normal admission/launch path only at whole-run boundaries."""
import asyncio
import json
from pathlib import Path
from owner import binding
from run_store import admit
from store import ProjectFault
import goal_keepalive as control


def schedule(host):
    for key in tuple(host.keepalives):
        task_key=(*key,'keepalive')
        if len(host.goal_tasks)>=2:return
        if task_key in host.goal_tasks:continue
        task=asyncio.create_task(dispatch(host,*key));host.goal_tasks[task_key]=task
        task.add_done_callback(lambda _,key=task_key:host.goal_tasks.pop(key,None))


async def dispatch(host,kind,ident,sid):
    store=None
    try:
        async with host.lock:
            if host.unbound or len(host.active)>=host.max_active_runs:return
            if any(binding(meta)==(kind,ident) for meta in host.active.values()):return
            store=host.store(ident,kind);value=control.row(store,sid)
            if not value or not value['active']:
                host.keepalives.discard((kind,ident,sid));return
            from quota_wait import row as quota_wait
            waiting=quota_wait(store,sid)
            if waiting and waiting['state'] in ('waiting','dispatching'):return
            from message_store import pending_queue
            if pending_queue(store,sid):return
            from run_boundary import require
            source=await require(host,store,sid)
            if source is not None and source['state']!='completed':
                waiting=quota_wait(store,sid);prior=json.loads(source['config']).get('goalKeepalive') or {}
                play=store.db.execute('SELECT created_at FROM goal_commands WHERE request_id=?',(value.get('playRequestId'),)).fetchone()
                explicit_restart=bool(waiting and waiting['state']=='cancelled' and waiting.get('sourceRunId')==source['id']
                    and value.get('lastIntent')=='play' and value['generation']>prior.get('generation',0)
                    and value.get('playRequestId')!=prior.get('playRequestId') and source['state']=='failed'
                    and play and play['created_at']>waiting.get('createdAt',''))
                if not explicit_restart:
                    if waiting and waiting['state']=='cancelled' and waiting.get('sourceRunId')==source['id']:
                        return  # This cancelled intent cannot rearm Goal or alter its clock/control.
                    control.block(store,sid,'The previous run did not complete normally. Continue explicitly.');return
            execution=control.prepare(store,sid,source['id'] if source else None)
            if not execution:return
            session=store.get(sid)
            from model_choice import capture
            selected,marker=capture(store,sid,session)
            selection=(selected['providerId'],selected['model'],selected.get('effort'),selected.get('fastMode'),marker,session['revision'])
        image_capability=None
        if selected.get('imageGenerationEnabled',True):
            from image_generation import inspect
            async with host.image_capability_lock:
                image_capability=await inspect(store,sid,host.config['providers'],{'model':selected['model']})
        async with host.lock:
            if host.unbound or len(host.active)>=host.max_active_runs:return
            control.require(store,sid,execution)
            if pending_queue(store,sid):return
            latest=await require(host,store,sid)
            if (latest['id'] if latest else None)!=execution['afterRunId']:return
            session=store.get(sid);selected,marker=capture(store,sid,session)
            if selection!=(selected['providerId'],selected['model'],selected.get('effort'),selected.get('fastMode'),marker,session['revision']):return
            target=Path(host.config.get('workerReleaseRoot','/opt/r4os-studio/current')).resolve(strict=True)
            if not target.is_relative_to('/opt/r4os-studio/releases') or not (target/'scripts/agent-sessions/goal_keepalive_run.py').is_file():
                raise ProjectFault('The selected worker release cannot preserve session Goal keepalive.',503)
            data={'requestId':execution['requestId'],'revision':session['revision'],'text':execution['goal']['objective'],
                'nativeWebSearch':1,'skillSelection':1,'skillScripts':1,'skillMcp':1,'nativeImageInputs':1,'documentInputs':1,
                'imageGenerationSettings':1,'environmentNotesSettings':1,
                **({'projectInstructions':1,'roadmapSettings':1,'remoteHostTools':1} if kind=='project' else {})}
            from model_choice import prepare
            await prepare(host,store,sid,data)
            run,fresh=admit(store,sid,data,host.config['providers'],image_capability,keepalive=execution)
            if not fresh:
                # An admitted original whose launch/end was lost cannot be launched again.
                control.block(store,sid,'The original Goal continuation already exists. Read its original run receipt.',unknown=True);return
            control.admitted(store,sid,execution,run['id'])
            await host.launch_admitted(store,run,kind,ident,sid)
    except ProjectFault as error:
        if error.code!=423 and store:
            try:
                value=control.row(store,sid)
                if value and value['active'] and ('execution' not in locals() or value['generation']==execution['generation']):
                    control.block(store,sid,str(error),unknown='unconfirmed' in str(error).lower() or 'unknown' in str(error).lower(),expected=value['generation'])
            except Exception:pass
    except Exception:
        if store:
            try:control.block(store,sid,'The original Goal boundary could not be confirmed. No continuation was repeated.',unknown=True)
            except Exception:pass
    finally:
        if store:store.close()
