"""Keep exact unresolved tool batches outside a summarized context prefix."""
import hashlib

from conversation import identifier
from model_transport import dumps
from session_store import identity
from store import ProjectFault

MAX_RECORDS = 8192
FIELDS = ('seq', 'session_id', 'run_id', 'record_id', 'kind', 'role', 'content', 'origin', 'through_seq', 'created_at')


def digest(row):
    return hashlib.sha256(dumps({key: row[key] for key in FIELDS}).encode()).hexdigest()


def references(checkpoint):
    value = (checkpoint or {}).get('origin', {}).get('retainedContextRecords', [])
    if not isinstance(value, list) or len(value) > MAX_RECORDS:
        raise ProjectFault('The checkpoint retained-record index is invalid. Original history was preserved.', 409)
    return value


def load(store, sid, checkpoint, present):
    result = []; previous = 0; pending = set()
    for ref in references(checkpoint):
        if (not isinstance(ref, dict) or set(ref) != {'sequence', 'recordId', 'runId', 'sha256'}
                or type(ref['sequence']) is not int or not previous < ref['sequence'] <= checkpoint['throughSequence']
                or not isinstance(ref['sha256'], str) or len(ref['sha256']) != 64):
            raise ProjectFault('The checkpoint retained-record binding is invalid.', 409)
        identity(ref['runId']); identifier(ref['recordId'])
        row = store.db.execute("SELECT * FROM conversation_records WHERE session_id=? AND seq=? AND run_id=? AND record_id=? AND kind='message'",
            (sid, ref['sequence'], ref['runId'], ref['recordId'])).fetchone()
        if row is None or digest(row) != ref['sha256']:
            raise ProjectFault('An original retained context record is missing or changed. No tool was repeated.', 409)
        value = present(row)
        for part in value['content']:
            key = (value['runId'], part.get('callId'))
            if part['type'] == 'tool_call':
                if key in pending: raise ProjectFault('The retained context has duplicate tool calls.', 409)
                pending.add(key)
            elif part['type'] == 'tool_result':
                if key not in pending: raise ProjectFault('The retained context has an unpaired tool result.', 409)
                pending.remove(key)
        result.append(value); previous = ref['sequence']
    if pending: raise ProjectFault('The retained context has open tool calls.', 409)
    return result


def reference(worker, record):
    row = worker.store.db.execute("SELECT * FROM conversation_records WHERE session_id=? AND seq=? AND run_id=? AND record_id=? AND kind='message'",
        (worker.session_id, record['sequence'], record['runId'], record['id'])).fetchone()
    if row is None or row['role'] != record['role']:
        raise ProjectFault('The original checkpoint record is unavailable.', 409)
    return {'sequence': row['seq'], 'recordId': row['record_id'], 'runId': row['run_id'], 'sha256': digest(row)}


def choices(worker, active, checkpoint, byte_limit):
    """Store shared prefix data and the admissible whole-group boundaries."""
    from context_results import has_uncertain_result
    from context_policy import optimized
    from summary_context import record_view
    config=getattr(worker,'config',{})
    projected=optimized(config.get('contextPolicy'),3)
    archive=worker if projected and config.get('contextResultProtocol')==1 and config.get('permissions',{}).get('studio.read_context_result') else None
    consumed = max((r.get('sequence', 0) for r in active if r.get('role') == 'assistant'
        and r.get('origin', {}).get('providerResponseId')), default=0)
    data = []; retained = []; ends = []; size = 0; pending = set(); group = []; confirmed = False
    for record in active:
        group.append(record)
        for part in record['content']:
            key = (record.get('runId'), part.get('callId'))
            if part['type'] == 'tool_call': pending.add(key)
            elif part['type'] == 'tool_result': pending.discard(key)
        if pending: continue
        sequence = max((r.get('sequence', 0) for r in group), default=0)
        if sequence >= consumed: break
        plain = ([record_view(r,archive) for r in group] if projected else
                 [{**r, 'content': [p for p in r['content'] if p['type'] != 'provider']} for r in group])
        amount = len(dumps(plain).encode())
        if any(has_uncertain_result(r) for r in group) or amount > byte_limit:
            retained.extend(reference(worker, r) for r in group if 'sequence' in r)
        else:
            if size + amount > byte_limit: break
            data.extend(plain); size += amount
            confirmed = confirmed or any(r['role'] == 'assistant' and r.get('origin', {}).get('providerResponseId')
                and any(p['type'] == 'provider' for p in r['content']) for r in group)
        if sequence and confirmed and (not checkpoint or sequence > checkpoint['throughSequence']):
            ends.append((sequence,len(data),len(retained)))
        group = []
    if len(retained) > MAX_RECORDS:
        raise ProjectFault('Too many original tool observations need exact retention. Original history was preserved.', 409)
    return data, retained, ends


def select(data, retained, end):
    through, records, originals = end
    return through, data[:records], retained[:originals]


def plan(worker, active, checkpoint, byte_limit):
    data, retained, ends = choices(worker,active,checkpoint,byte_limit)
    return select(data,retained,ends[-1]) if ends else None
