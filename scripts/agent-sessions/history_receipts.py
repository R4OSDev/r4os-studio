"""Read the exact dispatch that produced an immutable assistant record."""
import json

from request_capture import body, exists
from store import ProjectFault


def original_input(store, sid, record):
    origin = record.get('origin', {})
    rid = origin.get('studioRequestId')
    if not rid or not exists(store.db):
        return None
    row = store.db.execute('''SELECT r.sha256,r.metadata,c.data FROM studio_requests r
        JOIN studio_model_calls c ON c.request_id=r.request_id AND c.run_id=r.run_id
        WHERE r.session_id=? AND r.run_id=? AND r.request_id=? AND r.dispatch_at IS NOT NULL
        AND c.phase='completed' ''', (sid, record.get('runId'), rid)).fetchone()
    if not row:
        return None
    try:
        meta = json.loads(row['metadata'])
        call = json.loads(row['data'])
        owner = {'type': store.owner_type, 'id': store.owner_id}
        selection = origin.get('selection', {})
        if (call.get('requestId') != rid or call.get('sessionId') != sid or call.get('runId') != record.get('runId')
                or call.get('owner') != owner or meta.get('owner') != owner or meta.get('purpose') != 'conversation'
                or call.get('purpose') != 'conversation' or call.get('attempted') is not True
                or call.get('requestSha256') != row['sha256'] or call.get('processEnd', {}).get('confirmed') is not True
                or call.get('processEnd', {}).get('exitCode') != 0 or not 200 <= (meta.get('httpStatus') or 0) < 300
                or call.get('origin', {}).get('providerResponseId') != origin.get('providerResponseId')
                or not origin.get('providerResponseId') or meta.get('providerId') != selection.get('providerId')
                or meta.get('model') != selection.get('model')
                or meta.get('protocol') != selection.get('connection', {}).get('protocol')):
            return None
        return json.loads(body(store, sid, rid))
    except (ProjectFault, ValueError, TypeError, KeyError, RecursionError):
        return None
