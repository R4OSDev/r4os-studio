"""One continuation admission, only after fresh scope evidence and whole-run end."""
import json
import math
import uuid
from pathlib import Path
from session_store import SessionStore,encode,now
from run_store import admit,get_run
from store import ProjectFault
from zai_monitor import stamp
import quota_wait as waits

PROMPT=('Continue the existing unfinished user task from the last confirmed progress in this same conversation. '
    'The original primary model stopped because its usage allowance was exhausted; a fresh matching account observation now permits continuation. '
    'Read the original messages and tool receipts. Do not repeat the original user prompt, confirmed tool effects or completed work. '
    'Preserve unknown outcomes and ask for clarification when the remaining work is unclear.')

def positive(wait,observation):
    import datetime
    if observation.get('state')!='current' or observation.get('holds'):return False
    start=stamp(observation.get('startedAt'));observed=stamp(observation.get('observedAt'));negative=stamp(wait['negativeAt'])
    if not start or not observed or not negative or start<=negative or observed<start:return False
    age=(datetime.datetime.now(datetime.timezone.utc)-observed).total_seconds()
    if not -1<=age<90:return False
    if wait.get('accountIdentity') is not None and observation.get('source')!=wait['accountIdentity']:return False
    windows=observation.get('windows',[])
    if not windows or any(type(w.get('remaining')) not in (int,float) or not math.isfinite(w['remaining']) or w['remaining']<=0 for w in windows):return False
    kind=wait['providerBinding']['kind'];ids={w['id'] for w in windows}
    if kind=='zai-coding-plan' and (not wait.get('accountIdentity') or not {'5-hour','Weekly'}<={w['label'] for w in windows}):return False
    if kind=='claude-plan' and not {'five_hour','seven_day'}<=ids:return False
    if kind=='codex-subscription' and (observation.get('allowanceAllowed') is not True or not any(i.startswith('codex:') for i in ids)):return False
    if kind=='openrouter' and not wait.get('negativeWindows'):return False
    if kind not in ('zai-coding-plan','claude-plan','codex-subscription','openrouter'):return False
    if not set(wait.get('negativeWindows',[]))<=ids:return False
    return True

def context(config,kind,ident,sid,wait_id):
    store=SessionStore(config['projects'],config['r4os'],ident,kind)
    try:
        value=waits.row(store,sid)
        if not value or value.get('id')!=wait_id or value['state']!='waiting':raise ProjectFault('The original quota wait changed.',409)
        from active_history import ActiveHistory
        from studio_context import open_calls
        messages,_,_=ActiveHistory(store,sid).read('quota-continuation:'+value['configSha256'])
        if not messages or open_calls(messages):raise ProjectFault('Original conversation/tool context is incomplete.',409)
        sequence=store.db.execute('SELECT COALESCE(MAX(seq),0) FROM conversation_records WHERE session_id=?',(sid,)).fetchone()[0]
        if sequence<value['confirmedThroughSequence']:raise ProjectFault('Original confirmed conversation progress is unavailable.',409)
        return {'sequence':sequence,'contextSha256':waits.digest(messages)}
    finally:store.close()

def validate(store,sid,marker,snapshot=None):
    value=waits.row(store,sid)
    if (not value or value['state']!='dispatching' or value.get('id')!=marker['waitId'] or value.get('resumeRequestId')!=marker['requestId']
            or value['epoch']!=marker['epoch'] or value['sourceRunId']!=marker['parentRunId']):raise ProjectFault('The original quota continuation admission changed.',409)
    original=json.loads(get_run(store,value['sourceRunId'])['config'])
    if not waits.matches(store,sid,original):raise ProjectFault('The original selection or control changed before continuation.',409)
    if snapshot is not None:
        for key in ('providerId','model','effort','fastMode','apiProvider','apiNativeAccount','apiClaudeGrant','projectPins','owner','remoteHostBinding','githubBinding'):
            if snapshot.get(key)!=original.get(key):raise ProjectFault('The original model/account/runtime binding changed. Continue explicitly.',409)
        if any(allowed and not original['permissions'].get(key,False) for key,allowed in snapshot['permissions'].items()):raise ProjectFault('Continuation cannot expand the original tool permissions.',409)
        if snapshot.get('skillAccess')!=original.get('skillAccess'):raise ProjectFault('The original accepted skill resources changed. Continue explicitly.',409)
        for key in ('webSearchEnabled','nativeImageGeneration','environmentNotesEnabled','roadmapEnabled'):
            if snapshot.get(key) and not original.get(key):raise ProjectFault('Continuation cannot expand original feature permissions.',409)
    return value

async def dispatch(host,store,sid,observation,prepared):
    """Caller holds the normal host decision lock; no network read occurs here."""
    value=waits.row(store,sid)
    if not value or value['state']!='waiting' or not positive(value,observation):return False
    key=(store.owner_type,store.owner_id,sid)
    if host.unbound or len(host.active)>=host.max_active_runs:return False
    original=get_run(store,value['sourceRunId']);config=json.loads(original['config'])
    if not waits.matches(store,sid,config):
        with store.db:waits.control(store,sid,'The accepted model, account or control changed.')
        return False
    from run_boundary import require
    ended=await require(host,store,sid)
    if ended is None or ended['id']!=value['sourceRunId']:return False
    if original['state']!='failed' or waits.digest(config)!=value['configSha256']:raise ProjectFault('The original quota stop identity changed.',409)
    if not prepared or store.db.execute('SELECT COALESCE(MAX(seq),0) FROM conversation_records WHERE session_id=?',(sid,)).fetchone()[0]!=prepared['sequence']:
        raise ProjectFault('The original conversation changed during quota preparation.',409)
    if store.row(sid)['thread_id']!=value['threadId']:raise ProjectFault('The original conversation thread changed.',409)
    # Already accepted human input takes priority, without resending the old prompt.
    from message_store import pending_queue,exists as has_messages
    if pending_queue(store,sid):
        inbox=store.db.execute('SELECT * FROM session_inboxes WHERE session_id=?',(sid,)).fetchone() if has_messages(store) else None
        generic='The preceding run ended without a confirmed natural completion. Continue explicitly.'
        if inbox and (not inbox['held'] or inbox['reason']==generic):
            with store.db:
                first=store.db.execute("SELECT request_id FROM session_messages WHERE session_id=? AND mode='queue' AND state='queued' ORDER BY seq LIMIT 1",(sid,)).fetchone()
                value.update(consumedByRequestId=first['request_id'] if first else None,revision=value['revision']+1)
                waits.put(store,sid,value)
                store.db.execute('UPDATE session_inboxes SET held=0,reason=NULL,revision=revision+1 WHERE session_id=?',(sid,))
                waits.control(store,sid,'Accepted human queue takes priority after confirmed quota availability.')
            host.inboxes.add(key);host.quota_waits.discard(key)
        return False
    goal=None
    if value.get('goal'):
        from goal_keepalive import prepare
        goal=prepare(store,sid,value['sourceRunId'])
        if not goal:
            with store.db:waits.control(store,sid,'The original Goal is no longer authorized or its budget is exhausted.')
            return False
    session=store.get(sid)
    rid=str(uuid.uuid5(uuid.UUID(value['id']),'continuation'))
    marker={'waitId':value['id'],'parentRunId':value['sourceRunId'],'requestId':rid,'epoch':value['epoch'],'prompt':PROMPT,
        'clearanceStartedAt':observation['startedAt'],'clearanceObservedAt':observation['observedAt']}
    with store.db:
        value.update(state='dispatching',revision=value['revision']+1,resumeRequestId=rid,clearance=marker,context=prepared)
        waits.put(store,sid,value)
    data={'requestId':rid,'revision':session['revision'],'text':PROMPT}
    for feature,field in (('webSearchEnabled','nativeWebSearch'),('imageContext','nativeImageInputs'),('documentContext','documentInputs'),
            ('nativeImageGeneration','imageGenerationSettings'),('environmentNotesEnabled','environmentNotesSettings')):
        if config.get(feature):data[field]=1
    skills=config.get('skillAccess')
    if skills is not None:
        data['skillSelection']=1
        if skills.get('terminal'):data['skillScripts']=1
        if any(entry.get('mcp') for entry in skills['entries']):data['skillMcp']=1
    if store.owner_type=='project':
        data['projectInstructions']=1
        if config.get('roadmapEnabled'):data['roadmapSettings']=1
        if config.get('remoteHostBinding'):data['remoteHostTools']=1
    try:
        run,fresh=admit(store,sid,data,host.config['providers'],config.get('imageGenerationCapability'),keepalive=goal,quota_resume=marker)
    except Exception:
        # Admission may have produced an original receipt/lease before an
        # uncertain reply. Never reconstruct a launch or repeat the operation.
        current=waits.row(store,sid)
        if current and current.get('id')==value['id'] and current['state']=='dispatching':
            with store.db:current.update(state='unknown',revision=current['revision']+1,reason='Original quota continuation admission is unconfirmed. Read its original receipt; no launch was repeated.');waits.put(store,sid,current)
        raise
    with store.db:
        value=waits.row(store,sid);value.update(state='resumed' if fresh else 'unknown',revision=value['revision']+1,resumedRunId=run['id'],endedAt=now())
        waits.put(store,sid,value)
    host.quota_waits.discard(key)
    if not fresh:return False
    if goal:
        from goal_keepalive import admitted
        admitted(store,sid,goal,run['id'])
    await host.launch_admitted(store,run,store.owner_type,store.owner_id,sid)
    return True
