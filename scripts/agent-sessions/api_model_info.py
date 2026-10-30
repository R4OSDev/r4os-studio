"""Explicit API model facts and neutral descriptors for pinned Codex0.163.0.

The descriptor's tool/transport switches are Studio policy. Model context and
reasoning levels are never borrowed from an OpenAI model or guessed from names.
"""
import copy

from store import ProjectFault

CAPABILITIES=('text','functionTools','streaming','imageInput','reasoning','webSearch','imageGeneration','goals')
STATES=('supported','unsupported','unknown')
EFFORTS=('none','minimal','low','medium','high','xhigh')


def model_id(value):
    if (not isinstance(value,str) or not 1<=len(value)<=200
            or any(c.isspace() or ord(c)<33 or ord(c)==127 or 0xd800<=ord(c)<=0xdfff for c in value)):
        raise ProjectFault('Enter an exact model ID without whitespace or control characters.',400)
    return value


def limit(value):
    if value is None:return None
    if type(value) is not int or not 1<=value<=2147483647:
        raise ProjectFault('Enter a positive token limit or leave it unknown.',400)
    return value


def normalized(value):
    if not isinstance(value,dict) or set(value)-{'id','name','contextWindow','maxOutputTokens','capabilities','efforts','defaultEffort'}:
        raise ProjectFault('Invalid API model settings.',400)
    ident=model_id(value.get('id'));name=value.get('name',ident)
    if (not isinstance(name,str) or not 1<=len(name.strip())<=200
            or any(ord(c)<32 or ord(c)==127 or 0xd800<=ord(c)<=0xdfff for c in name)):
        raise ProjectFault('Enter a model name of at most200 characters.',400)
    caps=value.get('capabilities',{})
    if not isinstance(caps,dict) or set(caps)-set(CAPABILITIES) or any(v not in STATES for v in caps.values()):
        raise ProjectFault('Choose supported, unsupported or unknown model capabilities.',400)
    caps={key:caps.get(key,'unknown') for key in CAPABILITIES}
    efforts=value.get('efforts',[]);default=value.get('defaultEffort')
    if (not isinstance(efforts,list) or len(efforts)>6 or any(not isinstance(v,str) or v not in EFFORTS for v in efforts)
            or len(set(efforts))!=len(efforts) or default is not None and default not in efforts):
        raise ProjectFault('Choose only documented reasoning levels and an explicit supported default.',400)
    if caps['reasoning']=='unsupported':
        if efforts not in ([],['none']) or default not in (None,'none'):
            raise ProjectFault('A model without reasoning cannot declare reasoning effort levels.',400)
        efforts=['none'];default='none'
    elif caps['reasoning']=='unknown' and (efforts or default is not None):
        raise ProjectFault('Confirm the reasoning contract before setting effort levels.',400)
    return {'id':ident,'name':name.strip(),'contextWindow':limit(value.get('contextWindow')),
        'maxOutputTokens':limit(value.get('maxOutputTokens')),'capabilities':caps,'efforts':list(efforts),'defaultEffort':default}


def present(value,protocol):
    if not isinstance(value,dict):raise ProjectFault('Invalid stored API model metadata.',503)
    declared=normalized({k:v for k,v in value.items() if k not in ('source',)})
    effective=copy.deepcopy(declared['capabilities']);reasons=[]
    for key in ('text','functionTools','streaming'):
        if declared['capabilities'][key]!='supported':reasons.append({'text':'Text input','functionTools':'Function tools','streaming':'Streaming'}[key]+' is not confirmed.')
    if not declared['efforts'] or declared['defaultEffort'] is None:reasons.append('The reasoning/default-effort contract is not confirmed.')
    if protocol=='chat-completions' and declared['contextWindow'] is None:reasons.append('Chat Completions needs a confirmed context window.')
    for key in ('imageInput','webSearch','imageGeneration','goals'):effective[key]='unsupported'
    return {**declared,'declaredCapabilities':declared['capabilities'],'capabilities':effective,
        'available':not reasons,'unavailableReasons':reasons,'source':copy.deepcopy(value.get('source'))}


def native(value,protocol):
    public=present(value,protocol)
    if not public['available']:return None
    window=public['contextWindow']
    # Required fields follow the public pinned ModelInfo constructor, with
    # explicit neutral Studio controls instead of its272000/auto defaults.
    result={'slug':public['id'],'display_name':public['name'],'description':None,
        # The shipped binary requires this catalog template even when Studio
        # supplies the current explicit baseInstructions at thread start/resume.
        'base_instructions':'Follow the current R4OS Studio instructions and use only the declared tools.',
        'default_reasoning_level':public['defaultEffort'],
        'supported_reasoning_levels':[{'effort':v,'description':v.title()} for v in public['efforts']],
        'shell_type':'disabled','visibility':'list','supported_in_api':True,'priority':99,
        'additional_speed_tiers':[],'service_tiers':[],'default_service_tier':None,
        'available_access_programs':None,'availability_nux':None,'upgrade':None,'model_messages':None,
        'include_skills_usage_instructions':False,'include_plugin_usage_instructions':False,'include_apps_usage_instructions':False,
        'supports_reasoning_summary_parameter':False,'default_reasoning_summary':'none','support_verbosity':False,'default_verbosity':None,
        'apply_patch_tool_type':None,'web_search_tool_type':'text','truncation_policy':{'mode':'bytes','limit':196608},
        'supports_image_detail_original':False,'context_window':window,'max_context_window':window,
        'auto_compact_token_limit':None,'comp_hash':None,'effective_context_window_percent':95,
        'experimental_supported_tools':[],'input_modalities':['text'],'used_fallback_model_metadata':False,
        'supports_search_tool':False,'supports_experimental_context':False,'use_responses_lite':False,
        'supports_reasoning_effort_updates':False,'guardian':None,'node_repl_auto_review_required':False,'node_repl_disabled':True,
        'auto_review_model_override':None,'model_specialty':None,'tool_mode':'direct','multi_agent_version':None,'multi_agent_reasoning_effort':None}
    if protocol=='chat-completions':result['studio_chat']={'schema':1,'systemRole':'system',
        'reasoning':'none' if public['declaredCapabilities']['reasoning']=='unsupported' else 'effort','functionTools':True,'streaming':True}
    return result
