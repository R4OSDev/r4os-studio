"""Conservative historical result projection and exact session-bound readback."""
import base64
import hashlib
import json
import os
import zlib
from conversation import encoded,identifier
from context_result_ids import address,enabled as result_ids,identifier as result_id,resolve as result_reference
from session_store import identity,encode
from store import ProjectFault

PROTOCOL=1
KEEP_RESULTS=8
MIN_LATER_RESPONSES=2
LARGE_OUTPUT=4096
RESULT_READS = {'studio_read_result', 'studio_read_context_result', 'studio_read_skill_result'}


def digest(value):return hashlib.sha256(encoded(value).encode()).hexdigest()

def uncertain(value,depth=0):
    if depth>32:return True
    if isinstance(value,dict):
        for key,part in value.items():
            lower=key.lower()
            if lower in ('partialchangespossible','uncertaineffect') and part is True:return True
            if ('confirmed' in lower or 'verified' in lower) and lower!='contentunconfirmed' and part is False:return True
            if lower.endswith(('state','status','phase','outcome','error')) and isinstance(part,str) and part.lower().replace('-','_') in ('unknown','partial','pending','running','starting','stopping','queued','accepted','unconfirmed','in_progress','inconclusive'):return True
            if uncertain(part,depth+1):return True
    elif isinstance(value,list):return any(uncertain(v,depth+1) for v in value)
    return False


def settled(result):
    if result.get('success') is not True or uncertain(result):return False
    output=result.get('output')
    if isinstance(output,str) and output.lstrip().startswith(('{','[')):
        try:
            if uncertain(json.loads(output)):return False
        except (ValueError,RecursionError):return False
    return True


def reference(worker,record,index):
    part=record['content'][index]
    return {'version':PROTOCOL,'owner':{'type':worker.store.owner_type,'id':worker.store.owner_id},'sessionId':worker.session_id,
            'runId':record['runId'],'recordId':record['id'],'sequence':record['sequence'],'partIndex':index,'callId':part['callId'],
            'sha256':digest(part),'recordSha256':digest(record['content'])}


def load(worker,ref):
    expected={'version','owner','sessionId','runId','recordId','sequence','partIndex','callId','sha256','recordSha256'}
    if not isinstance(ref,dict) or set(ref)!=expected or ref.get('version')!=PROTOCOL:raise ProjectFault('Use the complete original context result reference.',400)
    if ref['owner']!={'type':worker.store.owner_type,'id':worker.store.owner_id} or ref['sessionId']!=worker.session_id:raise ProjectFault('This original context reference belongs to another owner or session.',403)
    identity(ref['runId']);identifier(ref['recordId']);identifier(ref['callId'])
    if type(ref['sequence']) is not int or ref['sequence']<1 or type(ref['partIndex']) is not int or not 0<=ref['partIndex']<8192:raise ProjectFault('Invalid original context sequence or partIndex.',400)
    row=worker.store.db.execute('SELECT c.*,r.session_id AS run_session FROM conversation_records c JOIN runs r ON r.id=c.run_id WHERE c.session_id=? AND c.seq=? AND c.record_id=? AND c.run_id=?',(worker.session_id,ref['sequence'],ref['recordId'],ref['runId'])).fetchone()
    if not row or row['run_session']!=worker.session_id or row['kind']!='message' or row['role']!='tool':raise ProjectFault('The original context result is missing or no longer available.',404)
    from conversation import Conversation
    record=Conversation.present(row);parts=record['content']
    if ref['partIndex']>=len(parts):raise ProjectFault('The original context part is missing.',409)
    part=parts[ref['partIndex']]
    if part.get('type')!='tool_result' or part['callId']!=ref['callId'] or digest(part)!=ref['sha256'] or digest(parts)!=ref['recordSha256']:raise ProjectFault('The original context result hash or identity changed.',409)
    receipt=record.get('origin',{}).get('toolReceiptId')
    if receipt is None and record.get('origin',{}).get('admissionOnly') is True and part['result'].get('success') is False and part['result'].get('error')=='notAdmitted':
        return record,part,{'tool':'not-admitted','state':'notAdmitted','result':encode(part['result'])}
    bound='studio-'+hashlib.sha256(encode([ref['runId'],ref['callId']]).encode()).hexdigest()
    if receipt!=bound or part['result'].get('studioReceiptId')!=receipt:raise ProjectFault('This result has no bound original Studio tool receipt.',409)
    tool=worker.store.db.execute('SELECT tool,state,result FROM tools WHERE run_id=? AND call_id=?',(ref['runId'],receipt)).fetchone()
    if tool is None:raise ProjectFault('The original context tool receipt is missing.',409)
    if tool['tool'] in ('studio_read_environment_notes','studio_record_environment_note'):
        raise ProjectFault('Historical environment-note text is not replayed. Read current environment notes; deleted reports remain deleted.',409)
    result=part['result'];current=worker.config.get('skillAccess',{}).get('entries',[])
    if result.get('skillMcp'):
        saved=result['skillMcp'];entries={(e['id'],e['activeHash']) for e in current if e.get('mcp')}
        if not worker.config.get('permissions',{}).get('studio.read_skill_result') or (saved['skillId'],saved['packageHash']) not in entries:
            raise ProjectFault('This retained skill result is outside the current accepted skill selection.',403)
        from skill_lifecycle import api
        from owner import skills_root
        if api.deleted(skills_root(worker.store.projects),saved['skillId']):raise ProjectFault('The original skill was deleted. Its private result is not replayed.',403)
    if result.get('skillResources'):
        entries={(e['id'],e['activeHash']) for e in current}
        permission=tool['tool'].replace('studio_','studio.',1)
        if not worker.config.get('permissions',{}).get(permission) or any((v['id'],v['hash']) not in entries for v in result['skillResources']):raise ProjectFault('This retained skill resource is outside the accepted skill selection or permission.',403)
        from skill_lifecycle import api
        from owner import skills_root
        if any(api.deleted(skills_root(worker.store.projects),v['id']) for v in result['skillResources']):raise ProjectFault('An original skill was deleted. Its private resource is not replayed.',403)
    return record,part,dict(tool)


def previous_results(worker, records, binding):
    """Use the last confirmed input to carry a prior worker's presentation."""
    from history_receipts import original_input
    from portable_history import foreign_selection

    latest = next((row for row in reversed(records) if row.get('role') == 'assistant'
                   and row.get('origin', {}).get('studioRequestId')), None)
    if latest is None or foreign_selection(latest['origin'].get('selection', {}), binding):
        return {}
    body = original_input(worker.store, worker.session_id, latest)
    if not body:
        return {}

    results = {}
    def remember(call_id, content):
        if not isinstance(call_id, str):
            return
        results[call_id] = None
        if not isinstance(content, str) or '"contextArchive":' not in content:
            return
        try:
            value = json.loads(content)
        except (ValueError, RecursionError):
            return
        if isinstance(value, dict) and isinstance(value.get('contextArchive'), dict) and isinstance(value.get('output'), str):
            results[call_id] = {'output': value['output'], 'contextArchive': value['contextArchive']}

    for message in body.get('input', body.get('messages', [])):
        if not isinstance(message, dict):
            continue
        if message.get('type') == 'function_call_output':
            remember(message.get('call_id'), message.get('output'))
        elif message.get('role') == 'tool':
            remember(message.get('tool_call_id'), message.get('content'))
        elif message.get('role') == 'user' and isinstance(message.get('content'), list):
            for part in message['content']:
                if isinstance(part, dict) and part.get('type') == 'tool_result':
                    content = part.get('content')
                    if isinstance(content, list):
                        content = next((item.get('text') for item in content if isinstance(item, dict) and item.get('type') == 'text'), None)
                    remember(part.get('tool_use_id'), content)
    return results


class Projection:
    def __init__(self,worker):
        from collections import OrderedDict
        from context_media import Screenshots
        self.w=worker;self.key=None;self.value=None;self.source=None;self.cache=OrderedDict();self.bytes=0
        self.screenshots=Screenshots(worker)
        self.previous = None
        self.provenance = None

    def project(self,active,records,checkpoint):
        w=self.w
        if w.config.get('contextResultProtocol')!=PROTOCOL or not w.config.get('permissions',{}).get('studio.read_context_result'):
            return active,records,checkpoint
        key=w.history_reader.scope
        if self.source is active and self.key==key and self.value is not None:return self.value,records,checkpoint
        if self.key!=key:self.cache.clear();self.bytes=0
        from context_policy import optimized
        from signed_history import latest, protected_route
        policy=w.config.get('contextPolicy')
        explicit_media=optimized(policy,1)
        stable=optimized(policy,11)
        self.provenance = {'checkpointSequence': (checkpoint or {}).get('sequence'),
                           'retiredScreenshotSequences': []} if stable else None
        binding={**w.config.get('apiProvider',{}),'model':w.config.get('model')}
        if explicit_media and (protected_route(binding) or latest(active,binding)):
            return active,records,checkpoint
        if stable and self.previous is None:
            self.previous = previous_results(w, records, binding)
        from checkpoint_records import references
        retained={ref['sequence'] for ref in references(checkpoint)}
        if not stable:
            responses=[m.get('sequence',0) for m in active if m.get('role')=='assistant' and m.get('origin',{}).get('providerResponseId')]
            tools=[m.get('sequence',0) for m in active if m.get('role')=='tool']
            recent=responses[-KEEP_RESULTS] if len(responses)>=KEEP_RESULTS else 0
            human=max((m.get('sequence',0) for m in active if m.get('role')=='user' and m.get('origin',{}).get('kind') not in ('goalContinuation','quotaContinuation')),default=0)
            protected={s for s in tools[-KEEP_RESULTS:] if s>=max(recent,human)};cutoff=responses[-MIN_LATER_RESPONSES] if len(responses)>=MIN_LATER_RESPONSES else 0
        retired=self.screenshots.retired(active,retained) if explicit_media else set()
        if stable:
            self.provenance['retiredScreenshotSequences'] = sorted(retired)
        result=[]
        for record in active:
            seq=record.get('sequence',0)
            preview_text = seq not in retained and (stable or seq < cutoff and seq not in protected)
            if record.get('role')!='tool' or not (preview_text or seq in retired):
                result.append(record);continue
            original=record.get('content',[]);parts=[];projected=False
            remove_pixels=seq in retired if explicit_media else True
            saved=self.cache.get(record.get('sequence'))
            if saved and saved[0] is original and saved[3]==(preview_text,remove_pixels):
                self.cache.move_to_end(record['sequence']);result.append(saved[1]);continue
            result_indices=[i for i,p in enumerate(original) if p.get('type')=='tool_result']
            if len(result_indices)!=1:result.append(record);continue
            index=result_indices[0];part=original[index];value=part['result']
            images=[p for p in original if p.get('type')=='image'] if remove_pixels else []
            output=value.get('output');large=preview_text and isinstance(output,str) and len(output.encode())>LARGE_OUTPUT
            if not (large or images) or not settled(value):result.append(record);continue
            try:
                ref=reference(w,record,index);_,_,tool=load(w,ref)
                if tool['state']!='completed' or not tool['result']:result.append(record);continue
                try:confirmed=settled(json.loads(tool['result']))
                except (ValueError,TypeError):confirmed=False
                if not confirmed:result.append(record);continue
            except ProjectFault:result.append(record);continue
            previous = None
            if stable:
                if part['callId'] in self.previous:
                    prior = self.previous[part['callId']]
                    if prior is not None and (prior['contextArchive'].get('reference') == ref or
                            result_ids(w.config) and prior['contextArchive'].get('resultId') == result_id(ref)):
                        previous = prior
                    # A previously transmitted result stays full unless its
                    # original request proves a preview was sent.
                    large = large and previous is not None and previous['output'] != output
                elif tool['tool'] in RESULT_READS:
                    large = False
                if not (large or images):
                    result.append(record);continue
            for offset,p in enumerate(original):
                if remove_pixels and p['type']=='image':continue
                if offset!=index:parts.append(p);continue
                small=dict(value)
                if large:
                    if previous is not None:
                        small['output'] = previous['output']
                    else:
                        from terminal import bounded_text
                        preview,_=bounded_text(output,2048 if stable else 512)
                        small['output']=encode({'kind':'tool_result_preview' if stable else 'historical_tool_preview',
                            'tool':tool['tool'],'originalOutputBytes':len(output.encode()),'textPreview':preview,
                            'truncated':True,'notice':('Read the retained original for the complete tool output.' if stable else
                                'This is a short historical preview, not the complete original. Read the exact original before relying on omitted details.')})
                if images and explicit_media:
                    small['imageDelivery']='reference-only'
                from tool_catalog import result_readback
                small['contextArchive']={**address(w,ref),'historical':not stable or bool(images),'tool':tool['tool'],'imageCount':len(images),
                    'read':result_readback(w.config,'context'),
                    **({'readImage':result_readback(w.config,'image')} if images else {}),
                    'notice':('Use the reference and read fields to retrieve the saved result or image.' if stable else
                        'Use the reference and read fields to retrieve the saved result or image. This is a historical observation.')}
                if previous is not None:
                    prior = previous['contextArchive']
                    if all(prior.get(key) == small['contextArchive'].get(key)
                           for key in ('reference','resultId','read','readImage','imageCount')):
                        small['contextArchive'] = prior
                parts.append({**p,'result':small});projected=True
            value={**record,'content':parts} if projected else record
            result.append(value)
            size=len(encoded(original).encode())
            if projected and size<=8*1024*1024:
                if seq in self.cache:self.bytes-=self.cache.pop(seq)[2]
                while self.cache and (self.bytes+size>8*1024*1024 or len(self.cache)>=1024):
                    _,(_,_,amount,_)=self.cache.popitem(last=False);self.bytes-=amount
                self.cache[seq]=(original,value,size,(preview_text,remove_pixels));self.bytes+=size
        self.key=key;self.value=result;self.source=active;return result,records,checkpoint


def image_reference(record,part,index):
    images=[p['reference'] for p in record['content'] if p.get('type')=='image']
    # A text-only capture may retain its original screenshot reference without
    # registering pixels in the main model's generated-image transport.
    result=part['result'];screenshot=result.get('image')
    if not images and isinstance(screenshot,dict) and result.get('presentation',{}).get('reference'):
        images=[result['presentation']['reference']]
    if type(index) is not int or not 0<=index<len(images):raise ProjectFault('imageIndex is unavailable in this original result.',404)
    return images[index]


async def original_image(worker,ref,index):
    record,part,_=load(worker,ref);reference=image_reference(record,part,index)
    if reference.startswith('studio-generated-image:'):
        from generated_images import GeneratedImages
        images=GeneratedImages(worker.store,worker.session_id)
        try:meta=images.get(identity(reference.split(':',1)[1]));raw=images.path(meta['id']).read_bytes()
        except (OSError,ValueError):raise ProjectFault('The original retained image is missing or changed. No image was regenerated and no new frame was captured.',410) from None
        # The record's immutable media reference must still match a same-run
        # registration (including already-read historical images).
        recorded=part['result'].get('images',[])
        if not any(v.get('id')==meta['id'] and v.get('sha256')==meta['sha256'] for v in recorded):raise ProjectFault('This image is not registered in the original tool result.',409)
        return meta,raw,None
    screenshot=part['result'].get('image')
    if not isinstance(screenshot,dict):raise ProjectFault('The original screenshot is unavailable.',404)
    original='studio-image:'+str(screenshot.get('jobId'))+'/'+str(screenshot.get('id'))
    if (worker.store.owner_type!='project' or reference not in (original,original+'/webp')
        or screenshot.get('projectId')!=worker.store.owner_id or screenshot.get('observer',{}).get('sessionId')!=worker.session_id):raise ProjectFault('The original screenshot is not bound to this owner/session result.',403)
    webp=reference.endswith('/webp') or part['result'].get('screenshotMediaType')=='image/webp'
    if screenshot.get('preview',{}).get('error') and (webp or part['result'].get('imageDelivery')=='reference-only'):
        raise ProjectFault(screenshot['preview']['error'],413)
    data=await worker.development.request('evidence',id=screenshot['jobId'],evidenceId=screenshot['id'],
        **({'screenshotPreview':webp} if screenshot.get('preview') else {}))
    if data.get('metadata')!=screenshot:raise ProjectFault('The original screenshot metadata changed.',409)
    if data.get('previewError'):raise ProjectFault(data['previewError'],413)
    from vision_analysis import transmitted_image
    try:raw,media_type=transmitted_image(data)
    except (ValueError,KeyError,TypeError,zlib.error):raise ProjectFault('The original screenshot bytes are unavailable or changed.',409) from None
    if (media_type=='image/webp')!=webp:raise ProjectFault('The screenshot delivery format changed.',409)
    meta={'id':screenshot['id'],'sessionId':worker.session_id,'runId':ref['runId'],
          'sha256':(screenshot['preview'] if webp else screenshot)['sha256'],'size':len(raw),'mediaType':media_type,
          'width':screenshot['width'],'height':screenshot['height'],**({'originalSha256':screenshot['sha256']} if webp else {})}
    return meta,raw,data


def admit(worker):
    row=worker.store.db.execute('SELECT session_id,busy,state FROM runs WHERE id=?',(worker.run_id,)).fetchone()
    if (worker.stopping or getattr(worker,'closing',False) or not row or row['session_id']!=worker.session_id or not row['busy'] or row['state']!='running'
        or worker.config.get('owner')!={'type':worker.store.owner_type,'id':worker.store.owner_id} or not worker.config.get('permissions',{}).get('studio.read_context_result')):
        raise ProjectFault('Original context readback is not admitted for this run.',403)


async def execute(worker,args,call_id):
    admit(worker)
    if args.get('view')=='index':return read_index(worker,args)
    ref=result_reference(worker,args)
    record,part,tool=load(worker,ref)
    selection={'resultId':args['resultId']} if 'resultId' in args else {'reference':ref}
    notice='Historical original observation only. Reading does not repeat a tool, capture a frame, refresh GUI evidence or confirm its underlying effect.'
    if args.get('view','result')=='result':
        raw=encoded(part['result']).encode();offset=args.get('offset',0);limit=args.get('byteLimit',8192)
        if type(offset) is not int or not 0<=offset<=len(raw) or type(limit) is not int or not 4<=limit<=32768:raise ProjectFault('Use a valid UTF-8 byte offset and byteLimit 4–32768.',400)
        try:raw[:offset].decode('utf-8')
        except UnicodeError:raise ProjectFault('Use the returned original UTF-8 byte offset.',400) from None
        end=min(offset+limit,len(raw))
        while True:
            try:text=raw[offset:end].decode('utf-8');break
            except UnicodeError:end-=1
        value={**selection,'historical':True,'notice':notice,'tool':tool['tool'],'originalReceiptState':tool['state'],'originalSuccess':part['result'].get('success'),
            'sha256':hashlib.sha256(raw).hexdigest(),'encoding':'utf-8','mediaType':'application/json','byteLength':len(raw),'offset':offset,'nextOffset':end if end<len(raw) else None,'text':text,'complete':offset==0 and end==len(raw),
            'imageCount':len([p for p in record['content'] if p.get('type')=='image']) or int(isinstance(part['result'].get('image'),dict))}
        return {'success':True,'output':encode(value)}
    meta,raw,data=await original_image(worker,ref,args.get('imageIndex',0))
    from vision_analysis import native_vision
    native=native_vision(worker)
    value={**selection,'historical':True,'notice':notice,'image':meta,'nativePixels':native}
    if native:
        if data is not None:return {'success':True,'output':encode(value),'image':data['metadata'],'imageDelivery':'pixels','contextReadback':ref,'_transientImage':data,
            **({'screenshotMediaType':'image/webp'} if meta['mediaType']=='image/webp' else {})}
        return {'success':True,'output':encode(value),'generatedImage':meta}
    question=args.get('question')
    if question:
        from vision_analysis import Vision
        if worker.vision_helper is None:worker.vision_helper=Vision(worker)
        historic={'reference':ref,'imageIndex':args.get('imageIndex',0)}
        payload={'metadata':{'id':meta['id'],'bytes':len(raw),'sha256':meta['sha256'],'width':meta['width'],'height':meta['height'],'kind':'historical-image'},
                 'base64':base64.b64encode(raw).decode(),**({'mediaType':'image/webp'} if meta.get('originalSha256') else {})}
        try:value['visionAnalysis']=await worker.vision_helper.analyse(call_id,payload,question,historical=historic)
        except ProjectFault as error:value['visionAnalysis']={'state':'unavailable','reason':str(error),'originalRetained':True}
    else:value['visionAnalysis']={'state':'not-requested','reason':'Provide question to request the configured Vision fallback. The text model did not receive pixels.'}
    return {'success':True,'output':encode(value),'imageDelivery':'reference-only'}


async def authorize_vision(worker,call_id,data,question,historical):
    # Invoked before/after account access by the same Vision helper. No live
    # capture grant or foreign image can enter through this historical branch.
    admit(worker)
    from vision_analysis import native_vision,validate_question,transmitted_image
    from attachment_store import birth
    if native_vision(worker):raise ProjectFault('Historical Vision fallback requires a non-Vision main model.',403)
    row=worker.store.db.execute('SELECT worker,request_id FROM runs WHERE id=?',(worker.run_id,)).fetchone();peer=json.loads(row['worker'] or '{}')
    if any(peer.get(k)!=v for k,v in {'pid':os.getpid(),'birth':birth(os.getpid()),'release':worker.manifest['release']}.items()):raise ProjectFault('The original historical-image parent worker changed.',409)
    tool=worker.store.db.execute('SELECT tool,intent FROM tools WHERE run_id=? AND call_id=?',(worker.run_id,call_id)).fetchone()
    if not tool or tool['tool']!='studio_read_context_result':raise ProjectFault('Historical image analysis needs its own original readback tool.',403)
    args=json.loads(tool['intent'])
    if args.get('view')!='image' or result_reference(worker,args)!=historical['reference'] or args.get('imageIndex',0)!=historical['imageIndex'] or args.get('question')!=question:raise ProjectFault('The original historical image question or reference changed.',409)
    validate_question(question);meta,raw,_=await original_image(worker,historical['reference'],historical['imageIndex'])
    if meta['mediaType']!='image/png' and not meta.get('originalSha256'):
        raise ProjectFault('This historical image format is unavailable to the Vision fallback.',409)
    try:checked,media_type=transmitted_image(data)
    except (ValueError,KeyError,TypeError,zlib.error):raise ProjectFault('The original historical image format or hash is invalid.',409) from None
    if checked!=raw or media_type!=meta['mediaType'] or data['metadata']['sha256']!=meta['sha256']:
        raise ProjectFault('The original historical image bytes changed.',409)
    if worker.config.get('apiProvider'):
        from api_provider_store import ApiProviders
        ApiProviders(worker.manifest['providers']).validate_active(worker.run_id,worker.store.owner_type,worker.store.owner_id,worker.session_id,row['request_id'],worker.config,{k:peer[k] for k in ('pid','birth','release')})
    return raw,data['metadata']


def checkpoint_references(prefix,checkpoint=None,worker=None):
    refs={}
    for ref in (checkpoint or {}).get('origin',{}).get('contextResultReferences',[]):
        refs[(ref['sequence'],ref['partIndex'])]=ref
    for record in prefix:
        for index,part in enumerate(record['content']):
            if part['type']=='tool_result':
                archive=part['result'].get('contextArchive',{})
                ref=result_reference(worker,archive) if worker is not None else archive.get('reference')
                if not ref and worker is not None and record.get('runId') and record.get('sequence'):
                    try:ref=reference(worker,record,index);load(worker,ref)
                    except ProjectFault:ref=None
                if ref:refs[(ref['sequence'],ref['partIndex'])]=ref
    if len(refs)>8192:raise ProjectFault('Historical result reference index exceeds its bound. Original history was retained.',413)
    return [value for _,value in sorted(refs.items())]

def read_index(worker,args):
    identifier(args['checkpointId']);row=worker.store.db.execute("SELECT origin FROM conversation_records WHERE session_id=? AND record_id=? AND kind='checkpoint'",(worker.session_id,args['checkpointId'])).fetchone()
    if not row:raise ProjectFault('Original historical result index not found in this session.',404)
    refs=json.loads(row['origin']).get('contextResultReferences',[]);raw=encoded(refs).encode();sha=hashlib.sha256(raw).hexdigest()
    if args['sha256']!=sha:raise ProjectFault('The original historical result index hash changed.',409)
    offset=args.get('offset',0);limit=args.get('limit',20)
    if type(offset) is not int or not 0<=offset<=len(refs) or type(limit) is not int or not 1<=limit<=20:raise ProjectFault('Use an index offset and limit 1–20.',400)
    page=refs[offset:offset+limit];unavailable=[];addresses=[]
    short=result_ids(worker.config)
    for i,ref in enumerate(page):
        if ref.get('owner')!={'type':worker.store.owner_type,'id':worker.store.owner_id} or ref.get('sessionId')!=worker.session_id:raise ProjectFault('The retained reference index contains a foreign owner/session.',409)
        entry={'sequence':ref.get('sequence'),'partIndex':ref.get('partIndex')} if short else None
        try:
            _,_,tool=load(worker,ref)
            if short:entry.update(address(worker,ref),tool=tool['tool'])
        except ProjectFault as error:unavailable.append({'offset':offset+i,'code':error.code,'reason':str(error)})
        if short:addresses.append(entry)
    return {'success':True,'output':encode({'unavailable':unavailable,'historical':True,'checkpointId':args['checkpointId'],'sha256':sha,'total':len(refs),'offset':offset,'nextOffset':offset+len(page) if offset+len(page)<len(refs) else None,'references':addresses if short else page,'notice':'Original reference index only; read exact result JSON or historical pixels before relying on omitted details.'})}


def has_uncertain_result(record, *, completions=None):
    for index,part in enumerate(record['content']):
        if part['type']!='tool_result':continue
        result=part['result']
        if completions and index in completions:
            from tool_completion import with_completion
            result=with_completion(result,completions[index])
        if uncertain(result):return True
        output=result.get('output')
        if isinstance(output,str) and output.lstrip().startswith(('{','[')):
            try:
                if uncertain(json.loads(output)):return True
            except (ValueError,RecursionError):return True
    return False
