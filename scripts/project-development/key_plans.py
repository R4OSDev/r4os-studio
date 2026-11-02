"""One bounded original own-client key plan, timed by the guest watchdog."""
import asyncio
from contracts import DevelopmentFault, UnconfirmedGuestEffect
from gui_input import key
from jobs import now
from layout import save


def steps(value):
    if not isinstance(value,list) or not 1 <= len(value) <= 32:
        raise DevelopmentFault('A key plan needs 1..32 normal key/codepoint steps.',400)
    result=[];previous=-1
    for step in value:
        if not isinstance(step,dict) or set(step) not in ({'key','atMilliseconds'},{'codepoint','atMilliseconds'}):
            raise DevelopmentFault('Each key-plan step needs key or codepoint and atMilliseconds.',400)
        at=step['atMilliseconds']
        if type(at) is not int or not 0 <= at <= 2000 or at < previous:
            raise DevelopmentFault('Key-plan times must be monotonic within0..2000 milliseconds.',400)
        previous=at
        if 'key' in step:
            point=key(step['key'])  # Deliberately excludes modifier shortcuts.
            kind='key'
        else:
            point=step['codepoint'];kind='codepoint'
            if (type(point) is not int or not 32 <= point <= 0x10ffff or
                    127 <= point < 160 or 0xd800 <= point <= 0xdfff):
                raise DevelopmentFault('Use a printable Unicode codepoint, without control/modifier codes.',400)
        result.append({'kind':kind,'value':point,'atMilliseconds':at})
    return result


async def execute(execution,message,request,state,control,lease,authorization):
    from authorization import authorize
    from vm_worker import guard
    store=execution.store;job=store.get(execution.job['id']);process=job['process']
    if authorization and authorization['engine']['profile'] != 'studio-tools-v21':
        raise DevelopmentFault('This conversation retains its original input schema. A key-plan-capable session is required.',403)
    deployment=store.deployment(job['deploymentId'])
    if deployment.get('helperCapabilities',{}).get('keyPlanVersion') != 1 or request.get('frameBindingVersion') != 1:
        raise DevelopmentFault('Deploy a key-plan-v1 helper and capture its focused own window first.',400)
    plan=steps(message['input']['steps']);plan_id=message['requestId']
    request.update(keyPlanVersion=1,keyPlanId=plan_id,keySteps=plan)
    guard(store,job,lease)
    if authorization:authorize(store,message['owner'],'input',message['peerPid'],job)
    prefix=execution.work/('key-plan-'+plan_id)
    save(prefix.with_suffix('.intent.json'),{'schema':1,'jobId':job['id'],'keyPlanId':plan_id,
        'process':process,'frameId':message['input']['frameId'],'steps':plan,'createdAt':now()})
    state=await control.call('input',**request)  # Submit this original plan once.
    deadline=asyncio.get_running_loop().time()+3
    previous_count=0;previous_receipt=None;cancelled=False
    while True:
        execution.output(state);state['outputBase64']='';execution.last=state
        count=state.get('keyPlanAccepted');times=state.get('keyPlanTimesMilliseconds');late=state.get('keyPlanLatenessMilliseconds')
        if (state.get('keyPlanId') != plan_id or type(state.get('keyPlanActive')) is not bool
                or type(count) is not int or not previous_count <= count <= len(plan)
                or not isinstance(times,list) or not isinstance(late,list) or len(times) != count or len(late) != count
                or any(type(t) is not int or not plan[i]['atMilliseconds'] <= t <= 2000
                    or type(late[i]) is not int or late[i] != t-plan[i]['atMilliseconds'] for i,t in enumerate(times))
                or any(a>b for a,b in zip(times,times[1:]))
                or previous_receipt is not None and (times[:previous_count] != previous_receipt['queuedAtMilliseconds']
                    or late[:previous_count] != previous_receipt['latenessMilliseconds'])):
            raise UnconfirmedGuestEffect('The original key-plan receipt is inconsistent. No input was replayed.')
        previous_count=count
        result={'version':1,'kind':'keyPlan','keyPlanId':plan_id,'process':process,'accepted':count,'expected':len(plan),
            'active':state['keyPlanActive'],'complete':count==len(plan) and not state['keyPlanActive'] and not state.get('keyPlanAborted'),
            'queuedAtMilliseconds':times,'latenessMilliseconds':late,'abortedReason':state.get('keyPlanAborted'),
            'delivery':'owned-event-queue','timingObservation':'monotonic-enqueue-call-start',
            'consumptionConfirmed':False,'heldKeys':False,'heldModifiers':False}
        if result != previous_receipt:
            save(prefix.with_suffix('.receipt.json'),result)
            store.update(job['id'],lastKeyPlan=result)
            previous_receipt=result
        if not result['active']: return state,result
        cancel=execution.stop_requested or store.get(job['id'])['state']=='stopping'
        try:
            guard(store,job,lease)
            if authorization:authorize(store,message['owner'],'input',message['peerPid'],job)
        except DevelopmentFault:cancel=True
        if cancel and not cancelled:
            cancelled=True
            state=await control.call('cancel_key_plan',generation=process['generation'],keyPlanId=plan_id)
            continue
        if asyncio.get_running_loop().time()>deadline:
            raise UnconfirmedGuestEffect('The original key plan did not confirm its bounded end. Read its saved receipt; do not repeat it.')
        await asyncio.sleep(.05)
        state=await control.call('poll')
