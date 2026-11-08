"""One original image operation, owned by a frozen Studio parent tool."""
import asyncio
import base64
import hashlib
import json
import os
import uuid
from attachment_store import birth
from api_provider_store import ApiProviders
from generated_images import GeneratedImages
from image_transport import ImageTransport
from model_operations import Operations
from model_transport import ModelFault
from native_openai import access
from run_store import get_run
from session_store import encode,identity
from store import ProjectFault
from vision_analysis import account_call

TIMEOUT=180

def references(w,args):
    result=[];hashes=[]
    ids=args.get('imageIds',[]);attachments=args.get('attachmentIds',[])
    if len(ids)+len(attachments)>5 or len(set(ids))!=len(ids) or len(set(attachments))!=len(attachments):raise ProjectFault('Use at most five distinct original image references.',400)
    if ids and not w.config['permissions'].get('studio.list_generated_images'):raise ProjectFault('Reading original generated images is disabled.',403)
    images=GeneratedImages(w.store,w.session_id)
    for ident in ids:
        meta=images.get(identity(ident));data=images.path(ident).read_bytes()
        result.append({'image_url':'data:'+meta['mediaType']+';base64,'+base64.b64encode(data).decode()});hashes.append(meta['sha256'])
    if attachments:
        if not w.config['permissions'].get('studio.read_attachment') or not w.config['permissions'].get('studio.read_file'):raise ProjectFault('Reading image attachments requires Read attachment and Read file.',403)
        from image_inputs import history,file_path
        accepted={m['id']:m for m in history(w.store,w.session_id)}
        for ident in attachments:
            meta=accepted.get(identity(ident))
            if not meta or meta['mode']!='localImage':raise ProjectFault('Use an original image explicitly sent in this session.',403)
            data=file_path(w.store,w.session_id,meta).read_bytes()
            result.append({'image_url':'data:'+meta['mediaType']+';base64,'+base64.b64encode(data).decode()});hashes.append(meta['sha256'])
    if sum(len(v['image_url']) for v in result)>7*1024*1024:raise ProjectFault('The original image references exceed the bounded edit input.',413)
    return result,hashes

def authorize(w,call_id,args):
    row=get_run(w.store,w.run_id)
    if (w.config['engine'].get('kind')!='studio' or w.stopping or getattr(w,'closing',False)
            or not row['busy'] or row['state']=='stopping' or row['session_id']!=w.session_id
            or not w.config.get('imageGenerationEnabled') or not w.config['permissions'].get('studio.generate_image')):
        raise ProjectFault('This image request has no active authorized Studio parent.',403)
    worker=json.loads(row['worker'] or '{}');expected={'pid':os.getpid(),'birth':birth(os.getpid()),'release':w.manifest['release']}
    if any(worker.get(k)!=v for k,v in expected.items()):raise ProjectFault('The original image parent worker changed.',409)
    tool=w.store.db.execute('SELECT tool,intent FROM tools WHERE run_id=? AND call_id=?',(w.run_id,call_id)).fetchone()
    if not tool or tool['tool']!='studio_generate_image' or json.loads(tool['intent'])!=args:raise ProjectFault('The original image tool arguments changed.',409)
    prompt=args.get('prompt')
    if (not isinstance(prompt,str) or not prompt.strip() or len(prompt.encode())>4096
            or any(ord(c)<32 and c not in '\t\n\r' for c in prompt) or type(args.get('transparentBackground',False)) is not bool):
        raise ProjectFault('Provide a bounded image prompt and explicit background choice.',400)
    if w.config.get('apiProvider'):
        ApiProviders(w.manifest['providers']).validate_active(w.run_id,w.store.owner_type,w.store.owner_id,w.session_id,row['request_id'],w.config,expected)
    return expected

class ImageGeneration:
    def __init__(self,worker):self.w=worker;self.lock=asyncio.Lock();self.running=None;self.model=None
    async def close(self):
        if self.running and not self.running.done():self.running.cancel();await asyncio.gather(self.running,return_exceptions=True)
        if self.model:await self.model.close()
    async def generate(self,call_id,args):
        async with self.lock:
            self.running=asyncio.create_task(self.once(call_id,args))
            try:return await self.running
            finally:self.running=None
    async def once(self,call_id,args):
        w=self.w;worker=authorize(w,call_id,args);inputs,hashes=references(w,args)
        key=hashlib.sha256(encode({'arguments':args,'imageInputSha256':hashes}).encode()).hexdigest()
        operations=Operations(w.store)
        # Repeated model requests for the same image in this run reuse the
        # original result, including failure or uncertainty, without a new POST.
        old=w.store.db.execute("SELECT data FROM studio_model_calls WHERE run_id=? AND json_extract(data,'$.imageGeneration.inputSha256')=? ORDER BY rowid LIMIT 1",(w.run_id,key)).fetchone()
        if old:
            data=json.loads(old[0]);return data.get('imageGenerationResult') or {'success':False,'error':'unknown','output':'The original image request is unconfirmed. It was not repeated.','operationId':data['requestId']}
        selected=w.config.get('imageGenerationTarget') or {}
        if not selected.get('available'):raise ProjectFault(selected.get('reason','Image generation is unavailable for this frozen run.'),409)
        if w.store.db.execute("SELECT 1 FROM studio_model_calls WHERE run_id=? AND json_extract(data,'$.imageGeneration.purpose')='image-generation' AND COALESCE(json_extract(data,'$.attempted'),1)!=0 AND json_extract(data,'$.processEnd.confirmed') IS NULL",(w.run_id,)).fetchone():raise ProjectFault('An original image process end remains unconfirmed.',503)
        target=selected['target'];provider=target['provider'];op=str(uuid.uuid5(uuid.UUID(w.run_id),encode(['image-generation',call_id])))
        frozen={'engine':{'kind':'studio'},'providerId':provider['id'],'apiProvider':provider,'model':target['modelId'],'effort':'none','apiRunId':op,
            'apiNativeAccount':target['account'],'imageChild':{'purpose':'image-generation','parentRunId':w.run_id,'operationId':op}}
        if 'contextPolicy' in w.config:frozen['contextPolicy']=w.config['contextPolicy'].copy()
        child={'purpose':'image-generation','parentRunId':w.run_id,'parentToolCallId':call_id,'settingsRevision':selected.get('settingsRevision'),
            'source':selected['source'],'snapshot':frozen,'worker':worker,'inputSha256':key,'imageInputSha256':hashes}
        images=GeneratedImages(w.store,w.session_id);images.check_capacity(w.run_id)
        operations.begin(w.run_id,op,child=child);api=ApiProviders(w.manifest['providers']);reserved=False;claimed=False;error=None;result=None;meta=None;self.model=None
        try:
            api.reserve(op,w.store.owner_type,w.store.owner_id,w.session_id,op,frozen);reserved=True
            api.claim(op,w.store.owner_type,w.store.owner_id,w.session_id,op,frozen,worker);claimed=True
            account=await account_call(access,w.manifest['providers'],provider['id'],target['account'])
            authorize(w,call_id,args)
            current_inputs,current_hashes=references(w,args)
            if current_hashes!=hashes:raise ProjectFault('The original edit image changed.',409)
            payload={'model':target['modelId'],'prompt':args['prompt'],'background':'transparent' if args.get('transparentBackground') else 'opaque','quality':'auto','size':'auto','n':1}
            if current_inputs:payload['images']=current_inputs
            self.model=ImageTransport({**provider,'imageAction':'edit' if inputs else 'generate'},target['modelId'],account['key'],
                headers={**account['extraHeaders'],'x-codex-image-turn-id':w.run_id})
            self.model.context_policy=frozen.get('contextPolicy')
            operations.observe(self.model,op)
            task=asyncio.create_task(self.model.response(payload,'',[]))
            async def watch():
                while not task.done():
                    await asyncio.sleep(.25);authorize(w,call_id,args)
                    api.validate_active(op,w.store.owner_type,w.store.owner_id,w.session_id,op,frozen,worker)
            watcher=asyncio.create_task(watch())
            try:
                done,_=await asyncio.wait((task,watcher),timeout=TIMEOUT,return_when=asyncio.FIRST_COMPLETED)
                if not done:raise ModelFault('image_request_timeout')
                if task not in done:await watcher
                result=await task
                # Studio conversation identity is session-owned, without an SDK thread.
                meta=images.accept(w.run_id,w.thread_id or 'studio-'+w.session_id,{'id':op,'result':result['imageResponse']['data'][0]['b64_json']})
            finally:
                watcher.cancel();await asyncio.gather(watcher,return_exceptions=True)
                if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
        except (Exception,asyncio.CancelledError) as cause:error=cause
        finally:
            if self.model:await self.model.close()
            attempted=bool(self.model and self.model.attempted and not getattr(error,'not_dispatched',False))
            operations.finish(op,result=result,error=error,attempted=attempted)
            row,data=operations.row(op);closed=not self.model or self.model.closed_confirmed
            info={'operationId':op,'providerId':provider['id'],'model':target['modelId'],'source':selected['source'],'settingsRevision':selected.get('settingsRevision')}
            if error is None and meta and closed:
                public={'success':True,'generatedImage':meta,'imageGeneration':{**info,'state':'completed'},'output':encode({'image':meta,'stage':'Generated','next':'Reuse this original image; use the authorized project importer when requested.'})}
            else:
                unknown=attempted and result is None and not getattr(error,'http_status',None)
                public={'success':False,'error':'unknown' if unknown else 'imageGenerationFailed','imageGeneration':{**info,'state':'unknown' if unknown else 'failed'},
                    'output':'The original image request did not return a confirmed image. No generation or fallback was repeated.',**({'partialChangesPossible':True} if unknown else {})}
            data['imageGenerationResult']=public;operations.put(op,row['phase'],data)
            if closed:
                if reserved:api.release(op,w.store.owner_type,w.store.owner_id,w.session_id,op,frozen,worker if claimed else None)
                data['imageGeneration']['leaseReleased']=True;operations.put(op,row['phase'],data)
                if self.model:self.model.credential=None;self.model.headers={};self.model._frozen=None
            else:raise ProjectFault('The original image process end is unconfirmed; credentials were retained.',503)
        if isinstance(error,asyncio.CancelledError):raise error
        return public
