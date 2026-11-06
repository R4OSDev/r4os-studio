"""Purpose-specific image connector facts; no main-model or inference discovery."""
import copy
import json
from pathlib import Path
from api_provider_store import ApiProviders
from native_openai import KIND,BASE,frozen
from store import ProjectFault
from tool_defaults import private_document


def contract():
    return json.loads((Path(__file__).resolve().parents[2]/'shared/image-generation-contract.json').read_text())

def accounts(providers):
    try:
        values=private_document(Path(providers)/'providers.json')
        if not isinstance(values,list) or len(values)>128:raise ValueError()
        return {v['id']:v for v in values if isinstance(v,dict) and isinstance(v.get('id'),str)}
    except (OSError,ValueError,KeyError,TypeError):return {}

def reason(provider,records):
    if provider['kind']!=KIND or provider['baseUrl']!=BASE or provider['protocol']!='responses':return 'This connection has no implemented image generation transport.'
    if not provider['enabled'] or not provider['keyConfigured']:return 'Connection unavailable.'
    record=records.get(provider['id'],{});account=record.get('account') or {};plan=account.get('plan')
    if record.get('connected') is not True:return 'The original OpenAI account is not connected.'
    if not isinstance(plan,str) or plan.lower() in ('','unknown','free'):return 'Image generation needs a confirmed eligible ChatGPT plan.'
    return None

def listing(providers):
    result=[];records=accounts(providers);facts=contract()
    for provider in ApiProviders(providers).listing():
        why=reason(provider,records)
        models=[{'id':facts['modelId'],'name':facts['modelName'],'available':why is None,'reason':why}] if provider['kind']==KIND else []
        result.append({'id':provider['id'],'name':provider['name'],'enabled':why is None,'models':models,'reason':why})
    return result

def freeze(providers,selection):
    provider=ApiProviders(providers).get(selection['providerId']);why=reason(provider,accounts(providers));facts=contract()
    if why:raise ProjectFault(why,409)
    if selection['modelId']!=facts['modelId']:raise ProjectFault('This image model has no implemented generation/edit contract.',409)
    from studio_engine import model_binding
    account=frozen(providers,provider);record=accounts(providers).get(provider['id'],{})
    if record.get('authGeneration')!=account['generation']:raise ProjectFault('The original image account generation changed.',409)
    return {'provider':model_binding(provider),'modelId':facts['modelId'],'modelName':facts['modelName'],
        'account':account,'contract':copy.deepcopy(facts)}

def select(projects,providers,session):
    if not session.get('imageGenerationEnabled',True) or not session.get('permissions',{}).get('studio.generate_image',False):
        return {'available':False,'reason':'Image generation is disabled for this run.'}
    own=None
    try:
        own=freeze(providers,{'providerId':session['providerId'],'modelId':contract()['modelId']})
    except ProjectFault:pass
    if own:return {'available':True,'source':'main-account','settingsRevision':None,'target':own}
    from global_fallback import read
    settings=read(projects,'image-generation')
    if settings['imageGeneration']:
        try:return {'available':True,'source':'fallback','settingsRevision':settings['revision'],'target':freeze(providers,settings['imageGeneration'])}
        except ProjectFault as error:return {'available':False,'reason':str(error),'source':'fallback','settingsRevision':settings['revision']}
    return {'available':False,'reason':'No own image transport or image generation fallback is configured.'}
