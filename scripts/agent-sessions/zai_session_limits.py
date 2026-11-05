"""Resolve subscription reads to the actual owned project/skill session."""
import json
from api_provider_store import ApiProviders
from session_store import identity
from store import ProjectFault
from zai_quota import Quota


def selection(host,store,sid,kinds=('zai-coding-plan',)):
    session=store.get(identity(sid))
    if not session['engine'].get('api'):return None
    provider=ApiProviders(host.config['providers']).get(session['providerId'])
    if provider['kind'] not in kinds:return None
    original=session['engine']['api']
    if original.get('providerId')!=provider['id'] or any(original.get(k)!=provider.get(k) for k in ('baseUrl','protocol')):
        raise ProjectFault('This session has a different original subscription connection.',409)
    return provider,session['model']


async def dispatch(host,store,sid,operation,data=None,request_id=None):
    chosen=selection(host,store,sid)
    if chosen is None:
        if operation=='session_zai_limits':return None
        raise ProjectFault('This session does not use a Z.AI subscription.',409)
    provider,model=chosen;quota=Quota(host.config['providers'])
    if operation=='session_zai_limit_receipt':return quota.receipt(provider['id'],identity(request_id))
    latest=store.db.execute('SELECT config FROM runs WHERE session_id=? AND busy=1 ORDER BY created_at DESC LIMIT 1',(sid,)).fetchone()
    if latest:
        original=json.loads(latest['config']).get('apiProvider')
        if original and any(original[k]!=provider[k] for k in ('id','revision','credentialRevision')):
            raise ProjectFault('Connection credentials changed during this original run. Its subscription scope is preserved; read current account limits in provider settings.',409)
    if operation=='session_zai_limits':return quota.listing(provider['id'],model)
    if operation=='session_zai_limit_refresh':
        from zai_quota_host import start
        return await start(host,provider['id'],data)
    raise ProjectFault('Unsupported subscription limit operation.',400)
