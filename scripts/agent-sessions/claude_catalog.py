"""Native client model facts; advertisement is not subscription/overage proof."""
import re

from claude_provider_store import account_identity
from claude_runtime import profile,text_profile,input_profile
from session_store import now
from store import ProjectFault

EFFORTS=('low','medium','high','xhigh','max')


def identifier(value):
    return isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:\[\]-]{0,199}',value) is not None


def display(value,maximum):
    return isinstance(value,str) and 0<len(value)<=maximum and not any(ord(c)<32 or ord(c)==127 for c in value)


def normalize(rows,provider,request_id):
    if not isinstance(rows,list) or not 1<=len(rows)<=256:raise ProjectFault('The native model catalog is unavailable.',503)
    adapter=text_profile();inputs=input_profile();qualified=provider.get('status')=='connected' and bool(account_identity(provider.get('account')))
    models={}
    for row in rows:
        if (not isinstance(row,dict) or not identifier(row.get('value')) or not display(row.get('displayName'),200)
            or not display(row.get('description'),4000) or row.get('resolvedModel') is not None and not identifier(row['resolvedModel'])):
            raise ProjectFault('The pinned native model catalog has an unknown shape. Existing selections were preserved.',503)
        for field in ('supportsEffort','supportsAdaptiveThinking','supportsFastMode','supportsAutoMode'):
            if field in row and type(row[field]) is not bool:raise ProjectFault('A native model capability has an unknown shape.',503)
        efforts=row.get('supportedEffortLevels')
        if efforts is not None and (not isinstance(efforts,list) or len(efforts)>5 or any(e not in EFFORTS for e in efforts) or len(set(efforts))!=len(efforts)):
            raise ProjectFault('The native effort contract changed. Existing selections were preserved.',503)
        canonical=row.get('resolvedModel');key=canonical or row['value']
        fact={'id':key,'nativeValue':row['value'],'resolvedModel':canonical,'name':row['displayName'],
            'description':row['description'],'aliases':[row['value']],
            'efforts':['',*efforts] if row.get('supportsEffort') is True and efforts else [''],
            'defaultEffort':'','supportsEffort':row.get('supportsEffort'),
            'adaptiveThinking':row.get('supportsAdaptiveThinking'),'fastModeAdvertised':row.get('supportsFastMode'),
            'fastModeAvailable':False,'contextWindow':None,'imageInputs':'unknown','imageSource':'unreported','inputModalities':['text'],
            'available':qualified and canonical is not None,
            'unavailableReasons':[] if qualified else ['Connect and check the native Claude subscription before selecting this model.'],
            'source':'native-supportedModels','entitlement':'not-verified-by-model-advertisement'}
        if canonical is None:fact['unavailableReasons'].append('The native client did not resolve this model to a fixed wire identifier.')
        if qualified and canonical and canonical.startswith('claude-'):
            fact.update(imageInputs='supported',imageSource='studio-input-profile',inputModalities=['text','image'],inputProfileId=inputs['id'])
        if key in models:
            previous=models[key];aliases=previous['aliases']+[row['value']]
            # Preserve aliases as provenance, while preferring a named row to
            # the native default label. Execution will use its resolved ID.
            if previous['nativeValue']=='default' and row['value']!='default':models[key]=fact
            models[key]['aliases']=list(dict.fromkeys(aliases))
        else:models[key]=fact
    return {'schema':1,'source':'claude-code-2.1.312/sdk-0.3.312/supportedModels','receivedAt':now(),
        'providerId':provider['id'],'providerRevision':provider['revision'],'accountIdentity':account_identity(provider.get('account')),
        'runtimeProfileId':profile()['id'],'sessionProfileId':adapter['id'],'requestId':request_id,'models':list(models.values()),
        'sessionModelsQualified':qualified}
