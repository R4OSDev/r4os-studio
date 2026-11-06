import {useCallback, useEffect, useRef, useState} from 'react';
import type {VisionSelection, VisionSettings} from '../../../../shared/vision-fallback';
import {ProjectRequestError, projectRequestId, studioRequest} from '../projects/api';
import './styles.css';
import './vision-fallback.css';
type Purpose = 'vision' | 'imageGeneration';
type Settings = Omit<VisionSettings,'vision'> & Partial<Record<Purpose,VisionSelection | null>>;
type Input = {requestId:string;revision:number} & Partial<Record<Purpose,VisionSelection | null>>;
type FormState = {dirty:boolean;pending:boolean;busy:boolean};
const same = (a: VisionSelection | null, b: VisionSelection | null) => a?.providerId === b?.providerId && a?.modelId === b?.modelId;
function stored<T>(key: string): T | null { try { return JSON.parse(sessionStorage.getItem(key) ?? 'null'); } catch { return null; } }
const request = <T,>(base:string, path = '', signal?: AbortSignal) => studioRequest<T>(base,path,'','GET',undefined,signal);
const VISION = '/api/settings/fallback';

export function VisionFallbackPanel({setLeaveGuard}: {setLeaveGuard: (guard: () => boolean) => void}) {
 const states = useRef<Partial<Record<Purpose,FormState>>>({});
 const [initial,setInitial] = useState<Settings | null>(null), [error,setError] = useState(''), [epoch,setEpoch] = useState(0);
 const report = useCallback((purpose:Purpose,state:FormState) => { states.current[purpose]=state; },[]);
 const guard = useCallback(() => {
  const forms=Object.values(states.current);
  return !forms.some(v => v.busy || v.pending) && (!forms.some(v => v.dirty) || window.confirm('Discard unsaved fallback changes?'));
 },[]);
 useEffect(() => { setLeaveGuard(guard); return () => setLeaveGuard(() => true); },[guard,setLeaveGuard]);
 useEffect(() => {
  const warn = (e:BeforeUnloadEvent) => { if (Object.values(states.current).some(v => v.dirty || v.pending || v.busy)) e.preventDefault(); };
  window.addEventListener('beforeunload',warn); return () => window.removeEventListener('beforeunload',warn);
 },[]);
 useEffect(() => {
  // Establish the shared settings cookie before mounting two independent forms.
  const controller=new AbortController();
  void request<Settings>(VISION,'',controller.signal).then(value => { if (!controller.signal.aborted) { setInitial(value);setError(''); } }).catch((cause:Error) => { if (!controller.signal.aborted) setError(cause.message); });
  return () => controller.abort();
 },[epoch]);
 if (!initial) return <div className="system-prompt-panel">{error ? <><p role="alert">{error}</p><button type="button" onClick={() => setEpoch(n => n+1)}>Reload settings</button></> : <p role="status">Loading fallback settings…</p>}</div>;
 return <div className="fallback-panels"><FallbackForm purpose="vision" initial={initial} report={report}/><FallbackForm purpose="imageGeneration" report={report}/></div>;
}

function FallbackForm({purpose,initial,report}: {purpose:Purpose;initial?:Settings;report:(purpose:Purpose,state:FormState) => void}) {
 const vision=purpose==='vision', label=vision?'Vision':'Image generation', prefix=vision?'vision':'image-generation';
 const DRAFT='studio.'+prefix+'-fallback.draft.v1', PENDING='studio.'+prefix+'-fallback.pending.v1';
 const base=VISION+(vision?'':'/image-generation');
 const [saved,setSaved] = useState<Settings | null>(null), [chosen,setChosen] = useState<VisionSelection | null>(null);
 const [baseRevision,setBaseRevision] = useState(0), [pending,setPending] = useState<Input | null>(() => stored(PENDING));
 const [busy,setBusy] = useState(false), [error,setError] = useState(''), [epoch,setEpoch] = useState(0), [retry,setRetry] = useState(false);
 const selected=saved?.[purpose] ?? null;
 const dirty = !!saved && !same(chosen,selected), conflict = !!saved && baseRevision !== saved.revision;
 useEffect(() => { report(purpose,{dirty,pending:!!pending,busy}); return () => report(purpose,{dirty:false,pending:false,busy:false}); },[purpose,dirty,pending,busy,report]);
 useEffect(() => {
  const controller = new AbortController();
  void (async () => {
   try {
    let value = epoch===0 && initial ? initial : await request<Settings>(base,'',controller.signal);
    const ticket = stored<Input>(PENDING);
    if (ticket) {
     try {
      await request(base,'/requests/'+ticket.requestId,controller.signal);
      if (controller.signal.aborted) return;
      sessionStorage.removeItem(PENDING); sessionStorage.removeItem(DRAFT); setPending(null); setRetry(false);
      value = await request<Settings>(base,'',controller.signal);
     } catch (cause) {
      if (controller.signal.aborted) return;
      setPending(ticket); setRetry((cause as ProjectRequestError).status === 404);
      setError('The original save is unconfirmed. Check its receipt or retry that same request.');
     }
    }
    if (!controller.signal.aborted) {
     const draft = stored<{revision:number} & Partial<Record<Purpose,VisionSelection | null>>>(DRAFT);
     setSaved(value); setChosen(draft ? draft[purpose] ?? null : value[purpose] ?? null); setBaseRevision(draft ? draft.revision : value.revision);
     if (!stored(PENDING)) setError('');
    }
   } catch (cause) { if (!controller.signal.aborted) setError((cause as Error).message); }
  })();
  return () => controller.abort();
 }, [epoch,base,DRAFT,PENDING,purpose,initial]);
 function choose(selection: VisionSelection | null) {
  if (!saved) return;
  sessionStorage.setItem(DRAFT,JSON.stringify({[purpose]:selection,revision:baseRevision})); setChosen(selection); setError('');
 }
 async function save(selection: VisionSelection | null, original?: Input) {
  if (!saved || busy) return;
  const input = original ?? {requestId:projectRequestId(),revision:selection === null ? saved.revision : baseRevision,[purpose]:selection};
  sessionStorage.setItem(PENDING,JSON.stringify(input)); setPending(input); setBusy(true); setRetry(false); setError('');
  try {
   await studioRequest(base,'',saved.csrfToken,'POST',input);
   const value = await request<Settings>(base);
   sessionStorage.removeItem(PENDING); sessionStorage.removeItem(DRAFT); setPending(null); setSaved(value); setChosen(value[purpose] ?? null); setBaseRevision(value.revision);
  } catch (cause) {
   if ([400,403,409].includes((cause as ProjectRequestError).status)) {
    sessionStorage.removeItem(PENDING); setPending(null); setError((cause as Error).message); setEpoch(n => n+1);
   } else { setError('The save response was not confirmed. Reading its original receipt.'); setEpoch(n => n+1); }
  } finally { setBusy(false); }
 }
 const savedProvider = saved?.providers.find(p => p.id === selected?.providerId);
 const savedModel = savedProvider?.models.find(m => m.id === selected?.modelId);
 const provider = saved?.providers.find(p => p.id === chosen?.providerId), model = provider?.models.find(m => m.id === chosen?.modelId);
 return <form className="system-prompt-panel vision-fallback" aria-label={label+' fallback'} onSubmit={e => { e.preventDefault(); void save(chosen); }}>
  <h2>{label}</h2><p>{vision ? 'Only requested image analysis uses this connection. The session’s main model stays unchanged.' : 'Requested image creation and edits use this connection when the session has no own image tool. The main model stays unchanged.'}</p>
  {!saved && !error && <p role="status">Loading fallback settings…</p>}
  {saved && <>
   <p className="vision-fallback-state" role="status">{saved.state}</p>
   {saved.reason && <p>{saved.reason}</p>}
   {selected && <p className="vision-fallback-saved">Saved: {savedProvider?.name ?? selected.providerId} / {savedModel?.name ?? selected.modelId}</p>}
   <label htmlFor={prefix+'-connection'}>Connection</label>
   <select id={prefix+'-connection'} value={chosen?.providerId ?? ''} disabled={busy || !!pending} onChange={e => choose(e.target.value ? {providerId:e.target.value,modelId:''} : null)}>
    <option value="">Not configured</option>
    {chosen && !provider && <option value={chosen.providerId}>Unavailable saved connection</option>}
    {saved.providers.map(p => <option key={p.id} value={p.id} disabled={!p.enabled}>{p.name}{!p.enabled ? ' · Unavailable' : ''}</option>)}
   </select>
   <label htmlFor={prefix+'-model'}>Model</label>
   <select id={prefix+'-model'} value={chosen?.modelId ?? ''} disabled={busy || !!pending || !provider} onChange={e => choose({providerId:chosen!.providerId,modelId:e.target.value})}>
    <option value="">Select {vision?'a Vision':'an image'} model</option>
    {chosen?.modelId && !model && <option value={chosen.modelId}>Unavailable saved model: {chosen.modelId}</option>}
    {provider?.models.map(m => <option key={m.id} value={m.id} disabled={!m.available}>{m.name}{m.available ? '' : ' · Unavailable'}</option>)}
   </select>
   {(model?.reason || provider?.reason) && <p>{model?.reason ?? provider?.reason}</p>}
   {conflict && <p role="alert">The saved revision changed. Your draft was retained. Cancel it to load the current selection.</p>}
  </>}
  {error && <p className="system-prompt-error" role="alert">{error}</p>}
  {pending ? <div className="system-prompt-actions">
   <button type="button" disabled={busy} onClick={() => setEpoch(n => n+1)}>Check original save</button>
   {retry && <button type="button" disabled={busy} onClick={() => void save(pending[purpose] ?? null,pending)}>Retry original save</button>}
  </div> : saved ? <div className="system-prompt-actions">
   <button type="button" disabled={busy || !selected} onClick={() => void save(null)}>Clear</button>
   <div className="system-prompt-save-actions">
    <button type="button" disabled={busy || !dirty && !conflict} onClick={() => { sessionStorage.removeItem(DRAFT); setChosen(selected); setBaseRevision(saved.revision); setError(''); }}>Cancel</button>
    <button type="submit" className="system-prompt-primary" disabled={busy || !dirty || conflict || !chosen || !model?.available}>{busy ? 'Saving…' : 'Save'}</button>
   </div>
  </div> : <button type="button" onClick={() => setEpoch(n => n+1)}>Reload settings</button>}
 </form>;
}
