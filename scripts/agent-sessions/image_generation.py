"""Qualified native image policy. No prompts, turns or provider credential parsing."""
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
from codex_rpc import CodexRPC
from profile import CODEX_SHA256,CODEX_VERSION,IMAGE_PROFILE,IMAGE_SKILL_PROFILE,prepare
from session_store import provider_models,providers,identity,encode,now
from store import ProjectFault

def evaluate(session,model,provider,account,engine,bridge=False):
    result={'schema':1,'providerId':session['providerId'],'model':session['model'],'engine':session['engine'],
        'checkedAt':now(),'state':'unknown','available':False,'qualified':False,'reason':'Native image capability could not be confirmed.'}
    def finish(state,reason):result.update(state=state,available=state=='available',reason=reason);return result
    if engine.get('sha256')!=CODEX_SHA256 or engine.get('version')!=CODEX_VERSION:
        return finish('unavailable','Select the qualified Codex 0.163.0 runtime before using image generation.')
    if session['engine'].get('profile') not in (IMAGE_PROFILE,IMAGE_SKILL_PROFILE):
        return finish('unavailable','New session required for generated-image tools. This conversation keeps its original profile.')
    if not model or model.get('imageInputs')=='unknown':return result
    if model.get('imageInputs')!='supported':return finish('unavailable','The selected model does not support the image modality required by the native image tool.')
    if not isinstance(provider,dict) or type(provider.get('imageGeneration')) is not bool:return result
    if not provider['imageGeneration']:return finish('unavailable','The native provider does not offer image generation.')
    raw=account.get('account') if isinstance(account,dict) else None
    if not isinstance(raw,dict) or raw.get('type')!='chatgpt':return finish('unavailable','Native image generation requires a connected ChatGPT account supported by Codex.')
    plan=raw.get('planType')
    if not isinstance(plan,str) or not plan or plan.lower()=='unknown':return result
    if plan.lower()=='free':return finish('unavailable','Native image generation is unavailable for this account plan.')
    account_hash=hashlib.sha256(encode({key:raw.get(key) for key in ('type','email','planType','chatgptAccountId')}).encode()).hexdigest()
    # Only non-secret, bounded policy facts enter the immutable run snapshot.
    result.update(qualified=True,accountType='chatgpt',accountPlan=plan[:40],accountSha256=account_hash,inputModalities=model.get('inputModalities'),
        policySha256=hashlib.sha256(encode({'provider':provider,'accountSha256':account_hash,'model':model,'engine':engine}).encode()).hexdigest())
    if not bridge:return finish('unavailable','The active worker release has no installed image output adapter yet.')
    return finish('available','Native image generation is available for this account, provider and model.')

async def inspect(store,sid,provider_dir,overrides=None,rpc_factory=CodexRPC,bridge=True):
    session=store.get(sid);overrides=overrides or {}
    if set(overrides)-{'providerId','model'}:raise ProjectFault('Unexpected image capability fields.',400)
    session={**session,**overrides};identity(session['providerId'])
    if not any(value['id']==session['providerId'] for value in providers(provider_dir)):raise ProjectFault('Connect the selected provider before checking image capability.',409)
    model=next((value for value in provider_models(provider_dir,session['providerId']) if value['id']==session['model']),None)
    fallback=evaluate(session,model,None,None,session['engine'],bridge)
    if fallback['state']=='unavailable' or not model:return fallback
    from generated_images import GeneratedImages
    try:GeneratedImages(store,sid).check_capacity()
    except (ProjectFault,ValueError,OSError) as error:
        return {**fallback,'state':'unavailable','available':False,'reason':str(error) if isinstance(error,ProjectFault) else 'Private image storage requires review. Original files were preserved.'}
    history=store.directory/sid/'Codex/native'
    if history.exists() and any(path.stat().st_size>64*1024*1024 for path in history.rglob('*') if path.is_file()):
        return {**fallback,'state':'unavailable','available':False,'reason':'Original native history exceeds the image runtime file bound. Generation is unavailable until review; existing history was preserved.'}
    parent=store.directory/sid
    if parent.is_symlink() or parent.parent.resolve(strict=True)!=parent.parent:
        raise ProjectFault('Unexpected native capability storage.',503)
    parent.mkdir(mode=0o700,exist_ok=True)
    if parent.resolve(strict=True)!=parent or not parent.is_dir():raise ProjectFault('Unexpected native capability storage.',503)
    with tempfile.TemporaryDirectory(prefix='.image-capability-',dir=parent) as temporary:
        client=None
        try:
            args,engine=prepare(Path(store.r4os)/'Toolchains/Codex'/session['engine']['version']/'codex',Path(provider_dir)/session['providerId'],Path(temporary),
                json.loads(Path(__file__).with_name('features.json').read_text()),session['model'],session['providerId'],session['engine']['profile'])
            async def notification(method,params):
                if method=='turn/started':raise RuntimeError('An image capability read cannot start a turn.')
            async def tool(params):raise RuntimeError('An image capability read cannot execute tools.')
            client=rpc_factory(args,notification,tool);client.version='R4OS Studio image capability read'
            await asyncio.wait_for(client.start(),5)
            capability=await client.request('modelProvider/capabilities/read',{},timeout=5)
            account=await client.request('account/read',{'refreshToken':False},timeout=5)
            return evaluate(session,model,capability,account,engine,bridge)
        except asyncio.CancelledError:raise
        except Exception:return fallback
        finally:
            if client:await client.close()

def freeze(session,value):
    if (not isinstance(value,dict) or value.get('schema')!=1 or type(value.get('available')) is not bool
            or value.get('available') and (value.get('state')!='available' or value.get('qualified') is not True)
            or any(value.get(key)!=session.get(key) for key in ('providerId','model','engine'))):
        return {'schema':1,'available':False,'qualified':False,'state':'unknown','reason':'No matching native image capability was confirmed for this run.'}
    return value
