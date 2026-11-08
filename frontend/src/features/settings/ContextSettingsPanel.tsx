import {useCallback,useEffect,useRef,useState} from 'react';
import {ProjectRequestError,projectRequestId,studioRequest} from '../projects/api';
import './styles.css';
import './context-settings.css';

type Settings={revision:number;enabled:boolean;budgetTokens:number;defaultEnabled:boolean;defaultBudgetTokens:number;maxBudgetTokens:number;csrfToken:string};
type Input={requestId:string;revision:number;action:'save'|'reset';budgetTokens?:number;enabled?:boolean};
const BASE='/api/settings/context',DRAFT='studio.context.draft.v1',PENDING='studio.context.pending.v1';
function stored<T>(key:string):T|null {try{return JSON.parse(sessionStorage.getItem(key)??'null');}catch{return null;}}
const get=<T,>(path='',signal?:AbortSignal)=>studioRequest<T>(BASE,path,'','GET',undefined,signal);

export function ContextSettingsPanel({setLeaveGuard}:{setLeaveGuard:(guard:()=>boolean)=>void}) {
 const [saved,setSaved]=useState<Settings|null>(null),[text,setText]=useState(''),[revision,setRevision]=useState(0);
 const [enabled,setEnabled]=useState(true);
 const [pending,setPending]=useState<Input|null>(()=>stored(PENDING)),[busy,setBusy]=useState(false),[retry,setRetry]=useState(false),[epoch,setEpoch]=useState(0),[error,setError]=useState('');
 const dirty=!!saved && (text!==String(saved.budgetTokens)||enabled!==saved.enabled),conflict=!!saved && revision!==saved.revision;
 const state=useRef({dirty,pending:!!pending,busy});
 useEffect(()=>{state.current={dirty,pending:!!pending,busy};},[dirty,pending,busy]);
 const guard=useCallback(()=>!state.current.busy&&!state.current.pending&&(!state.current.dirty||window.confirm('Discard unsaved context settings?')),[]);
 useEffect(()=>{setLeaveGuard(guard);const warn=(e:BeforeUnloadEvent)=>{if(Object.values(state.current).some(Boolean))e.preventDefault();};window.addEventListener('beforeunload',warn);return()=>{setLeaveGuard(()=>true);window.removeEventListener('beforeunload',warn);};},[guard,setLeaveGuard]);
 useEffect(()=>{
  const controller=new AbortController();
  void(async()=>{
   try {
    let value=await get<Settings>('',controller.signal);const ticket=stored<Input>(PENDING);
    if(ticket){
     try {await get('/requests/'+ticket.requestId,controller.signal);if(controller.signal.aborted)return;sessionStorage.removeItem(PENDING);sessionStorage.removeItem(DRAFT);setPending(null);setRetry(false);value=await get<Settings>('',controller.signal);}
     catch(cause){if(controller.signal.aborted)return;setPending(ticket);setRetry((cause as ProjectRequestError).status===404);setError('The original save is unconfirmed. Check its receipt or retry that same request.');}
    }
    if(controller.signal.aborted)return;
    const draft=stored<{text:string;revision:number;enabled?:boolean}>(DRAFT);setSaved(value);setText(draft?.text??String(value.budgetTokens));setEnabled(draft?.enabled??value.enabled);setRevision(draft?.revision??value.revision);if(!stored(PENDING))setError('');
   }catch(cause){if(!controller.signal.aborted)setError((cause as Error).message);}
  })();return()=>controller.abort();
 },[epoch]);
 function change(value:string,active=enabled){setText(value);setEnabled(active);sessionStorage.setItem(DRAFT,JSON.stringify({text:value,enabled:active,revision}));setError('');}
 async function save(action:'save'|'reset',original?:Input){
  if(!saved||busy)return;
  const amount=Number(text);
  if(!original&&action==='save'&&(!/^\d+$/.test(text)||!Number.isSafeInteger(amount)||amount<1||amount>saved.maxBudgetTokens)){setError('budgetTokens must be a whole number from 1 to '+saved.maxBudgetTokens+'.');return;}
  const input=original??{requestId:projectRequestId(),revision,action,...(action==='save'?{budgetTokens:amount,enabled}:{})};
  sessionStorage.setItem(PENDING,JSON.stringify(input));setPending(input);setBusy(true);setRetry(false);setError('');
  try{
   await studioRequest(BASE,'',saved.csrfToken,'POST',input);const value=await get<Settings>();sessionStorage.removeItem(PENDING);sessionStorage.removeItem(DRAFT);setPending(null);setSaved(value);setText(String(value.budgetTokens));setEnabled(value.enabled);setRevision(value.revision);
  }catch(cause){if([400,403,409].includes((cause as ProjectRequestError).status)){sessionStorage.removeItem(PENDING);setPending(null);setError((cause as Error).message);}else setError('The save response was not confirmed. Reading its original receipt.');setEpoch(n=>n+1);}finally{setBusy(false);}
 }
 return <form className="system-prompt-panel context-settings" aria-label="Context limit settings" onSubmit={e=>{e.preventDefault();void save('save');}}>
  <h2>Context · Limit</h2><p>Global input limit for project and skill sessions. Changes apply from the next accepted Studio run. Lower model limits always apply.</p>
  {!saved&&!error&&<p role="status">Loading context settings…</p>}
  {saved&&<>
   <label className="context-limit-switch" htmlFor="context-enabled"><input id="context-enabled" type="checkbox" role="switch" checked={enabled} disabled={busy||!!pending} onChange={e=>change(text,e.target.checked)}/><span>Enable global context limit</span></label>
   <label htmlFor="context-budget">Global input limit (tokens)</label>
   <input id="context-budget" type="text" inputMode="numeric" value={text} disabled={busy||!!pending} aria-describedby="context-budget-help" onChange={e=>change(e.target.value)}/>
   <p id="context-budget-help">Whole number from 1 to {saved.maxBudgetTokens.toLocaleString('en-US')}. Default: {saved.defaultBudgetTokens.toLocaleString('en-US')}.</p>
   <p>Global limit: {saved.enabled?'On':'Off'} · {saved.budgetTokens.toLocaleString('en-US')} tokens. Switching it off keeps this value and leaves model limits in effect. The input includes instructions, tools, conversation, summaries and media; cached input counts in full. Studio checks a conservative full-input estimate before sending; it can stop earlier than the provider’s token count. Original context is kept if it cannot be reduced safely.</p>
   {conflict&&<p role="alert">The saved revision changed. Your draft was retained. Cancel the draft to load current settings.</p>}
  </>}
  {error&&<p role="alert" className="system-prompt-error">{error}</p>}
  {pending?<div className="system-prompt-actions"><button type="button" disabled={busy} onClick={()=>setEpoch(n=>n+1)}>Check original save</button>{retry&&<button type="button" disabled={busy} onClick={()=>void save(pending.action,pending)}>Retry original save</button>}</div>:saved?<div className="system-prompt-actions">
   <button type="button" disabled={busy||conflict||saved.budgetTokens===saved.defaultBudgetTokens&&saved.enabled===saved.defaultEnabled} onClick={()=>void save('reset')}>Reset to default</button>
   <div className="system-prompt-save-actions"><button type="button" disabled={busy||!dirty&&!conflict} onClick={()=>{sessionStorage.removeItem(DRAFT);setText(String(saved.budgetTokens));setEnabled(saved.enabled);setRevision(saved.revision);setError('');}}>Cancel</button><button type="submit" className="system-prompt-primary" disabled={busy||!dirty||conflict}>Save</button></div>
  </div>:<button type="button" onClick={()=>setEpoch(n=>n+1)}>Reload settings</button>}
 </form>;
}
