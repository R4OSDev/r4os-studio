import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { AgentSession, QuotaWaitCancelInput, QuotaWaitResult, SessionQuotaWait } from '../../../../shared/agent-sessions';
import { ProjectRequestError, sessionPath, useSessionApi } from './api';
import { watchSessionIdentity } from './sessionReads';
import { providerRequestId } from '../llm-providers/api';
const uuid=/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;
function stored(key:string):QuotaWaitCancelInput|null {
  try {
    const value=JSON.parse(sessionStorage.getItem(key)??'null') as QuotaWaitCancelInput|null;
    return value&&Object.keys(value).sort().join(',')==='requestId,revision,waitId'&&uuid.test(value.requestId)&&uuid.test(value.waitId)
      &&Number.isSafeInteger(value.revision)&&value.revision>0?value:null;
  } catch { return null; }
}
export function useQuotaWait(ownerId:string,sid:string,token:string,wait:SessionQuotaWait|undefined,saved:(value:SessionQuotaWait,session?:AgentSession)=>void,reauth:()=>Promise<void>) {
  const {request:api,base:apiBase,scope}=useSessionApi();
  const base=sessionPath(ownerId,sid)+'/quota-wait',key=`studio.quota-wait:${apiBase}:${ownerId}:${sid}`;
  const [pending,setPending]=useState(()=>stored(key)),[busy,setBusy]=useState(false),[notFound,setNotFound]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const live=useRef(0),inflight=useRef(false),controller=useRef<AbortController|null>(null),onSaved=useRef(saved),latest=useRef(wait);
  useLayoutEffect(()=>{onSaved.current=saved;latest.current=wait;},[saved,wait]);
  const accept=useCallback((result:QuotaWaitResult,input:QuotaWaitCancelInput,generation:number)=>{
    if(live.current!==generation)return;
    if(result.owner.type!==scope||result.owner.id!==ownerId||result.sessionId!==sid||result.receipt.sessionId!==sid
      ||result.receipt.requestId!==input.requestId||result.receipt.waitId!==input.waitId||result.receipt.state!=='confirmed')throw new Error('The original cancellation has another owner, wait or session.');
    if(stored(key)?.requestId===input.requestId)sessionStorage.removeItem(key);
    setPending(null);setNotFound(false);setError('');
    setNotice(result.receipt.outcome==='already-admitted'?'The continuation was already admitted. Use Stop in the message composer to stop it.':'');
    onSaved.current(result.quotaWait,result.session);
    if(typeof BroadcastChannel!=='undefined') {const channel=new BroadcastChannel('studio-quota-waits');channel.postMessage({scope,ownerId,sid,revision:result.quotaWait.revision});channel.close();}
  },[key,ownerId,sid,scope]);
  const execute=useCallback(async(input:QuotaWaitCancelInput,write:boolean)=>{
    if(inflight.current)return;
    const generation=live.current,abort=new AbortController();controller.current=abort;inflight.current=true;setBusy(true);setError('');
    try {
      const result=await api<QuotaWaitResult>(base+(write?'/cancel':'/requests/'+input.requestId),write?token:'',write?'POST':'GET',write?input:undefined,abort.signal);
      accept(result,input,generation);
    } catch(cause) {
      if(live.current!==generation||abort.signal.aborted)return;
      if((cause as ProjectRequestError).status===403)await reauth().catch(()=>undefined);
      if(write) {
        try {accept(await api<QuotaWaitResult>(base+'/requests/'+input.requestId,'','GET',undefined,abort.signal),input,generation);return;}
        catch(readError) {
          if(live.current!==generation||abort.signal.aborted)return;
          const status=(cause as ProjectRequestError).status,missing=(readError as ProjectRequestError).status===404;
          setNotFound(missing);
          if(missing&&status&&status>=400&&status<500&&status!==408) {
            if(stored(key)?.requestId===input.requestId)sessionStorage.removeItem(key);setPending(null);
            try {const result=await api<{quotaWait:SessionQuotaWait}>(base,'','GET',undefined,abort.signal);if(live.current===generation)onSaved.current(result.quotaWait);}catch{/* Keep concrete rejection visible. */}
          }
        }
      } else setNotFound((cause as ProjectRequestError).status===404);
      if(live.current===generation)setError(cause instanceof Error?cause.message:'The original cancellation is unconfirmed. Read its receipt.');
    } finally {if(live.current===generation){inflight.current=false;controller.current=null;setBusy(false);}}
  },[api,base,token,accept,reauth,key]);
  const executeRef=useRef(execute);useLayoutEffect(()=>{executeRef.current=execute;},[execute]);
  const invalidate=useCallback(()=>{live.current++;controller.current?.abort();inflight.current=false;},[]);
  useEffect(()=>{
    const generation=live.current;queueMicrotask(()=>{if(live.current!==generation)return;const input=stored(key);setPending(input);if(input)void executeRef.current(input,false);});
    return invalidate;
  },[key,invalidate]);
  useEffect(()=>watchSessionIdentity(()=>{live.current++;controller.current?.abort();controller.current=null;inflight.current=false;setBusy(false);}),[]);
  useEffect(()=>{
    if(typeof BroadcastChannel==='undefined')return;
    const channel=new BroadcastChannel('studio-quota-waits');let active=true;
    channel.onmessage=event=>{const value=event.data;if(value?.scope!==scope||value.ownerId!==ownerId||value.sid!==sid||value.revision<=(latest.current?.revision??0))return;
      void api<{quotaWait:SessionQuotaWait}>(base).then(result=>{if(active)onSaved.current(result.quotaWait);}).catch(()=>{/* Existing stream/reload remains authoritative. */});};
    return()=>{active=false;channel.close();};
  },[api,base,ownerId,sid,scope]);
  async function stop() {
    if(inflight.current)return;
    if(pending){await execute(pending,notFound);return;}
    if(!wait?.active||wait.state!=='waiting'||!wait.waitId)return;
    const input={requestId:providerRequestId(),waitId:wait.waitId,revision:wait.revision};
    try{sessionStorage.setItem(key,JSON.stringify(input));}catch{setError('Enable session storage to preserve the original cancellation.');return;}
    setPending(input);setNotFound(false);setNotice('');await execute(input,true);
  }
  return {pending,busy,error,notice,notFound,stop,read:()=>pending?execute(pending,false):Promise.resolve()};
}
