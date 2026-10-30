"""Native account/usage proof for one original send; never activate overage."""
import asyncio
import json
import os
import signal
import time

from claude_auth import auth_home,command
from claude_auth_store import AuthStore
from claude_limits_policy import usage_sample,admission
from claude_runtime import installed
from store import ProjectFault


async def native_status(providers,provider_id):
    runtime=await asyncio.to_thread(installed,providers)
    home=auth_home(AuthStore(providers),provider_id)
    child=None
    try:
        child=await asyncio.create_subprocess_exec(*command(runtime,home,'status',network=False),
            stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
            env={'PATH':'/usr/bin'},start_new_session=True,umask=0o077)
        raw=await asyncio.wait_for(child.stdout.read(32769),5)
        await asyncio.wait_for(child.wait(),2)
        if len(raw)>32768:raise ValueError()
        return {'output':raw.decode('utf-8'),'returncode':child.returncode}
    except (OSError,ValueError,UnicodeError,asyncio.TimeoutError):
        raise ProjectFault('The original native Claude account could not be confirmed. No model prompt was submitted.',503) from None
    finally:
        if child and child.returncode is None:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            await child.wait()


async def admit(worker,binding,account,usage):
    if not await worker.current(binding):return {'allowed':False,'reason':'The original native run is no longer active.'}
    started=worker.admission_started_at;providers=worker.manifest['providers']
    from claude_provider_store import ClaudeProviders
    provider=ClaudeProviders(providers).get(binding['providerId'])
    native=await native_status(providers,provider['id'])
    if not await worker.current(binding):return {'allowed':False,'reason':'Stop or a changed binding closed native admission.'}
    provider=ClaudeProviders(providers).get(binding['providerId'])
    sample=usage_sample(usage,provider,worker.row['request_id'])
    # Aliases are provenance from the authenticated native catalog; they are
    # not inferred from a display name or used to reroute a denied model.
    catalog=AuthStore(providers).latest_catalog(provider['id'])
    model=next((m for m in catalog['models'] if m['id']==binding['model']),None) if catalog else None
    if not model or model['resolvedModel']!=binding['model']:
        return {'allowed':False,'reason':'The original native model catalog binding is unavailable.'}
    if catalog.get('sessionModelsQualified') is not True or model.get('available') is not True:
        return {'allowed':False,'reason':'The original native model execution profile is not qualified.'}
    frozen=worker.config.get('claudeModel')
    if (not frozen or frozen.get('id')!=model['id'] or frozen.get('resolvedModel')!=model['resolvedModel']
        or frozen.get('catalogRequestId')!=catalog['requestId'] or frozen.get('runtimeProfileId')!=catalog['runtimeProfileId']
        or frozen.get('effort')!=worker.config['effort'] or frozen['effort'] not in model['efforts']):
        return {'allowed':False,'reason':'The original native model/effort selection changed.'}
    scope=next((v for v in ('opus','sonnet') if v in model['aliases']),None) if model else None
    result=admission(sample,provider,native,account,binding,started,model_scope=scope)
    from claude_quota_store import QuotaStore
    quota=QuotaStore(providers);saved=quota.record(provider['id'],sample=sample,denial=result)
    if result['allowed'] and saved['hold']:
        if not explicit_resume(worker,saved['hold'],sample['accountIdentity']):
            return {'allowed':False,'reason':'This subscription is held. Continue the queue or send again explicitly after a fresh limit check.'}
        quota.release(provider['id'],saved['hold'],worker.row['request_id'])
    # Keep only numeric/source quota observations in the private session log.
    # These observations never themselves clear a hold or resume a queue.
    from run_store import event
    event(worker.store,worker.session_id,worker.run_id,'claudeUsage',json.loads(json.dumps(sample)))
    return result


def explicit_resume(worker,hold,account):
    """An old queued input and a timer are not new human authorization."""
    db=worker.store.db
    if worker.config.get('goalExecution') or worker.config.get('claudeGoalExecution'):
        return False  # A bounded automatic step can never release an account hold.
    queued=(db.execute("SELECT mode FROM session_messages WHERE request_id=?",(worker.row['request_id'],)).fetchone()
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='session_messages'").fetchone() else None)
    if not queued:return worker.row['created_at']>hold['createdAt']
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='claude_quota_resumes'").fetchone():return False
    return db.execute('SELECT 1 FROM claude_quota_resumes WHERE session_id=? AND account_id=? AND created_at>? LIMIT 1',
        (worker.session_id,account,hold['createdAt'])).fetchone() is not None
