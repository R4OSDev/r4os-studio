"""Pinned native subscription observations; never infer quota from token usage."""
import datetime
import math
import time

from claude_provider_store import account_identity
from session_store import now
from store import ProjectFault

SOURCE='claude-code-2.1.312/sdk-0.3.312/get_usage'
WINDOWS=(('five_hour','5-hour','account'),('seven_day','Weekly','account'),
    ('seven_day_oauth_apps','Weekly OAuth apps','oauth-apps'),
    ('seven_day_opus','Weekly Opus','opus'),('seven_day_sonnet','Weekly Sonnet','sonnet'))


def number(value,maximum=100):
    return type(value) in (int,float) and math.isfinite(value) and 0<=value<=maximum


def reset(value):
    if value is None:return None
    if not isinstance(value,str) or len(value)>64:raise ValueError('Invalid native reset time.')
    parsed=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:raise ValueError('The native reset timezone is missing.')
    return parsed.astimezone(datetime.timezone.utc).isoformat()


def window(key,label,scope,value):
    if not isinstance(value,dict):raise ValueError('Invalid native quota window.')
    used=value.get('utilization')
    if used is not None and not number(used):raise ValueError('Invalid native usage percentage.')
    return {'id':key,'label':label,'scope':scope,'usedPercent':used,
        'remainingPercent':None if used is None else 100-used,'resetsAt':reset(value.get('resets_at'))}


def usage_sample(value,provider,request_id,received_at=None):
    """Project only this pinned control reply, with its receipt time and scope.

    Receipt time is not an invented server timestamp. The SDK owns the request,
    OAuth/refresh and any native cache. No raw credentials or behaviors persist.
    """
    received_at=received_at or now()
    sample={'schema':1,'source':SOURCE,'receivedAt':received_at,'providerId':provider['id'],
        'providerRevision':provider['revision'],'accountIdentity':account_identity(provider.get('account')),
        'requestId':request_id,'plan':None,'coverage':'unavailable','windows':[],
        'extraUsageEnabled':None,'serverMetersReported':False,'message':'Native subscription usage is unavailable.'}
    if (not isinstance(value,dict) or value.get('subscription_type') not in ('pro','max')
        or value.get('rate_limits_available') is not True or not sample['accountIdentity']
        or provider.get('status')!='connected' or value['subscription_type']!=provider['account']['plan']):return sample
    sample['plan']=value['subscription_type'];limits=value.get('rate_limits')
    if not isinstance(limits,dict):return sample
    try:
        for key,label,scope in WINDOWS:
            if limits.get(key) is not None:sample['windows'].append(window(key,label,scope,limits[key]))
        rows=limits.get('limits')
        if rows is not None:
            if not isinstance(rows,list) or len(rows)>64:raise ValueError()
            sample['serverMetersReported']=True
            for index,row in enumerate(rows):
                if (not isinstance(row,dict) or not all(isinstance(row.get(k),str) and 0<len(row[k])<=120 and not any(ord(c)<32 for c in row[k]) for k in ('kind','group','severity'))
                    or type(row.get('is_active')) is not bool or not number(row.get('percent'))):raise ValueError()
                scope=row.get('scope');labels=[]
                if scope is not None:
                    if not isinstance(scope,dict):raise ValueError()
                    for key in ('model','surface'):
                        if scope.get(key) is not None:
                            label=scope[key].get('display_name') if isinstance(scope[key],dict) else None
                            if not isinstance(label,str) or not 1<=len(label)<=120 or any(ord(c)<32 for c in label):raise ValueError()
                            labels.append(label)
                label=' · '.join(labels) or row['kind'].replace('_',' ').capitalize()
                reported=window('native-meter-'+str(index),label,'native-meter',{'utilization':row['percent'],'resets_at':row.get('resets_at')})
                reported.update(kind=row['kind'],group=row['group'],severity=row['severity'],active=row['is_active'])
                sample['windows'].append(reported)
        scoped=limits.get('model_scoped')
        if scoped is not None:
            if not isinstance(scoped,list) or len(scoped)>64:raise ValueError()
            for index,entry in enumerate(scoped):
                if not isinstance(entry,dict) or not isinstance(entry.get('display_name'),str) or not 1<=len(entry['display_name'])<=120 or any(ord(c)<32 for c in entry['display_name']):raise ValueError()
                sample['windows'].append(window('model-scoped-'+str(index),entry['display_name'],'native-model-label',entry))
        extra=limits.get('extra_usage')
        if isinstance(extra,dict) and type(extra.get('is_enabled')) is bool:sample['extraUsageEnabled']=extra['is_enabled']
    except (ValueError,TypeError,OverflowError):
        sample.update(coverage='unavailable',windows=[],extraUsageEnabled=None,serverMetersReported=False,message='The pinned native usage schema could not be confirmed.')
        return sample
    complete=all(any(w['id']==key and w['usedPercent'] is not None for w in sample['windows']) for key in ('five_hour','seven_day'))
    sample['coverage']='available' if complete else 'partial'
    sample['message']='Reported by the native Claude subscription control.' if complete else 'Some native subscription windows are unknown.'
    return sample


def event_sample(value):
    """The pinned rate-limit event uses fractions and epoch seconds, unlike get_usage."""
    if not isinstance(value,dict) or value.get('status') not in ('allowed','allowed_warning','rejected'):raise ValueError('Unknown native rate-limit event.')
    used=value.get('utilization');epoch=value.get('resetsAt')
    if used is not None and not number(used,1):raise ValueError('Unknown native rate-limit utilization.')
    if epoch is not None and (not number(epoch,253402300799) or epoch<=0):raise ValueError('Unknown native rate-limit reset epoch.')
    return {'schema':1,'source':'claude-code-2.1.312/sdk-0.3.312/rate_limit_event','receivedAt':now(),
        'status':value['status'],'scope':value.get('rateLimitType') if value.get('rateLimitType') in
        ('five_hour','seven_day','seven_day_opus','seven_day_sonnet','seven_day_overage_included','overage') else None,
        'usedPercent':None if used is None else used*100,
        'resetsAt':None if epoch is None else datetime.datetime.fromtimestamp(epoch,datetime.timezone.utc).isoformat(),
        'overageEnabled':value.get('overageEnabled') if type(value.get('overageEnabled')) is bool else None,
        'usingOverage':value.get('isUsingOverage') is True or value.get('overageInUse') is True}


def admission(sample,provider,native_auth,sdk_account,binding,started_at,model_scope=None):
    """Fresh original native observations only; never activate extra usage.

    The pinned client exposes no qualified per-send overage-disable switch.
    Account-level extra usage must therefore be explicitly disabled and remain
    disabled. Hiding /extra-usage or interrupting after a charge is no guard.
    """
    from claude_provider_store import valid_account
    from claude_auth import status_result
    reason='The original native subscription/limit proof is unavailable.'
    deny=lambda message,code='proof_unavailable':{'allowed':False,'reason':message,'reasonCode':code}
    if not number(started_at,10**12) or not 0<=time.time()-started_at<=20:return deny('The native limit observation is stale. Check subscription limits again.')
    if not isinstance(native_auth,dict) or set(native_auth)!={'output','returncode'}:return deny(reason)
    try:status,account,_=status_result(native_auth['output'],native_auth['returncode'])
    except ProjectFault:return deny(reason)
    if (status!='connected' or not valid_account(account,status) or account_identity(account)!=account_identity(provider.get('account'))
        or account['plan']!=provider['account']['plan'] or provider['status']!='connected'
        or sample.get('accountIdentity')!=account_identity(account) or sample.get('providerId')!=provider['id']
        or sample.get('providerRevision')!=provider['revision'] or sample.get('source')!=SOURCE):return deny(reason)
    plan={'Claude Pro':'pro','Claude Max':'max','pro':'pro','max':'max'}.get(sdk_account.get('subscriptionType'))
    if (sdk_account.get('apiProvider')!='firstParty' or sdk_account.get('apiKeySource') not in (None,'none')
        or sdk_account.get('tokenSource') not in (None,'claude.ai') or plan!=account['plan']
        or sdk_account.get('email')!=account['email']):return deny(reason)
    if sample.get('extraUsageEnabled') is not False:return deny('Paid extra usage is enabled or unconfirmed. Disable it in your Claude account before using this subscription.','overage_unconfirmed')
    if sample.get('serverMetersReported') is not True:return deny('Fresh native server meters could not be confirmed. No model prompt was submitted.')
    if sample.get('coverage')!='available':return deny('Native subscription windows are incomplete. No model prompt was submitted.')
    for row in sample['windows']:
        relevant=(row['scope']=='account' or row['scope']==model_scope or row['scope'] in ('oauth-apps','native-model-label','native-meter')
            or model_scope not in ('opus','sonnet') and row['scope'] in ('opus','sonnet'))
        if relevant and row['usedPercent'] is not None and row['usedPercent']>=100:
            return deny('The reported '+row['label']+' subscription window is exhausted. Check its reset time and resume explicitly.','subscription_limit')
    import uuid
    return {'allowed':True,'extraUsageDisabled':True,'authMethod':'claude.ai','apiProvider':'firstParty',
        'subscriptionType':plan,'providerId':provider['id'],'nativeSessionId':binding['nativeSessionId'],
        'model':binding['model'],'admissionId':str(uuid.uuid4()),'expiresAt':time.time()*1000+10000}
