"""Optional Responses input counting: one bounded request, never inference."""
import asyncio
from collections import OrderedDict
import codecs
import hashlib
import json
import time
import uuid

from model_transport import ModelTransport,ModelFault,loads,dumps
from session_store import now
from store import ProjectFault

CONTRACT='openai-responses-input-tokens-v1'


def supported(binding):
    # The published API contract is qualified; the Codex subscription route
    # exposes no confirmed count endpoint. Never probe it or switch accounts.
    return (binding.get('kind')=='openai-compatible' and binding.get('baseUrl')=='https://api.openai.com/v1'
        and binding.get('protocol')=='responses' and binding.get('auth')=='bearer'
        and binding.get('server','custom')=='custom')


class JSONDecoder:
    def __init__(self):self.text=codecs.getincrementaldecoder('utf-8')('strict');self.parts=[];self.size=0
    def push(self,value,final=False):
        self.size+=len(value)
        if self.size>65536:raise ModelFault('input_count_response_limit')
        self.parts.append(self.text.decode(value,final))
        return [''.join(self.parts)] if final else []


class CountResult:
    origin=None;usage=None
    def __init__(self):self.tokens=None
    def push(self,raw):
        data=loads(raw)
        if (self.tokens is not None or not isinstance(data,dict) or data.get('object')!='response.input_tokens'
                or type(data.get('input_tokens')) is not int or not 0<=data['input_tokens']<=2**53-1):
            raise ModelFault('input_count_response_invalid')
        self.tokens=data['input_tokens']
    def result(self):
        if self.tokens is None:raise ModelFault('input_count_response_invalid')
        return {'inputTokens':self.tokens}


class CountTransport(ModelTransport):
    def decoder(self):return JSONDecoder()
    def prepare(self,payload,instructions,tools,effort=''):
        return payload,CountResult()


def payload(body):
    fields={'model','instructions','input','tools','reasoning','text','tool_choice','parallel_tool_calls',
        'truncation','previous_response_id','conversation'}
    metadata={'store','stream','include','max_output_tokens','temperature','top_p','user','service_tier',
        'prompt_cache_key','prompt_cache_retention','background','metadata','safety_identifier','max_tool_calls'}
    if set(body)-fields-metadata:raise ModelFault('input_count_projection_unavailable')
    return {key:value for key,value in body.items() if key in fields}


async def count(model,body):
    policy=model.context_policy or {};choice=policy.get('providerCount') or {}
    if (policy.get('schema')!=4 or choice!={'version':1,'enabled':True,'contract':CONTRACT}
            or model.binding.get('inputTokenCounting') is not True or not supported(model.binding)):
        return
    raw=model.encoded(body);scope=model.freeze_scope();key=(hashlib.sha256(raw.encode()).hexdigest(),scope)
    try:value=model.input_estimate(body)
    except ModelFault as error:
        if error.code!='context_input_unavailable':raise
        value={'schema':1,'tokens':None,'bytes':len(raw.encode()),'characters':len(raw),'categories':[],
            'accuracy':'unavailable','source':'unavailable','method':'Local input could not be counted.',
            'requestSha256':key[0],'fallbackReason':'Local media accounting is unavailable.'}
        model._input_estimate=(raw,value);model._estimate_scope=json.dumps([model.context_policy,model.binding],ensure_ascii=False,separators=(',',':'))
    from input_budget import limit
    maximum=limit(policy,model.binding)
    # Count only ambiguous media/unmapped models or a request near its limit.
    needed=(value['tokens'] is None or value.get('fallbackReason') is not None or value.get('mediaTokens',0)>0
        or maximum is not None and value['tokens']>=maximum*0.8)
    if not needed:return
    cache=getattr(model,'_count_cache',None)
    if cache is None:cache=model._count_cache=OrderedDict()
    saved=cache.get(key)
    if saved and saved[0]>time.monotonic():
        apply(model,value,saved[1],scope);return
    if getattr(model,'_count_backoff_scope',None)==scope and getattr(model,'_count_backoff',0)>time.monotonic():return
    pending=getattr(model,'_count_task',None)
    if pending is not None and not pending.done() and getattr(model,'_count_key',None)==key:
        record=await pending
    else:
        model._count_key=key;model._count_task=asyncio.create_task(request(model,body,key[0]))
        record=await model._count_task
    # A result for a changed payload, route, credential or policy is never used.
    if model.freeze_scope()!=scope or model.encoded(body)!=raw:return
    ttl=60 if record['state']=='complete' else 30
    cache[key]=(time.monotonic()+ttl,record);cache.move_to_end(key)
    while len(cache)>8:cache.popitem(last=False)
    if record['state']!='complete':model._count_backoff=time.monotonic()+30;model._count_backoff_scope=scope
    apply(model,value,record,scope)


def apply(model,value,record,scope):
    value['providerCount']=record
    if record['state']=='complete':
        value['admissionTokens']=record['inputTokens'];model._provider_count_scope=scope


async def request(model,body,digest):
    binding={**model.binding,'countInput':True}
    counter=CountTransport(binding,binding['model'],model.credential,headers=model.headers.copy())
    record={'id':str(uuid.uuid4()),'purpose':'input-count','state':'checking','contract':CONTRACT,
        'requestSha256':digest,'providerId':binding['id'],'model':binding['model'],
        'configRevision':binding.get('revision'),'credentialRevision':binding.get('credentialRevision'),
        'createdAt':now(),'inputTokens':None,'process':None,'processEnd':None,'dispatchAt':None,'responseAt':None}
    def emit():
        observer=getattr(model,'count_observer',None)
        if observer:observer(dict(record))
    def transport(stage,status=None):
        record['dispatchAt' if stage=='dispatch' else 'responseAt']=now()
        if status is not None:record['httpStatus']=status
    def process(stage,child):
        from attachment_store import birth
        if stage=='started':record['process']={'pid':child.pid,'birth':birth(child.pid)}
        else:record['processEnd']={'confirmed':child.returncode is not None,'exitCode':child.returncode,'at':now()}
    counter.request_observer=transport;counter.process_observer=process
    emit()
    try:
        data=payload(body)
        record['countBodySha256']=hashlib.sha256(dumps(data).encode()).hexdigest()
        result=await asyncio.wait_for(counter.response(data,'',[]),8)
        record.update(state='complete',inputTokens=result['inputTokens'])
    except asyncio.CancelledError:
        record['state']='interrupted'
        raise
    except (ProjectFault,OSError,ValueError,asyncio.TimeoutError) as error:
        record.update(state='unavailable',error={'code':getattr(error,'code','input_count_unavailable'),
            'httpStatus':getattr(error,'http_status',None)})
    finally:
        await counter.close();record['finishedAt']=now();record['closedConfirmed']=counter.closed_confirmed
        emit()
    return record
