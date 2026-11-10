"""Versioned, disjoint full-input estimates. Original JSON is never rewritten."""
import hashlib
import json
import math

from input_budget import scan

LABELS={'system':'System prompt','tools':'Tools','conversation':'Conversation','other':'Other / protocol'}
DECODER=json.JSONDecoder()
PROFILE={'version':1,'method':'characters-v1','charactersPerToken':3}
METHOD='Unicode codepoints / 3, protocol framing and raster reserves; local estimate, not provider usage'


def members(raw,object_members=False):
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
        yield key,start,pos,value


def regions(raw):
    """Non-overlapping original spans; uncovered protocol bytes stay visible."""
    selected=[];messages=0
    if raw.startswith('{'):
        for key,start,end,value in members(raw,True):
            if key in ('instructions','system'):selected.append(('system',start,end,value))
            elif key=='tools':selected.append(('tools',start,end,value))
            elif key in ('messages','input') and isinstance(value,list):
                messages+=len(value)
                for _,a,b,item in members(raw[start:end]):
                    role=item.get('role') if isinstance(item,dict) else None
                    selected.append(('system' if role in ('system','developer') else 'conversation',start+a,start+b,item))
            elif key in ('input','messages','prompt','images'):selected.append(('conversation',start,end,value))
    position=0
    for kind,start,end,value in selected:
        if start>position:yield 'other',raw[position:start],None,0
        yield kind,raw[start:end],value,0
        position=end
    yield 'other',raw[position:],None,messages


def estimate(raw,policy,binding):
    profile=policy.get('counting')
    from input_tokenizer import PROFILE as TOKENIZER,select,count,scope
    if profile not in (PROFILE,TOKENIZER):
        from model_transport import ModelFault
        raise ModelFault('context_input_unavailable',not_dispatched=True)
    groups={key:{'raw':[],'text':[],'media':0} for key in LABELS};message_count=0
    from context_policy import optimized
    from image_input_cost import ImageCost
    media_cost=ImageCost(binding) if optimized(policy,2) else None
    for kind,part,value,messages in regions(raw):
        message_count+=messages
        _,media,_,replacements=scan(value,media_cost) if value is not None else (0,0,0,[])
        text=part
        for original,replacement in replacements:
            # Provider serialization quotes these ASCII data strings verbatim.
            text=text.replace(json.dumps(original,ensure_ascii=False),json.dumps(replacement,ensure_ascii=False),1)
        group=groups[kind];group['raw'].append(part);group['text'].append(text);group['media']+=media
    texts=[''.join(group['text']) for group in groups.values()]
    name,reason=select(binding,profile) if profile==TOKENIZER else (None,'No qualified local tokenizer is selected for this accepted input.')
    try:
        amounts=[count(name,binding,text) for text in texts] if name else [math.ceil(len(text)/3) for text in texts]
    except (ImportError,OSError,ValueError,KeyError,RuntimeError):
        name=None;reason='The pinned tokenizer assets are unavailable for this worker; Unicode fallback used.'
        amounts=[math.ceil(len(text)/3) for text in texts]
    categories=[];framing=1024+16*message_count;media=0;text_chars=0
    for (kind,label),text,amount in zip(LABELS.items(),texts,amounts):
        group=groups[kind];original=''.join(group['raw'])
        text_chars+=len(text);media+=group['media']
        tokens=amount+group['media']+(framing if kind=='other' else 0)
        categories.append({'id':kind,'label':label,'tokens':tokens,'bytes':len(original.encode()),'characters':len(original)})
    return {'schema':1,'tokens':sum(item['tokens'] for item in categories),'bytes':len(raw.encode()),
        'characters':len(raw),'textCharacters':text_chars,'textBytes':sum(len(''.join(g['text']).encode()) for g in groups.values()),
        'mediaTokens':media,'method':('tiktoken 0.14.0 '+name+' over disjoint original JSON text, framing and raster reserves; local estimate, not provider usage') if name else METHOD,
        'source':'local-tokenizer' if name else 'character-estimate','methodVersion':'local-tokenizer-v1' if name else 'characters-v1',
        'tokenizer':{'library':'tiktoken','version':'0.14.0','encoding':name,'manifestSha256':TOKENIZER['manifestSha256']} if name else None,
        'textTokens':sum(amounts),'accuracy':'estimated','fallbackReason':reason,
        'requestSha256':hashlib.sha256(raw.encode()).hexdigest(),
        'modelBinding':{key:binding.get(key) for key in ('id','model','protocol','revision','credentialRevision')},'bindingSha256':scope(binding),
        'reserves':{'framing':framing,'media':media},'categories':categories,
        **({'mediaCost':media_cost.provenance()} if media_cost else {})}
