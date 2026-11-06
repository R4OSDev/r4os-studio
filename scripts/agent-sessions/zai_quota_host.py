"""One original subscription GET through the normal private helper lifecycle."""
import asyncio
import json
from pathlib import Path
from api_catalog_host import close
from api_runtime import resolve_binding
from attachment_store import birth
from zai_quota import Quota
from store import ProjectFault


async def run(host,ident,rid):
    store=Quota(host.config['providers']);child=None;proof=None;body=None;error='service';retry_after=None
    try:
        binding=store.binding(ident,rid);addresses=await resolve_binding(binding)
        script=str(Path(__file__).with_name('zai-quota.mjs').resolve(strict=True))
        child=await asyncio.create_subprocess_exec('/usr/bin/node',script,stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,limit=524288)
        proof={'pid':child.pid,'birth':birth(child.pid),'script':script}
        credential=store.claim(ident,rid,proof)
        child.stdin.write(json.dumps({'binding':binding,'addresses':addresses,'key':credential},separators=(',',':')).encode()+b'\n')
        await child.stdin.drain();credential=None
        result=json.loads(await asyncio.wait_for(child.stdout.readline(),20))
        if result.get('ok') is True and set(result)=={'ok','body'}:body=result['body'];error=None
        else:
            error=result.get('code') if result.get('code') in ('auth','format','timeout','rate_limit') else 'service'
            retry_after=result.get('retryAfterAt') if error=='rate_limit' else None
    except asyncio.CancelledError:error='cancelled'
    except (ProjectFault,OSError,ValueError,TypeError,KeyError,ConnectionError,asyncio.TimeoutError):pass
    finally:
        ended=await close(child)
        try:
            if ended:store.finish(ident,rid,body,error,proof,retry_after)
            else:store.unknown(ident,rid)
        except Exception:pass  # Keep the original credential lease on uncertainty.


async def start(host,ident,data=None):
    async with host.catalog_lock:
        store=Quota(host.config['providers'])
        allowed=len(host.catalog_tasks)<2
        result,fresh=await asyncio.to_thread(store.ensure,ident,allowed) if data is None else await asyncio.to_thread(store.start_refresh,ident,data,allowed)
        if fresh:
            rid=result['requestId'];task=asyncio.create_task(run(host,ident,rid));host.catalog_tasks[rid]=task
            task.add_done_callback(lambda _,rid=rid:host.catalog_tasks.pop(rid,None))
        return result

async def ensure(host,ident):
    await start(host,ident)
    return await host.read_work.run(Quota(host.config['providers']).listing,ident)
