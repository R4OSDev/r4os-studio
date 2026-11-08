"""Disjoint estimates over original JSON spans; never measured component tokens."""
import json

from input_budget import estimate, limit, model_limit, strict
from store import ProjectFault

LABELS={'system':'System prompt','tools':'Tools','conversation':'Conversation','other':'Other / protocol'}
DECODER=json.JSONDecoder()


def spans(raw,object_members=False):
    """Top-level value spans. Keeping slices preserves escaping and UTF-8 size."""
    pos=1
    while pos<len(raw):
        while pos<len(raw) and raw[pos] in ' \r\n\t,':pos+=1
        if raw[pos] in ']}':return
        key=None
        if object_members:
            key,pos=DECODER.raw_decode(raw,pos)
            while raw[pos] in ' \r\n\t':pos+=1
            if raw[pos]!=':':raise ValueError('Invalid JSON member')
            pos+=1
            while raw[pos] in ' \r\n\t':pos+=1
        start=pos;value,pos=DECODER.raw_decode(raw,pos)
        yield key,raw[start:pos],value


def analyze(raw,facts,policy,full=None):
    window=facts.get('contextWindow')
    window=window if type(window) is int and window>0 else None
    input_limit=limit(policy,facts) if isinstance(policy,dict) and strict(policy) else None
    capacity=input_limit if input_limit is not None else window
    model_ceiling=model_limit(facts)
    result={'schema':1,'state':'unavailable','method':None,'estimatedInput':None,'categories':[],
        'modelWindow':window,'inputLimit':input_limit,'capacity':capacity,
        'capacityBasis':'effective-input-limit' if input_limit is not None else 'model-window',
        'outputReserve':window-model_ceiling if window is not None and model_ceiling is not None else None,
        'free':None,'overflow':None,'policyEnforced':isinstance(policy,dict) and strict(policy),'reason':None}
    try:
        full=full or estimate(raw,policy,facts)
        if full.get('schema')==1:
            result.update(state='estimated',method=full['method'],estimatedInput=full['tokens'],
                categories=full['categories'],counting={key:value for key,value in full.items() if key!='categories'},
                free=max(0,capacity-full['tokens']) if capacity is not None else None,
                overflow=max(0,full['tokens']-capacity) if capacity is not None else None)
            return result
        amounts={key:0 for key in LABELS};sizes={key:0 for key in LABELS}
        def add(kind,span):
            value=estimate(span)
            amounts[kind]+=value['tokens']-1024  # shared framing belongs to protocol
            sizes[kind]+=value['bytes']
        for key,span,value in spans(raw,True):
            if key in ('system','instructions'):add('system',span)
            elif key=='tools':add('tools',span)
            elif key in ('messages','input') and isinstance(value,list):
                for _,message,decoded in spans(span):
                    role=decoded.get('role') if isinstance(decoded,dict) else None
                    add('system' if role in ('system','developer') else 'conversation',message)
            elif key in ('input','messages','prompt','images'):add('conversation',span)
        amounts['other']=full['tokens']-sum(amounts.values())
        sizes['other']=full['bytes']-sum(sizes.values())
        if min(*amounts.values(),*sizes.values())<0:raise ValueError('Inconsistent estimate basis')
        result.update(state='estimated',method=full['method'],estimatedInput=full['tokens'],
            categories=[{'id':key,'label':label,'tokens':amounts[key],'bytes':sizes[key]} for key,label in LABELS.items()],
            free=max(0,capacity-full['tokens']) if capacity is not None else None,
            overflow=max(0,full['tokens']-capacity) if capacity is not None else None)
    except (ProjectFault,ValueError,TypeError,KeyError,RecursionError):
        result['reason']='Component tokens cannot be estimated for this original request. The complete body is still available when retained.'
    return result
