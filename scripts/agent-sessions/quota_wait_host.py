"""Demand from registered waits, using the coordinator's existing bounded work."""
import asyncio
import json
import time
from run_store import get_run
from store import ProjectFault
import quota_wait as waits


def schedule(host):
    for key in tuple(host.quota_waits):
        if len(host.quota_tasks)>=2:return
        if key in host.quota_tasks or host.quota_next.get(key,0)>time.monotonic():continue
        task=asyncio.create_task(observe(host,*key));host.quota_tasks[key]=task
        task.add_done_callback(lambda _,key=key:host.quota_tasks.pop(key,None))

def notify(host,provider):
    if hasattr(host,'quota_epochs'):host.quota_epochs[provider]=host.quota_epochs.get(provider,0)+1
    for scope in tuple(getattr(host,'quota_samples',{})):
        if scope[0]==provider:host.quota_samples.pop(scope,None)
    for key,pid in getattr(host,'quota_scopes',{}).items():
        if pid==provider:host.quota_next.pop(key,None)

def registered(host,store,sid):
    value=waits.row(store,sid);key=(store.owner_type,store.owner_id,sid)
    if value and value['state']=='waiting':host.quota_waits.add(key)

async def observe(host,kind,ident,sid):
    key=(kind,ident,sid);store=None;value=None
    try:
        async with host.lock:
            store=host.store(ident,kind);value=waits.row(store,sid)
            if not value or value['state']!='waiting':host.quota_waits.discard(key);return
            original=get_run(store,value['sourceRunId']);config=json.loads(original['config'])
            if not waits.matches(store,sid,config):
                with store.db:waits.control(store,sid,'The accepted selection or session settings changed.')
                host.quota_waits.discard(key);return
            if original['busy']:return
            from run_boundary import require
            try:ended=await require(host,store,sid)
            except ProjectFault as error:
                if error.code not in (409,423):raise
                status={'state':'unknown','reason':str(error)}
                if value.get('observation')!=status:
                    with store.db:
                        value.update(observation=status,revision=value['revision']+1);waits.put(store,sid,value)
                host.quota_next[key]=time.monotonic()+5
                return
            if ended is None or ended['id']!=value['sourceRunId']:
                with store.db:waits.control(store,sid,'New explicit work replaced the original quota wait.')
                host.quota_waits.discard(key);return
            host.quota_scopes[key]=value['providerId']
        if value['providerBinding']['kind']=='zai-coding-plan':
            from zai_quota_host import start
            await start(host,value['providerId'])
        from quota_wait_sources import read,summary
        generation=host.quota_epochs.get(value['providerId'],0)
        scope=(value['providerId'],value['providerBinding']['revision'],value['providerBinding']['credentialRevision'])
        cached=host.quota_samples.get(scope)
        if not cached or time.monotonic()-cached[0]>=60:
            task=host.quota_reads.get(scope)
            if task is None:
                if len(host.quota_reads)>=2:return
                task=asyncio.create_task(host.read_work.run(read,host.config['providers'],value));host.quota_reads[scope]=task
                task.add_done_callback(lambda _,scope=scope:host.quota_reads.pop(scope,None))
            observation=await asyncio.shield(task)
            host.quota_samples[scope]=(time.monotonic(),observation)
            while len(host.quota_samples)>64:host.quota_samples.pop(next(iter(host.quota_samples)))
        else:observation=cached[1]
        from quota_wait_resume import positive,context,dispatch
        prepared=await host.read_work.run(context,host.config,kind,ident,sid,value['id']) if positive(value,observation) else None
        async with host.lock:
            if host.quota_epochs.get(value['providerId'],0)!=generation:
                host.quota_samples.pop(scope,None);host.quota_next[key]=time.monotonic()+1
                return
            current=waits.row(store,sid)
            if not current or current['state']!='waiting' or current.get('id')!=value['id']:return
            visible=summary(observation)
            from zai_monitor import stamp
            negative=[w['id'] for w in observation.get('windows',[]) if type(w.get('remaining')) in (int,float) and w['remaining']<=0]
            if negative and stamp(observation.get('observedAt')) and stamp(observation['observedAt'])>stamp(current['negativeAt']):
                current.update(negativeAt=observation['observedAt'],negativeWindows=sorted(set(current.get('negativeWindows',[]))|set(negative)))
            if visible!=current.get('observation'):
                with store.db:
                    current.update(observation=visible,revision=current['revision']+1);waits.put(store,sid,current)
            # Re-open current owner/project facts after metadata/context awaits.
            fresh=host.store(ident,kind)
            try:await dispatch(host,fresh,sid,observation,prepared)
            finally:fresh.close()
        host.quota_next[key]=time.monotonic()+60
    except ProjectFault as error:
        if error.code in (404,410):host.quota_waits.discard(key)
        elif error.code==409 and store:
            latest=waits.row(store,sid)
            if latest and value and latest.get('id')==value.get('id'):
                with store.db:waits.control(store,sid,str(error))
                host.quota_waits.discard(key)
            else:host.quota_next.pop(key,None)
        else:host.quota_next[key]=time.monotonic()+60
    except Exception:host.quota_next[key]=time.monotonic()+60
    finally:
        if store:store.close()
