"""Freeze native Claude identity before accepting an original Studio request.

Public model eligibility is supplied separately by the qualified catalog. This
module grants neither model access nor subscription/overage admission.
"""
import uuid

from claude_history import ClaudeHistory
from claude_provider_store import ClaudeProviders,account_identity
from claude_run_leases import ClaudeRunLeases
from claude_runtime import installed
from session_store import encode,identity
from store import ProjectFault


def engine(providers,tool_profile):
    runtime=installed(providers)
    return {'kind':'claude-code','profile':tool_profile,'version':runtime['version'],
        'sha256':runtime['sha256'],'available':True}


def freeze(store,sid,data,providers,snapshot,queue_context=None):
    if snapshot['engine'].get('kind')!='claude-code':return
    provider=ClaudeProviders(providers).get(snapshot['providerId'])
    history=ClaudeHistory(store,sid).get();runtime=history['runtime']
    queue_live=False
    if queue_context is not None:
        from claude_messages import context
        if context(store,sid,providers)!=queue_context:
            raise ProjectFault('The original Claude queue selection changed before capture.',409)
        queue_live=history['phase'] in ('opening','active') and queue_context['source'] is not None
    if (provider['status']!='connected' or provider['runtimeProfileId']!=runtime['runtimeProfileId']
        or account_identity(provider['account'])!=history['accountIdentity'] or not history['accountIdentity']
        or history['phase'] not in ('allocated','ready') and not queue_live):
        raise ProjectFault('The original Claude account/history is unavailable or unconfirmed. It was preserved.',409)
    if (data.get('mode')=='goal' or any(snapshot.get(key) for key in
        ('goalExecution','apiProvider','nativeImageGeneration','attachments','webSearchEnabled','fastMode'))):
        raise ProjectFault('This native Claude input/lifecycle capability has not been qualified.',409)
    snapshot['claudeProvider']={'providerId':provider['id'],'providerRevision':provider['revision'],
        'runtimeProfileId':provider['runtimeProfileId'],'accountIdentity':history['accountIdentity']}
    from claude_auth_store import AuthStore
    catalog=AuthStore(providers).latest_catalog(provider['id'])
    model=next((m for m in catalog['models'] if m['id']==snapshot['model']),None) if catalog else None
    if model:
        snapshot['claudeModel']={'id':model['id'],'resolvedModel':model['resolvedModel'],'efforts':model['efforts'],
            'effort':snapshot['effort'],'imageInput':model['imageInputs'],'contextWindow':model['contextWindow'],
            'catalogRequestId':catalog['requestId'],'runtimeProfileId':catalog['runtimeProfileId']}
    snapshot['claudeRunId']=str(uuid.uuid5(uuid.NAMESPACE_URL,'r4os-studio-claude-run:'+encode(
        {'owner':{'type':store.owner_type,'id':store.owner_id},'session':identity(sid),'request':identity(data['requestId'])})))


def reserve(store,sid,run_id,request_id,providers,snapshot):
    original=ClaudeHistory(store,sid).get()
    return ClaudeRunLeases(providers).reserve({**snapshot['claudeProvider'],'studioSessionId':sid,
        'ownerType':store.owner_type,'ownerId':store.owner_id,'runId':run_id,'requestId':request_id,
        'nativeSessionId':original['runtime']['nativeSessionId']})
