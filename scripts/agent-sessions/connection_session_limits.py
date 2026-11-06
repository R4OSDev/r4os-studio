"""The shared account reader, bound to the selected owned Studio session."""
import asyncio
import json
from connection_limits import Limits, KINDS
from session_store import identity
from store import ProjectFault
from zai_session_limits import selection


async def dispatch(host, store, sid, operation, data=None, request_id=None):
    chosen = selection(host, store, sid, KINDS)
    if chosen is None:
        if operation == 'session_connection_limits':
            return None
        raise ProjectFault('This session has no supported account-limit reader.', 409)
    provider, _ = chosen
    limits = Limits(host.config['providers'])
    if operation == 'session_connection_limit_receipt':
        return await asyncio.to_thread(limits.receipt, provider['id'], identity(request_id))
    latest = store.db.execute('SELECT config FROM runs WHERE session_id=? AND busy=1 ORDER BY created_at DESC LIMIT 1', (sid,)).fetchone()
    if latest:
        original = json.loads(latest['config']).get('apiProvider')
        if original and any(original[k] != provider[k] for k in ('id', 'revision', 'credentialRevision')):
            raise ProjectFault('This original run uses another credential revision. Read current limits in provider settings.', 409)
    if operation == 'session_connection_limits':
        return await asyncio.to_thread(limits.listing, provider['id'])
    if operation == 'session_connection_limit_refresh':
        result=await asyncio.to_thread(limits.refresh, provider['id'], data)
        from quota_wait_host import notify
        notify(host,provider['id'])
        return result
    raise ProjectFault('Unknown session account-limit operation.', 400)
