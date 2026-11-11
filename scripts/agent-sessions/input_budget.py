"""Conservative admission of the complete serialized provider input.

This is deliberately separate from provider usage. No universal tokenizer is
available for arbitrary compatible endpoints. Charge every UTF-8 byte, framing
headroom and a raster reserve instead of treating four bytes as one token.
"""
import base64
import io
import json
import math

METHOD='Full request UTF-8 bytes (one per token), framing headroom and raster reserves; conservative local estimate, not provider usage'


def strict(policy):
    return isinstance(policy,dict) and policy.get('schema') in (3,4)


def model_limit(binding):
    capacity=binding.get('contextWindow')
    if type(capacity) is not int or capacity<=0:return None
    # Keep the established 20% output headroom, and any larger declared output
    # reservation. Neither an off switch nor a large custom limit removes it.
    maximum=binding.get('maxOutputTokens',8192 if binding.get('protocol')=='messages' else None)
    reserve=maximum if type(maximum) is int and maximum>0 else 0
    return max(0,min(capacity*4//5,capacity-reserve))


def limit(policy,binding):
    result=model_limit(binding)
    if policy.get('enabled',True):
        from context_policy import budget
        chosen=budget(policy.get('budgetTokens'))
        result=chosen if result is None else min(chosen,result)
    return result


def unavailable_count(value):
    from model_transport import ModelFault
    missing_images=value.get('mediaCost',{}).get('unavailableImages')
    code='context_image_tokens_unavailable' if missing_images else 'context_input_unavailable'
    return ModelFault(code,not_dispatched=True)


def raster_dimensions(data,mime):
    from model_transport import ModelFault
    try:
        from PIL import Image
        raw=base64.b64decode(data,validate=True)
        with Image.open(io.BytesIO(raw),formats=['PNG','JPEG','WEBP']) as image:
            width,height=image.size
            if mime!={'PNG':'image/png','JPEG':'image/jpeg','WEBP':'image/webp'}[image.format]:raise ValueError()
        if not 0<width<=16384 or not 0<height<=16384 or width*height>40_000_000:raise ValueError()
        return width,height
    except (ImportError,OSError,ValueError,KeyError,TypeError):
        raise ModelFault('context_input_unavailable',not_dispatched=True) from None


def raster_reserve(width,height):
    return max(65536,16*math.ceil(width/32)*math.ceil(height/32))


def raster(data,mime):
    return raster_reserve(*raster_dimensions(data,mime))


def scan(body, media_cost=None):
    """Charge raster inputs once; expose exact strings whose base64 is not text."""
    from model_transport import ModelFault
    pending=[body];nodes=0;media=0;encoded_media=0;replacements=[]
    while pending:
        value=pending.pop();nodes+=1
        if isinstance(value,dict):
            kind=value.get('type');data=None;mime=None
            if kind in ('input_image','image_url') or set(value)=={'image_url'} and isinstance(value['image_url'],str):
                url=value.get('image_url')
                if isinstance(url,dict):url=url.get('url')
                if not isinstance(url,str) or not url.startswith('data:') or ';base64,' not in url:
                    raise ModelFault('context_input_unavailable',not_dispatched=True)
                prefix,data=url.split(';base64,',1);mime=prefix[5:]
            elif kind=='image' and isinstance(value.get('source'),dict):
                source=value['source']
                if source.get('type')!='base64' or not isinstance(source.get('data'),str):
                    raise ModelFault('context_input_unavailable',not_dispatched=True)
                data=source['data'];mime=source.get('media_type')
            if data is not None:
                detail=value.get('detail','auto')
                if kind=='image_url' and isinstance(value.get('image_url'),dict):
                    detail=value['image_url'].get('detail','auto')
                media+=(media_cost(data,mime,detail) if media_cost else raster(data,mime));encoded_media+=len(data.encode())
                if kind=='image':replacements.append((data,''))
                else:replacements.append((url,url[:-len(data)] if data else url))
            pending.extend(value.values())
        elif isinstance(value,list):pending.extend(value)
    return nodes,media,encoded_media,replacements


def estimate(raw,policy=None,binding=None):
    if isinstance(policy,dict) and policy.get('schema')==4:
        from input_count import estimate as count
        return count(raw,policy,binding or {})
    nodes,media,encoded_media,_=scan(json.loads(raw))
    size=len(raw.encode())
    # Base64 pixels are not text tokens. All surrounding JSON, text, schemas,
    # names, signatures, cache markers and provider prefixes remain charged.
    return {'tokens':size-encoded_media+1024+16*nodes+media,'bytes':size,
        'textBytes':size-encoded_media,'mediaTokens':media,'method':METHOD}
