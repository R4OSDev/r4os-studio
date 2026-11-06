import {useCallback,useEffect,useLayoutEffect,useRef,useState} from 'react';
import type {AgentSession,ModelChoiceInput,ModelChoiceResult} from '../../../../shared/agent-sessions';
import {ProjectRequestError,sessionPath,useSessionApi} from './api';
import {watchSessionIdentity} from './sessionReads';

const uuid=/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;
function stored(key:string):ModelChoiceInput|null {
  try {
    const value=JSON.parse(sessionStorage.getItem(key)??'null') as ModelChoiceInput|null;
    return value&&Object.keys(value).sort().join(',')==='afterRunId,effort,fastMode,model,requestId,revision,selectionRevision'
      &&uuid.test(value.requestId)&&uuid.test(value.afterRunId)&&Number.isSafeInteger(value.revision)&&value.revision>0
      &&Number.isSafeInteger(value.selectionRevision)&&value.selectionRevision>=0&&typeof value.fastMode==='boolean'
      &&typeof value.model==='string'&&value.model.length>0&&value.model.length<=200&&typeof value.effort==='string'&&value.effort.length<=30?value:null;
  } catch {return null;}
}

/** Recover only the original choice; never infer that a lost reply was a save. */
export function useModelChoice(ownerId:string,sid:string,token:string,saved:(session:AgentSession)=>void,reauth:()=>Promise<void>) {
  const {request:api,base:apiBase}=useSessionApi();
  const base=sessionPath(ownerId,sid)+'/model-choice',key=`studio.model-choice:${apiBase}:${ownerId}:${sid}`;
  const [pending,setPending]=useState<ModelChoiceInput|null>(()=>stored(key));
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const live=useRef(0),inflight=useRef(false),controller=useRef<AbortController|null>(null),onSaved=useRef(saved);
  useLayoutEffect(()=>{onSaved.current=saved;},[saved]);
  const accept=useCallback((result:ModelChoiceResult,input:ModelChoiceInput,generation:number)=>{
    if(live.current!==generation)return;
    if(result.receipt.requestId!==input.requestId||result.receipt.sessionId!==sid||result.session.id!==sid
      ||result.session.owner.id!==ownerId)throw new Error('The original model-choice receipt has another owner or session.');
    if(stored(key)?.requestId===input.requestId)sessionStorage.removeItem(key);
    setPending(null);setError('');onSaved.current(result.session);
  },[key,ownerId,sid]);
  const execute=useCallback(async(input:ModelChoiceInput,write:boolean)=>{
    if(inflight.current)return;
    const generation=live.current,abort=new AbortController();controller.current=abort;inflight.current=true;setBusy(true);setError('');
    try {
      const result=await api<ModelChoiceResult>(base+(write?'':'/requests/'+input.requestId),write?token:'',write?'POST':'GET',write?input:undefined,abort.signal);
      accept(result,input,generation);
    } catch(cause) {
      if(live.current!==generation||abort.signal.aborted)return;
      if((cause as ProjectRequestError).status===403)await reauth().catch(()=>undefined);
      if(write) {
        try {
          const original=await api<ModelChoiceResult>(base+'/requests/'+input.requestId,'','GET',undefined,abort.signal);
          accept(original,input,generation);return;
        } catch(readError) {
          if(live.current!==generation||abort.signal.aborted)return;
          const status=(cause as ProjectRequestError).status;
          if((readError as ProjectRequestError).status===404&&status&&status>=400&&status<500&&status!==408) {
            if(stored(key)?.requestId===input.requestId)sessionStorage.removeItem(key);
            setPending(null);
            try {
              const current=await api<{session:AgentSession}>(sessionPath(ownerId,sid),'','GET',undefined,abort.signal);
              if(live.current===generation&&current.session.id===sid&&current.session.owner.id===ownerId)onSaved.current(current.session);
            } catch { /* The concrete rejection and existing choice remain visible. */ }
          }
        }
      }
      if(live.current===generation)setError(cause instanceof Error?cause.message:'The original model choice is unconfirmed. Check its receipt.');
    } finally {
      if(live.current===generation){inflight.current=false;controller.current=null;setBusy(false);}
    }
  },[api,base,token,accept,reauth,key,ownerId,sid]);
  const executeRef=useRef(execute);
  useLayoutEffect(()=>{executeRef.current=execute;},[execute]);
  const invalidate=useCallback(()=>{live.current++;controller.current?.abort();inflight.current=false;},[]);
  useEffect(()=>{
    const generation=live.current;
    queueMicrotask(()=>{
      if(live.current!==generation)return;
      const original=stored(key);setPending(original);
      if(original)void executeRef.current(original,false);
    });
    return invalidate;
  },[key,invalidate]);
  useEffect(()=>watchSessionIdentity(()=>{
    live.current++;controller.current?.abort();controller.current=null;inflight.current=false;setBusy(false);
    if(stored(key))setError('The connection changed. Check the original model-choice receipt before choosing again.');
  }),[key]);
  async function send(input:ModelChoiceInput) {
    if(inflight.current||pending)return;
    try {sessionStorage.setItem(key,JSON.stringify(input));}
    catch {setError('Enable session storage to preserve the original model-choice request before saving.');return;}
    setPending(input);await execute(input,true);
  }
  return {pending,busy,error,send,read:()=>pending?execute(pending,false):Promise.resolve(),retry:()=>pending?execute(pending,true):Promise.resolve()};
}
