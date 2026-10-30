"""Read qualified, revision-bound native API catalogs; never subscription auth."""
import copy
import json
from pathlib import Path

from api_provider_store import ApiProviders, private
from session_store import identity
from store import ProjectFault


def catalog(providers,provider):
    if provider['kind']=='openrouter':
        from openrouter_policy import unavailable
        if unavailable(provider):return []
    from api_catalog import Catalogs
    models=Catalogs(providers).native_models(provider['id'])
    if models is not None:return models
    ident=identity(provider['id']);root=ApiProviders(providers).root/'Models';path=root/(ident+'.json')
    if not path.exists() and not path.is_symlink():return []
    try:
        private(root,directory=True);private(path)
        if path.stat().st_size>1048576:raise ValueError()
        value=json.loads(path.read_text())
        if (not isinstance(value,dict) or set(value)!={'schema','providerId','configRevision','models'} or type(value['schema']) is not int or value['schema']!=1
                or type(value['configRevision']) is not int
                or value['providerId']!=ident or value['configRevision']!=provider['revision']
                or not isinstance(value['models'],list) or not 1<=len(value['models'])<=128):raise ValueError()
        seen=set()
        for model in value['models']:
            if not isinstance(model,dict):raise ValueError()
            slug=model.get('slug')
            if (not isinstance(slug,str) or not 1<=len(slug)<=200 or any(ord(c)<33 or ord(c)==127 or 0xd800<=ord(c)<=0xdfff for c in slug)
                    or slug in seen or model.get('use_responses_lite') is not False
                    or model.get('input_modalities')!=['text']):raise ValueError()
            seen.add(slug)
        models=copy.deepcopy(value['models'])
        if provider['kind']=='openrouter':models=[model for model in models if model.get('studio_chat',{}).get('reasoning')=='none']
        return models
    except (OSError,ValueError,TypeError,KeyError):
        raise ProjectFault('The API model catalog is unqualified or belongs to an older configuration. Refresh its model metadata before starting work.',409) from None


def connection(providers,ident):
    try:return ApiProviders(providers).get(ident)
    except ProjectFault as error:
        if error.code==404:return None
        raise


def future_run_id(store,sid,request_id):
    import uuid
    from session_store import encode
    return str(uuid.uuid5(uuid.NAMESPACE_URL,'r4os-studio-api-run:'+encode(
        {'owner':{'type':store.owner_type,'id':store.owner_id},'session':identity(sid),'request':identity(request_id)})))


def chat_policy(model,effort):
    policy=model.get('studio_chat')
    if (not isinstance(policy,dict) or set(policy)!={'schema','systemRole','reasoning','functionTools','streaming'}
            or type(policy['schema']) is not int or policy['schema']!=1 or policy['systemRole'] not in ('system','developer')
            or policy['reasoning'] not in ('none','effort') or policy['functionTools'] is not True or policy['streaming'] is not True
            or model.get('supports_reasoning_summary_parameter') is not False or model.get('default_reasoning_summary') not in (None,'none')
            or model.get('support_verbosity') is not False or model.get('default_verbosity') is not None
            or type(model.get('context_window')) is not int or model['context_window']<=0
            or policy['reasoning']=='none' and effort!='none'):
        raise ProjectFault('This Chat Completions model lacks qualified text/function streaming, context or reasoning semantics. Select a qualified model; no request was started.',409)
    return copy.deepcopy(policy)


def freeze(store,sid,data,providers,snapshot):
    session=store.get(sid);selected=session['engine'].get('api')
    if not selected:return
    provider=connection(providers,snapshot['providerId'])
    if provider is None:raise ProjectFault('The original API connection is unavailable.',409)
    if not provider['enabled']:raise ProjectFault('This API connection is disconnected.',409)
    if (not selected or selected['providerId']!=provider['id'] or selected['baseUrl']!=provider['baseUrl']
            or selected['protocol']!=provider['protocol']):
        raise ProjectFault('The API connection identity changed. Create a new session; the existing conversation was preserved.',409)
    if data.get('mode')=='goal':raise ProjectFault('Native Goal execution is not qualified for this API model.',409)
    if session.get('webSearchEnabled',False) or session.get('imageGenerationEnabled',False) or session.get('fastMode',False):
        raise ProjectFault('Hosted web/image generation and Fast Mode are not qualified for this API model. Review its explicit session settings.',409)
    models=catalog(providers,provider);model=next((m for m in models if m['slug']==snapshot['model']),None)
    if model is None:raise ProjectFault('The selected API model has no current qualified catalog entry.',409)
    if provider['protocol']=='chat-completions':snapshot['apiChat']=chat_policy(model,snapshot['effort'])
    model.pop('studio_chat',None)
    snapshot['apiProvider']={key:provider[key] for key in ('id','kind','baseUrl','protocol','auth','revision','credentialRevision')}
    if provider['kind']=='openrouter':snapshot['apiProvider']['openrouter']=copy.deepcopy(provider['openrouter'])
    snapshot['apiModels']={'models':[model]};snapshot['apiRunId']=future_run_id(store,sid,data['requestId'])
    snapshot['nativeGoalPreparation']=False
