import { useCallback, useEffect, useState } from 'react';
import type { ApiProvider } from '../../../../../shared/api-providers';
import type { ProviderApi } from '../useProviders';
import { providerRequestId } from '../api';
import { useApiMutation } from '../useApiMutation';

type Attempt = { requestId:string; name:string; state:string; registrationIssued?:boolean; canFinish?:boolean; redirectSubmitted?:boolean; authorizationUrl?:string; providerId?:string; error?:string };
type Pending={requestId:string;name:string;providerId?:string;previousAttempt?:string};
type Status = { accounts:{providerId:string;email?:string;clientId?:string;directPermission:boolean;remoteRevocation?:'confirmed'|'unknown'|null;quota:null;usageUrl:string}[]; attempts:Attempt[] };
export function ChatGPTPlan({ api, provider, saved }: { api:ProviderApi; provider?:ApiProvider; saved:(id:string)=>void }) {
  const {request,reload,loading}=api;
  const storageKey='studio.chatgpt-plan.attempt.'+(provider?.id??'new');
  const [status,setStatus]=useState<Status|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [name,setName]=useState(provider?.name??'ChatGPT plan'),[redirectUrl,setRedirectUrl]=useState('');
  const [pending,updatePending]=useState<Pending|null>(()=>{try{const value=JSON.parse(sessionStorage.getItem(storageKey)??'null') as Pending|null;return value&&/^[a-f0-9-]{36}$/.test(value.requestId)&&typeof value.name==='string'&&Object.keys(value).every(k=>['requestId','name','providerId','previousAttempt'].includes(k))?value:null;}catch{return null;}});
  const setPending=useCallback((value:Pending|null)=>{try{if(value)sessionStorage.setItem(storageKey,JSON.stringify(value));else sessionStorage.removeItem(storageKey);updatePending(value);return true;}catch{setError('Enable session storage to preserve the original sign-in ID.');return false;}},[storageKey]);
  const logout=useApiMutation(api,provider?.id??null);
  const active=status?.attempts.find(a=>a.requestId===pending?.requestId);
  const waiting=active&&['starting','waiting','exchanging','sent','intent','activating'].includes(active.state);
  const account=status?.accounts.find(a=>a.providerId===provider?.id);
  useEffect(()=>{if(loading)return;let mounted=true;void request<Status>('/chatgpt-plan').then(value=>{if(mounted)setStatus(value);}).catch((e:Error)=>{if(mounted)setError(e.message);});return()=>{mounted=false;};},[request,loading]);
  useEffect(()=>{
    if(!pending||loading)return;let mounted=true;let timer:ReturnType<typeof setTimeout>;
    const read=async()=>{
      try{
        const value=await request<Status>('/chatgpt-plan');if(!mounted)return;setStatus(value);
        const original=value.attempts.find(a=>a.requestId===pending.requestId);
        if(original?.providerId){setPending(null);await reload();saved(original.providerId);return;}
        if(!original||['starting','waiting','exchanging','sent','intent','activating'].includes(original.state))timer=setTimeout(()=>{void read();},1000);
      }catch(e){if(mounted)setError((e as Error).message);}
    };void read();return()=>{mounted=false;clearTimeout(timer);};
  },[pending,request,reload,saved,setPending,loading]);
  async function start(previousAttempt?:string){
    const original=previousAttempt?{requestId:providerRequestId(),name:name.trim(),previousAttempt}:pending??{requestId:providerRequestId(),name:name.trim(),...(provider?{providerId:provider.id}:{})};
    if(!setPending(original))return;setBusy(true);setError('');
    try{setStatus(await request<Status>('/chatgpt-plan/login','POST',original));}catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  async function submitRedirect(){
    if(!active||busy)return;setBusy(true);setError('');
    try{setStatus(await request<Status>('/chatgpt-plan/attempts/'+active.requestId+'/redirect','POST',{redirectUrl:redirectUrl.trim()}));setRedirectUrl('');}
    catch(e){setError((e as Error).message);}
    finally{setBusy(false);}
  }
  async function control(action:'cancel'|'finish'){
    if(!active)return;setBusy(true);setError('');try{const value=await request<Status>('/chatgpt-plan/attempts/'+active.requestId+'/'+action,'POST');setStatus(value);if(action==='cancel'){setPending(null);setRedirectUrl('');}else{const id=value.attempts.find(a=>a.requestId===active.requestId)?.providerId;if(id){setPending(null);await reload();saved(id);}}}catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  const disconnected=async()=>{const result=await logout.send('disconnect',{revision:provider!.revision});if(result?.state==='complete'){await reload();saved(provider!.id);}};
  return <div className="provider-form chatgpt-plan">
    <p className="field-help">Use your ChatGPT plan in Studio. Sign in with OpenAI, then paste the final redirect address here to finish connecting.</p>
    <label htmlFor="chatgpt-plan-name">Display name</label><input id="chatgpt-plan-name" value={name} onChange={e=>setName(e.target.value)} maxLength={80} disabled={!!provider||busy||!!pending}/>
    {account&&<p className="field-help">{account.email??provider?.name} · {account.directPermission?'Direct plan permission saved':'Sign-in required'}. Registration {account.clientId??'unavailable'}. Exact remaining plan quota is unavailable here. <a href={account.usageUrl} target="_blank" rel="noopener noreferrer">Manage ChatGPT usage</a></p>}
    {provider&&!provider.enabled&&account?.remoteRevocation&&<p role="status" className="field-help">Signed out locally. Remote token revocation: {account.remoteRevocation}. Review ChatGPT app access when its outcome is unknown.</p>}
    <p className="field-help">Review the plan and credit permissions you grant in ChatGPT settings. You can choose a model after connecting.</p>
    <div className="provider-actions"><button className="button-primary" type="button" disabled={loading||busy||!!waiting||!name.trim()} onClick={()=>{void start();}}>Continue with ChatGPT</button></div>
    {active&&<div role="status"><p>Sign-in: {active.state}</p>
      {active.state==='waiting'&&active.authorizationUrl?.startsWith('https://auth.openai.com/api/accounts/authorize?')&&<a href={active.authorizationUrl} target="_blank" rel="noopener noreferrer">Open ChatGPT sign-in</a>}
      {active.state==='waiting'&&!active.redirectSubmitted&&<div>
        <p className="field-help">After signing in, copy the complete final address from the other tab and paste it below. On another computer, the final 127.0.0.1 page may say it cannot connect; the address still contains the one-time sign-in result. Keep this Studio tab open. No download or terminal is needed.</p>
        <label htmlFor="chatgpt-redirect">Redirect address</label><textarea id="chatgpt-redirect" rows={3} value={redirectUrl} onChange={e=>setRedirectUrl(e.target.value)} autoComplete="off" autoCapitalize="none" spellCheck={false} placeholder="http://127.0.0.1:…/auth/callback?…" disabled={busy}/>
        <button className="button-primary" type="button" disabled={busy||!redirectUrl.trim()} onClick={()=>{void submitRedirect();}}>Complete sign-in</button>
      </div>}
      {active.redirectSubmitted&&waiting&&<p className="field-help">Redirect received. Studio is completing this original sign-in. Do not submit another address.</p>}
      {waiting&&active.state!=='activating'&&<button type="button" className="button-secondary" onClick={()=>{void control('cancel');}}>Cancel sign-in</button>}
      {active.canFinish&&!active.providerId&&<button type="button" className="button-secondary" onClick={()=>{void control('finish');}}>Finish original sign-in</button>}
      {active.error&&<p role="alert">{active.error}</p>}
      {!waiting&&active.state!=='authorized'&&<button type="button" className="button-secondary" onClick={()=>{setPending(null);}}>Review a new sign-in</button>}
    </div>}
    {!waiting&&!provider&&status?.attempts.filter(a=>!a.providerId&&a.registrationIssued).map(a=><button key={a.requestId} type="button" className="button-secondary" disabled={busy} onClick={()=>{void start(a.requestId);}}>Continue original registration · {a.name}</button>)}
    {provider?.enabled&&<button type="button" className="button-secondary" disabled={loading||busy||!!waiting||logout.busy||!!logout.pending} onClick={()=>{void disconnected();}}>Sign out of this plan connection</button>}
    {logout.pending&&<button type="button" className="button-secondary" onClick={()=>{void logout.read().then(()=>{void reload();saved(provider!.id);});}}>Read original sign-out status</button>}
    {(error||logout.error)&&<p role="alert" className="provider-alert">{error||logout.error}</p>}
  </div>;
}
