"""Indexed, session-bound reads of originals; no model, migration or schema writes."""
import base64
import json

from request_capture import exists, body, MAX_BODY, MAX_REQUESTS, BODY_BUDGET
from session_store import identity
from store import ProjectFault


def record(store,row):
    meta=json.loads(row['metadata'])
    if meta['owner']!={'type':store.owner_type,'id':store.owner_id}:
        raise ProjectFault('Original request ownership is unavailable.',503)
    blocked=meta.get('blocked')
    if not blocked and row['phase'] is None:raise ProjectFault('Original model call metadata is unavailable.',503)
    return {'id':row['request_id'],'sequence':row['seq'],'runId':row['run_id'],
        'model':meta['model'],'providerId':meta['providerId'],'protocol':meta['protocol'],
        'purpose':meta['purpose'],'at':row['dispatch_at'] or meta['capturedAt'],'capturedAt':meta['capturedAt'],
        'responseAt':meta['responseAt'],'httpStatus':meta['httpStatus'],'bytes':meta['bytes'],
        'sha256':row['sha256'],'bodyAvailable':bool(row['available']),'phase':row['phase'] or 'blocked',
        'blockedReason':blocked.get('reason') if blocked else None,
        'status':'blocked-before-send' if blocked else 'response-received' if meta['responseAt'] else 'dispatch-attempted'}


SELECT='''SELECT r.*,c.phase,b.sha256 IS NOT NULL AS available FROM studio_requests r
    LEFT JOIN studio_model_calls c ON c.request_id=r.request_id AND c.run_id=r.run_id
    LEFT JOIN studio_request_bodies b ON b.session_id=r.session_id AND b.sha256=r.sha256 '''


BLOCKED="r.dispatch_at IS NULL AND json_extract(r.metadata,'$.blocked') IS NOT NULL"
SENT='r.dispatch_at IS NOT NULL'
VISIBLE='('+SENT+' OR '+BLOCKED+')'


def page(store,sid,before=None,count=20,kind='dispatched'):
    session=store.row(sid)
    if kind not in ('dispatched','blocked'):raise ProjectFault('Invalid context request kind.',400)
    if before is not None and (type(before) is not int or before<1):raise ProjectFault('Invalid request cursor.',400)
    if type(count) is not int or not 1<=count<=50:raise ProjectFault('Invalid request page size.',400)
    rows=[];dropped=0;blocked_available=False
    if exists(store.db):
        blocked_available=store.db.execute('SELECT 1 FROM studio_requests r WHERE r.session_id=? AND '+BLOCKED+' LIMIT 1',(sid,)).fetchone() is not None
        stamp='9999'
        sequence=9223372036854775807
        if before is not None:
            cursor=store.db.execute('SELECT r.dispatch_at,r.seq FROM studio_requests r WHERE r.session_id=? AND r.seq=? AND '+(BLOCKED if kind=='blocked' else SENT),(sid,before)).fetchone()
            if not cursor:raise ProjectFault('The original request cursor is no longer retained.',410)
            stamp,sequence=cursor['dispatch_at'],cursor['seq']
        if kind=='blocked':
            rows=store.db.execute(SELECT+'WHERE r.session_id=? AND '+BLOCKED+' AND r.seq<? ORDER BY r.seq DESC LIMIT ?',
                (sid,sequence,count+1)).fetchall()
        else:
            rows=store.db.execute(SELECT+'''WHERE r.session_id=? AND r.dispatch_at IS NOT NULL
                AND (r.dispatch_at,r.seq)<(?,?) ORDER BY r.dispatch_at DESC,r.seq DESC LIMIT ?''',
                (sid,stamp,sequence,count+1)).fetchall()
        saved=store.db.execute('SELECT dropped FROM studio_request_retention WHERE session_id=?',(sid,)).fetchone()
        dropped=saved['dropped'] if saved else 0
    engine=json.loads(session['engine']).get('kind')
    return {'requests':[record(store,row) for row in rows[:count]],'kind':kind,'blockedAvailable':blocked_available,
        'nextBefore':rows[count-1]['seq'] if len(rows)>count else None,
        'retention':{'maxRequests':MAX_REQUESTS,'compressedBodyBytes':BODY_BUDGET,'droppedRequests':dropped},
        'notice':('Prepared inputs blocked locally are separate from dispatched LLM requests.' if kind=='blocked' else 'Only retained direct Studio dispatch attempts are listed. Earlier calls without captured originals are unavailable.')
            if engine=='studio' else 'This native SDK does not expose the final provider request body. Only previously captured direct requests can be inspected.'}


def detail(store,sid,rid):
    store.row(sid);rid=identity(rid)
    row=store.db.execute(SELECT+'WHERE r.session_id=? AND r.request_id=? AND '+VISIBLE,(sid,rid)).fetchone() if exists(store.db) else None
    if not row:raise ProjectFault('Original context request not found.',404)
    result=record(store,row);meta=json.loads(row['metadata'])
    result['context']=meta.get('context')
    if result['context'] is None:
        # 0.12.18 originals already freeze facts/policy; derive only from those
        # original bytes, never from today's settings or a new conversation.
        from request_breakdown import analyze
        result['context']=analyze(body(store,sid,rid).decode(),meta['facts'],meta['contextPolicy']) if result['bodyAvailable'] and (meta.get('contextPolicy') or {}).get('schema')!=4 else None
    call=store.db.execute('SELECT data FROM studio_model_calls WHERE request_id=?',(rid,)).fetchone()
    operation=json.loads(call['data']) if call else {};usage=operation.get('usage');usage_source='provider-response'
    if usage is None:
        usage=((operation.get('error') or {}).get('partial') or {}).get('usage');usage_source='partial-provider-response'
    from studio_usage import numbers
    counts=numbers(usage,meta['protocol'])
    result['usage']={'input':counts['input'],'cachedInput':counts['cachedInput'],'cacheWrite':counts['cacheWrite'],
        'source':usage_source if counts['input'] is not None else 'unavailable'}
    result['policy']=meta['contextPolicy']
    blocked=result['status']=='blocked-before-send'
    condition=BLOCKED if blocked else SENT
    ordering='seq' if blocked else 'dispatch_at'
    position='r.seq' if blocked else '(r.dispatch_at,r.seq)'
    point='?' if blocked else '(?,?)'
    cursor=(row['seq'],) if blocked else (row['dispatch_at'],row['seq'])
    for key,comparison,order in (('older','<','DESC'),('newer','>','ASC')):
        adjacent=store.db.execute('SELECT request_id FROM studio_requests r WHERE r.session_id=? AND '+condition+' AND '+position+comparison+point+' ORDER BY '+ordering+' '+order+',seq '+order+' LIMIT 1',(sid,*cursor)).fetchone()
        result[key]=adjacent['request_id'] if adjacent else None
    result['position']=store.db.execute('SELECT COUNT(*) FROM studio_requests r WHERE r.session_id=? AND '+condition+' AND '+position+'<='+point,(sid,*cursor)).fetchone()[0]
    result['total']=store.db.execute('SELECT COUNT(*) FROM studio_requests r WHERE r.session_id=? AND '+condition,(sid,)).fetchone()[0]
    return result


def chunk(store,sid,rid,offset=0,count=65536):
    rid=identity(rid)
    if type(offset) is not int or offset<0 or type(count) is not int or not 1<=count<=MAX_BODY:
        raise ProjectFault('Invalid original request range.',400)
    store.row(sid)
    sent=store.db.execute('SELECT 1 FROM studio_requests r WHERE r.session_id=? AND r.request_id=? AND '+VISIBLE,(sid,rid)).fetchone() if exists(store.db) else None
    if not sent:raise ProjectFault('Original context request not found.',404)
    raw=body(store,sid,rid)
    if offset>len(raw):raise ProjectFault('Original request range is outside the body.',400)
    end=min(offset+count,len(raw))
    # Base64 preserves arbitrary UTF-8 boundaries and every original byte.
    return {'requestId':rid,'offset':offset,'nextOffset':end if end<len(raw) else None,
        'bytes':len(raw),'base64':base64.b64encode(raw[offset:end]).decode('ascii')}
