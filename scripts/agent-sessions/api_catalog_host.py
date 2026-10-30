"""Bounded metadata-only helpers; original receipts survive coordinator loss."""
import asyncio
import json
from pathlib import Path

from api_catalog import Catalogs
from api_runtime import resolve_binding
from attachment_store import birth
from store import ProjectFault

ERRORS={
    'auth':'The API connection rejected authentication. Review its key and permissions.',
    'account':'The API account needs credits or billing attention before metadata can be read.',
    'unavailable':'The metadata service is temporarily unavailable. Check again explicitly later.',
    'rate_limit':'The API metadata rate limit was reached. Check again explicitly later.',
    'redirect':'The metadata endpoint redirected. Configure its final base URL explicitly.',
    'no_catalog':'This endpoint has no standard Models API. Add an exact model ID manually.',
    'timeout':'The metadata check exceeded its deadline. No model request was made.',
    'cancelled':'The original metadata check was cancelled. No replacement check was sent.',
}
FAILED='The metadata check failed or returned unsupported data. Add a model manually or check again explicitly.'


async def close(child):
    if child is None:return True
    if child.stdin:child.stdin.close()
    if child.returncode is None:
        try:await asyncio.wait_for(child.wait(),2)
        except asyncio.TimeoutError:
            child.terminate()
            try:await asyncio.wait_for(child.wait(),2)
            except asyncio.TimeoutError:
                child.kill()
                try:await asyncio.wait_for(child.wait(),2)
                except asyncio.TimeoutError:return False
    return child.returncode is not None


async def run(host,ident,rid):
    store=Catalogs(host.config['providers']);child=None;proof=None;models=None;error=FAILED;truncated=False
    try:
        binding=store.binding(ident,rid)
        addresses=await resolve_binding(binding)
        script=str(Path(__file__).with_name('api-models.mjs').resolve(strict=True))
        child=await asyncio.create_subprocess_exec('/usr/bin/node',script,stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,limit=4194305)
        proof={'pid':child.pid,'birth':birth(child.pid),'script':script}
        # No credential is obtained until this exact waiting process is journaled.
        credential=store.claim(ident,rid,proof)
        child.stdin.write(json.dumps({'binding':binding,'addresses':addresses,'key':credential},separators=(',',':')).encode()+b'\n')
        await child.stdin.drain();credential=None
        raw=await asyncio.wait_for(child.stdout.readline(),20)
        result=json.loads(raw)
        if result.get('ok') is True and set(result)=={'ok','models','truncated'}:
            models=result['models'];truncated=result['truncated'];error=None
        else:error=ERRORS.get(result.get('code'),FAILED)
    except asyncio.CancelledError:error=ERRORS['cancelled']
    except ProjectFault as failure:error=str(failure)
    except (OSError,ValueError,TypeError,KeyError,ConnectionError,asyncio.TimeoutError):pass
    finally:
        ended=await close(child)
        try:
            if not ended:store.unknown(ident,rid)
            else:
                try:store.finish(ident,rid,models,error,proof,truncated)
                except ProjectFault:store.finish(ident,rid,error=FAILED,child=proof)
        except Exception:pass  # Preserve the original journal/credential on uncertainty.


async def start(host,ident,data):
    async with host.catalog_lock:
        result,fresh=Catalogs(host.config['providers']).start_refresh(ident,data,len(host.catalog_tasks)<2)
        if fresh:
            rid=result['requestId'];task=asyncio.create_task(run(host,ident,rid));host.catalog_tasks[rid]=task
            task.add_done_callback(lambda _,rid=rid:host.catalog_tasks.pop(rid,None))
        return result


async def recover(host,ident=None):
    """Close only original helpers; neither boot nor disconnect repeats a GET."""
    store=Catalogs(host.config['providers'])
    for row in store.pending(ident):
        rid=row['id']
        if rid in host.catalog_tasks:
            host.catalog_tasks[rid].cancel()
            await asyncio.gather(host.catalog_tasks[rid],return_exceptions=True)
        try:
            proof=json.loads(row['child']) if row['child'] else None
            if row['held']:
                if not isinstance(proof,dict) or set(proof)!={'pid','birth','script'}:raise ValueError()
                store.signal_original(proof)
                for _ in range(20):
                    if not store.alive(proof):break
                    await asyncio.sleep(.1)
                if store.alive(proof):raise ValueError()
            store.finish(row['provider_id'],rid,error=ERRORS['cancelled'],child=proof)
        except Exception:store.unknown(row['provider_id'],rid)
