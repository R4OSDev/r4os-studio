"""Current declared image-to-text facts; no tools requirement or model probes."""
import copy
from api_provider_store import ApiProviders
from api_catalog import Catalogs
from api_model_info import reasoning_facts
from studio_engine import model_binding
from store import ProjectFault


def output_budget(model):
    # This is our bounded helper policy, never a reported provider maximum.
    return min(8192,model.get('maxOutputTokens') or 8192,max(1,model['contextWindow']//4))


def reason(provider, listing, model):
    if not provider['enabled'] or provider['auth'] != 'none' and not provider['keyConfigured']: return 'Connection unavailable.'
    if provider['protocol'] not in ('responses','chat-completions','messages') or listing['stale']: return 'Current transport/model metadata unavailable.'
    caps = model['declaredCapabilities']
    if any(caps[k] != 'supported' for k in ('text','imageInput','streaming')): return 'Text, image input and streaming must be confirmed.'
    if not model['contextWindow']: return 'A confirmed context limit is required.'
    if model['defaultEffort'] is None or model['defaultEffort'] not in model['efforts']: return 'Documented model default unavailable.'
    if caps['reasoning'] == 'unknown': return 'Reasoning contract unavailable.'
    if caps['reasoning'] == 'supported':
        if 'reasoning' in model or model.get('reasoningMetadata'):
            try:
                facts = reasoning_facts(model['reasoning'])
                if not facts or model.get('reasoningMetadata') and model['reasoningMetadata']['facts'] != facts: return 'Current documented reasoning facts must be applied.'
            except (KeyError, ProjectFault): return 'Documented reasoning facts unavailable.'
        if provider['protocol'] == 'messages':
            value = model.get('messages', {})
            if value.get('thinkingType') not in ('adaptive','enabled') and not (model['defaultEffort'] == 'none' and value.get('thinkingDisabled')):
                return 'Messages thinking/default contract unavailable.'
            if value.get('thinkingType') == 'enabled' and provider['kind'] != 'zai-coding-plan' and not 1024 <= value.get('thinkingBudget',0) < output_budget(model):
                return 'Messages thinking budget exceeds the bounded helper output.'
    from api_server import unavailable
    errors = unavailable(provider,model)
    if provider['kind'] == 'openrouter':
        from openrouter_policy import unavailable as routing_unavailable
        errors += routing_unavailable(provider,model)
    return errors[0] if errors else None


def listing(providers):
    result = []
    for provider in ApiProviders(providers).listing():
        models = []; error = None
        try:
            catalog = Catalogs(providers).listing(provider['id'])
            for model in catalog['models']:
                why = reason(provider,catalog,model)
                models.append({'id':model['id'],'name':model['name'],'available':why is None,'reason':why})
        except ProjectFault: error = 'Current model metadata unavailable.'
        result.append({'id':provider['id'],'name':provider['name'],'enabled':provider['enabled'],'models':models,'reason':error})
    return result


def freeze(providers, selection):
    provider = ApiProviders(providers).get(selection['providerId'])
    catalog = Catalogs(providers).listing(provider['id'])
    model = next((m for m in catalog['models'] if m['id'] == selection['modelId']),None)
    why = 'The saved Vision model is unavailable.' if model is None else reason(provider,catalog,model)
    if why: raise ProjectFault(why,409)
    return {'provider':model_binding(provider),'model':copy.deepcopy(model),'catalogRevision':catalog['revision'],
            'effort':model['defaultEffort']}
