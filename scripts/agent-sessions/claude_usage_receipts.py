"""Original native numeric receipts; cumulative values are never summed as turns."""
import json
import math

from session_store import encode,identity,now
from store import ProjectFault

COUNTS=('input_tokens','output_tokens','cache_creation_input_tokens','cache_read_input_tokens')
MODEL_COUNTS=('inputTokens','outputTokens','cacheReadInputTokens','cacheCreationInputTokens','contextWindow','maxOutputTokens')


def counts(value,fields):
    if value is None:return None
    if not isinstance(value,dict):raise ProjectFault('The native usage shape is unqualified. No total was invented.',409)
    result={}
    for field in fields:
        number=value.get(field)
        if number is not None and (type(number) is not int or not 0<=number<=2**63-1):
            raise ProjectFault('The native token counter is unqualified. No total was invented.',409)
        result[field]=number
    return result


def record(worker,result):
    native_id=identity(result['uuid']);frozen=worker.config['engine']['claude']
    if result.get('session_id')!=frozen['nativeSessionId']:raise ProjectFault('The native usage session binding changed.',409)
    models=result.get('modelUsage');projected=None
    if models is not None:
        if not isinstance(models,dict) or len(models)>256:raise ProjectFault('The native model-usage shape changed.',409)
        projected={}
        for model,value in models.items():
            if not isinstance(model,str) or not 1<=len(model)<=200 or any(ord(c)<32 for c in model):raise ProjectFault('Invalid native usage model.',409)
            if not isinstance(value,dict):raise ProjectFault('The native model-usage counters are unqualified.',409)
            selected=counts(value,MODEL_COUNTS);estimate=value.get('costUSD')
            if estimate is not None and (type(estimate) not in (int,float) or not math.isfinite(estimate) or estimate<0):
                raise ProjectFault('The native estimated cost shape changed.',409)
            projected[model]={**selected,'nativeEstimatedListPriceUSD':estimate}
    payload={'schema':1,'engine':'claude-code','runtime':frozen,'studioRequestId':worker.row['request_id'],'runId':worker.run_id,
        'nativeResultId':native_id,'nativeTurnId':None,'subtype':result.get('subtype'),
        'nativeMainLoopUsage':counts(result.get('usage'),COUNTS),'nativeCumulativeModelUsage':projected,
        'semantics':'native cumulative query/session snapshots, including possible resumed history; not summed',
        'billing':'native list-price estimate is not a subscription remainder or invoice',
        'totalsQualified':False}
    db=worker.store.db
    with db:
        db.execute('CREATE TABLE IF NOT EXISTS claude_usage_receipts(session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,native_result_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,request_id TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL)')
        old=db.execute('SELECT payload FROM claude_usage_receipts WHERE native_result_id=?',(native_id,)).fetchone()
        if old:
            if json.loads(old[0])!=payload:raise ProjectFault('The original native usage receipt conflicts. Existing totals were preserved.',409)
            return payload
        db.execute('INSERT INTO claude_usage_receipts VALUES (?,?,?,?,?,?)',
            (worker.session_id,native_id,worker.run_id,worker.row['request_id'],encode(payload),now()))
    return payload
