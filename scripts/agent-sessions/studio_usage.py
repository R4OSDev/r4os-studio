"""Reported direct-model usage projected onto the existing numeric receipts."""
import json

from session_store import encode
from stats_store import Source, MAX_NUMBER


def count(value):return value if type(value) is int and 0<=value<=MAX_NUMBER else None


def numbers(raw,protocol):
    raw=raw if isinstance(raw,dict) else {}
    chat=protocol=='chat-completions'
    values={'input':count(raw.get('prompt_tokens' if chat else 'input_tokens')),
        'output':count(raw.get('completion_tokens' if chat else 'output_tokens')),
        'total':count(raw.get('total_tokens')),'cachedInput':None,'cacheWrite':None,'reasoningOutput':None}
    if protocol=='messages':
        values['cachedInput']=count(raw.get('cache_read_input_tokens'));values['cacheWrite']=count(raw.get('cache_creation_input_tokens'))
        parts=[values[key] for key in ('input','cachedInput','cacheWrite')]
        values['input']=sum(parts) if all(v is not None for v in parts) and sum(parts)<=MAX_NUMBER else None
        values['total']=None
        details=raw.get('output_tokens_details')
        if isinstance(details,dict):values['reasoningOutput']=count(details.get('thinking_tokens'))
    else:
        input_details=raw.get('prompt_tokens_details' if chat else 'input_tokens_details')
        output_details=raw.get('completion_tokens_details' if chat else 'output_tokens_details')
        if isinstance(input_details,dict):
            values['cachedInput']=count(input_details.get('cached_tokens'));values['cacheWrite']=count(input_details.get('cache_write_tokens'))
        if isinstance(output_details,dict):values['reasoningOutput']=count(output_details.get('reasoning_tokens'))
    for sub,parent in (('cachedInput','input'),('cacheWrite','input'),('reasoningOutput','output')):
        if values[sub] is not None and values[parent] is not None and values[sub]>values[parent]:values[sub]=None
    if values['input'] is not None and values['output'] is not None:
        total=values['input']+values['output']
        if values['total'] is not None and values['total']<total:values['total']=None
        elif values['total'] is None and protocol=='messages' and total<=MAX_NUMBER:values['total']=total
    return values


def record(store,row):
    data=json.loads(row['data']);sid=data['sessionId'];rid=row['request_id']
    if data.get('attempted') is False:return False
    from usage_stats import Usage
    Usage(store,sid).schema()
    if store.db.execute("SELECT 1 FROM statistic_usage WHERE run_id=? AND turn_id=? AND origin='studio-direct-v1'",(row['run_id'],rid)).fetchone():return False
    identity={'source':'studio-model-v1','owner':data['owner'],'session':sid,'run':row['run_id'],'request':rid}
    values=numbers(data.get('usage'),data['selection']['apiProvider']['protocol']) if row['phase']=='completed' else {}
    source=Source(store)
    if any(v is not None for v in values.values()):receipt=source.put(sid,'tokens',identity,values)
    else:receipt=source.put(sid,'gap',identity,{'missing':1})
    selected=data['selection'];connection=selected['apiProvider']
    origin={'schema':1,'providerId':connection['id'],'providerKind':connection['kind'],'configRevision':connection['revision'],
        'credentialRevision':connection['credentialRevision'],'protocol':connection['protocol'],
        'adapter':'studio-'+connection['protocol']+'-v1','requestId':rid,'requestedModel':selected['model'],
        'responseState':row['phase'],'reported':data.get('origin')}
    with store.db:
        store.db.execute('CREATE TABLE IF NOT EXISTS statistic_api_origins(key TEXT PRIMARY KEY,session_id TEXT NOT NULL,run_id TEXT NOT NULL,origin TEXT NOT NULL)')
        store.db.execute('INSERT OR IGNORE INTO statistic_api_origins VALUES (?,?,?,?)',(receipt['key'],sid,row['run_id'],encode(origin)))
        store.db.execute('INSERT OR IGNORE INTO statistic_usage VALUES (?,?,?,?,?)',(receipt['key'],sid,row['run_id'],rid,'studio-direct-v1'))
    return True


def scan(store,sid,limit=200):
    if not store.db.execute("SELECT 1 FROM sqlite_master WHERE name='studio_model_calls'").fetchone():return 0
    from usage_stats import Usage
    Usage(store,sid).schema()
    rows=store.db.execute("""SELECT c.* FROM studio_model_calls c JOIN runs r ON r.id=c.run_id
        WHERE r.session_id=? AND c.phase IN ('completed','unknown','failed')
        AND COALESCE(json_extract(c.data,'$.attempted'),1)!=0
        AND NOT EXISTS(SELECT 1 FROM statistic_usage u WHERE u.run_id=c.run_id AND u.turn_id=c.request_id AND u.origin='studio-direct-v1')
        ORDER BY c.rowid LIMIT ?""",(sid,limit)).fetchall()
    return sum(record(store,row) for row in rows)
