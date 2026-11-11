"""Read image estimates from original requests with provider-reported usage."""
from collections import Counter, defaultdict
import hashlib
import json
import sqlite3

from history_receipts import completed_call
from input_budget import raster_dimensions, scan
from request_capture import body, exists
from session_store import encode
from store import ProjectFault


MAX_RECEIPTS = 8
MAX_READ_BYTES = 12 * 1024 * 1024
DETAILS = ('auto', 'low', 'high', 'original')


def scope(binding):
    fields = ('id','model','kind','baseUrl','protocol','server','openrouter','imageAction')
    return hashlib.sha256(encode([binding.get(key) for key in fields]).encode()).hexdigest()


def rasters(value):
    images = []
    def observe(data, mime, detail):
        images.append((*raster_dimensions(data, mime), detail))
        return 0
    scan(value, observe)
    return images


def anonymous_messages(wire, usage):
    """Compare only anonymous input messages, with explicit IDs excluded."""
    attribution = (usage.get('attribution') or {}).get('items')
    inputs = wire.get('input')
    if not isinstance(attribution, dict) or not isinstance(inputs, list):
        return None
    identified = {item['id'] for item in inputs if isinstance(item,dict) and isinstance(item.get('id'),str)}
    text = []
    media = []
    for item in inputs:
        if not isinstance(item,dict) or item.get('id') or item.get('role') not in ('assistant','user','developer','system'):
            continue
        content = item.get('content')
        images = sum(isinstance(part,dict) and part.get('type')=='input_image' for part in content) if isinstance(content,list) else 0
        if images:
            media.append(images)
        else:
            text.append(hashlib.sha256(encode(item).encode()).hexdigest())
    counts = []
    for key, item in attribution.items():
        if key.startswith('msg_') and key not in identified and isinstance(item,dict):
            tokens = item.get('input_tokens')
            if type(tokens) is int and tokens > 0:
                counts.append(tokens)
    total = usage.get('input_tokens')
    if len(counts) != len(text)+len(media) or type(total) is not int or sum(counts)>total:
        return None
    params = {key:value for key,value in wire.items() if key!='input'}
    fingerprint = hashlib.sha256(encode([params,text]).encode()).hexdigest()
    return fingerprint, media, tuple(sorted(counts))


def image_tokens(wire, usage, images, baselines):
    if not images or len(set(images)) != 1:
        return None
    total = usage.get('input_tokens', usage.get('prompt_tokens'))
    details = usage.get('input_tokens_details', usage.get('prompt_tokens_details'))
    explicit = details.get('image_tokens') if isinstance(details,dict) else None
    if type(explicit) is int and type(total) is int and 0 < explicit <= total:
        return (explicit+len(images)-1)//len(images)
    if len(images)!=1:
        return None
    anon = anonymous_messages(wire, usage)
    if not anon or anon[1]!=[1]:
        return None
    key, _, counts = anon
    observed = Counter(counts)
    candidates = []
    for previous in baselines.get(key, set()) | ({()} if len(counts)==1 else set()):
        before = Counter(previous)
        if not before-observed:
            difference = list((observed-before).elements())
            if len(difference)==1:
                candidates.append(difference[0])
    return max(candidates, default=None)


def previous(store, sid, binding):
    """Freeze a bounded set of resolution samples from the session's own archive."""
    try:
        return read_samples(store, sid, binding)
    except (sqlite3.Error, ValueError, TypeError, IndexError, KeyError, RecursionError):
        # Optional samples must not hold an input when the archive is unavailable.
        return None


def read_samples(store, sid, binding):
    if not exists(store.db):
        return None
    bound = scope(binding)
    # The last admitted input already carries the samples it used. Read only
    # newer image receipts on the next admission.
    last = store.db.execute("SELECT json_extract(config,'$.contextPolicy.imageEstimate') FROM runs WHERE session_id=? ORDER BY rowid DESC LIMIT 1",
                            (sid,)).fetchone()
    cached = json.loads(last[0]) if last and last[0] else None
    cursor = cached.get('throughSequence',0) if isinstance(cached,dict) and cached.get('bindingSha256')==bound else 0
    if type(cursor) is not int or cursor<1:
        cached = None
        cursor = 0
    select = '''SELECT r.seq,r.request_id,r.run_id,r.sha256,r.metadata,b.bytes,c.data FROM studio_requests r
        JOIN studio_request_bodies b ON b.session_id=r.session_id AND b.sha256=r.sha256
        JOIN studio_model_calls c ON c.request_id=r.request_id AND c.run_id=r.run_id
        WHERE r.session_id=? AND r.dispatch_at IS NOT NULL AND c.phase='completed'
        AND json_extract(r.metadata,'$.providerId')=? AND json_extract(r.metadata,'$.model')=?
        AND json_extract(r.metadata,'$.protocol')=? AND json_extract(r.metadata,'$.purpose') IN ('conversation','vision')
        AND COALESCE(json_extract(r.metadata,'$.context.counting.mediaTokens'),-1)'''
    params = (sid,binding['id'],binding['model'],binding['protocol'])
    with_images = select+" <> 0 AND r.seq>? ORDER BY r.seq DESC LIMIT ?"
    text_only = select+" = 0 ORDER BY r.seq DESC LIMIT ?"
    rows = store.db.execute(with_images,(*params,cursor,MAX_RECEIPTS)).fetchall()
    if not rows:
        return cached
    remaining = MAX_READ_BYTES

    def read(row):
        nonlocal remaining
        if row['bytes']>remaining:
            return None
        try:
            receipt = completed_call(store,sid,row)
            if not receipt:
                return None
            _,call = receipt
            provider = call['selection']['apiProvider']
            if scope({**provider,'model':call['selection']['model']}) != bound:
                return None
            usage = call.get('usage')
            if not isinstance(usage,dict):
                return None
            remaining-=row['bytes']
            wire = json.loads(body(store,sid,row['request_id']))
            if not isinstance(wire,dict) or wire.get('model')!=binding['model']:
                return None
            return wire,usage
        except (ProjectFault, ValueError, TypeError, KeyError, AttributeError, RecursionError):
            return None

    baselines = defaultdict(set)
    if binding['protocol']=='responses':
        for row in store.db.execute(text_only,(*params,MAX_RECEIPTS)):
            original=read(row)
            if not original:
                continue
            try:
                anon=anonymous_messages(*original)
                if anon and not anon[1]:
                    baselines[anon[0]].add(anon[2])
            except (ProjectFault, ValueError, TypeError, AttributeError, RecursionError):
                continue
    remaining = MAX_READ_BYTES
    observed = {}
    for row in rows:
        original=read(row)
        if not original:
            continue
        wire,usage=original
        try:
            images=rasters(wire.get('input',wire.get('messages',[])))
            tokens=image_tokens(wire,usage,images,baselines)
            if tokens and images[0][2] in DETAILS:
                key=images[0]
                observed[key]=max(observed.get(key,0),tokens)
        except (ProjectFault, ValueError, TypeError, AttributeError, RecursionError):
            continue
    samples = {tuple(sample[:3]):sample[3] for sample in (cached or {}).get('samples',[])}
    for key,tokens in reversed(observed.items()):
        samples[key] = max(samples.pop(key,0),tokens)
    return {'bindingSha256':bound, 'throughSequence':rows[0]['seq'],
            'samples':[[*key,tokens] for key,tokens in list(samples.items())[-MAX_RECEIPTS:]]} if samples else None
