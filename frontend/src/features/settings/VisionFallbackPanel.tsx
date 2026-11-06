import {useCallback, useEffect, useState} from 'react';
import type {VisionSelection, VisionSettings, VisionSettingsInput} from '../../../../shared/vision-fallback';
import {ProjectRequestError, projectRequestId, studioRequest} from '../projects/api';
import './styles.css';
import './vision-fallback.css';
const DRAFT = 'studio.vision-fallback.draft.v1', PENDING = 'studio.vision-fallback.pending.v1';
const same = (a: VisionSelection | null, b: VisionSelection | null) => a?.providerId === b?.providerId && a?.modelId === b?.modelId;
function stored<T>(key: string): T | null { try { return JSON.parse(sessionStorage.getItem(key) ?? 'null'); } catch { return null; } }
const request = <T,>(path = '', signal?: AbortSignal) => studioRequest<T>('/api/settings/fallback',path,'','GET',undefined,signal);

export function VisionFallbackPanel({setLeaveGuard}: {setLeaveGuard: (guard: () => boolean) => void}) {
 const [saved,setSaved] = useState<VisionSettings | null>(null), [chosen,setChosen] = useState<VisionSelection | null>(null);
 const [baseRevision,setBaseRevision] = useState(0), [pending,setPending] = useState<VisionSettingsInput | null>(() => stored(PENDING));
 const [busy,setBusy] = useState(false), [error,setError] = useState(''), [epoch,setEpoch] = useState(0), [retry,setRetry] = useState(false);
 const dirty = !!saved && !same(chosen,saved.vision), conflict = !!saved && baseRevision !== saved.revision;
 const guard = useCallback(() => !busy && !pending && (!dirty || window.confirm('Discard unsaved fallback changes?')), [busy,pending,dirty]);
 useEffect(() => { setLeaveGuard(guard); return () => setLeaveGuard(() => true); }, [guard,setLeaveGuard]);
 useEffect(() => { const warn = (e: BeforeUnloadEvent) => { if (dirty || pending || busy) e.preventDefault(); }; window.addEventListener('beforeunload',warn); return () => window.removeEventListener('beforeunload',warn); }, [dirty,pending,busy]);
 useEffect(() => {
  const controller = new AbortController();
  void (async () => {
   try {
    let value = await request<VisionSettings>('',controller.signal);
    const ticket = stored<VisionSettingsInput>(PENDING);
    if (ticket) {
     try {
      await request('/requests/'+ticket.requestId,controller.signal);
      if (controller.signal.aborted) return;
      sessionStorage.removeItem(PENDING); sessionStorage.removeItem(DRAFT); setPending(null); setRetry(false);
      value = await request<VisionSettings>('',controller.signal);
     } catch (cause) {
      if (controller.signal.aborted) return;
      setPending(ticket); setRetry((cause as ProjectRequestError).status === 404);
      setError('The original save is unconfirmed. Check its receipt or retry that same request.');
     }
    }
    if (!controller.signal.aborted) {
     const draft = stored<{vision:VisionSelection | null;revision:number}>(DRAFT);
     setSaved(value); setChosen(draft ? draft.vision : value.vision); setBaseRevision(draft ? draft.revision : value.revision);
     if (!stored(PENDING)) setError('');
    }
   } catch (cause) { if (!controller.signal.aborted) setError((cause as Error).message); }
  })();
  return () => controller.abort();
 }, [epoch]);
 function choose(vision: VisionSelection | null) {
  if (!saved) return;
  sessionStorage.setItem(DRAFT,JSON.stringify({vision,revision:baseRevision})); setChosen(vision); setError('');
 }
 async function save(vision: VisionSelection | null, original?: VisionSettingsInput) {
  if (!saved || busy) return;
  const input = original ?? {requestId:projectRequestId(),revision:vision === null ? saved.revision : baseRevision,vision};
  sessionStorage.setItem(PENDING,JSON.stringify(input)); setPending(input); setBusy(true); setRetry(false); setError('');
  try {
   await studioRequest('/api/settings/fallback','',saved.csrfToken,'POST',input);
   const value = await request<VisionSettings>();
   sessionStorage.removeItem(PENDING); sessionStorage.removeItem(DRAFT); setPending(null); setSaved(value); setChosen(value.vision); setBaseRevision(value.revision);
  } catch (cause) {
   if ([400,403,409].includes((cause as ProjectRequestError).status)) {
    sessionStorage.removeItem(PENDING); setPending(null); setError((cause as Error).message); setEpoch(n => n+1);
   } else { setError('The save response was not confirmed. Reading its original receipt.'); setEpoch(n => n+1); }
  } finally { setBusy(false); }
 }
 const savedProvider = saved?.providers.find(p => p.id === saved.vision?.providerId);
 const savedModel = savedProvider?.models.find(m => m.id === saved?.vision?.modelId);
 const provider = saved?.providers.find(p => p.id === chosen?.providerId), model = provider?.models.find(m => m.id === chosen?.modelId);
 return <form className="system-prompt-panel vision-fallback" aria-label="Fallback settings" onSubmit={e => { e.preventDefault(); void save(chosen); }}>
  <h2>Vision</h2><p>Only requested image analysis uses this connection. The session’s main model stays unchanged.</p>
  {!saved && !error && <p role="status">Loading fallback settings…</p>}
  {saved && <>
   <p className="vision-fallback-state" role="status">{saved.state}</p>
   {saved.reason && <p>{saved.reason}</p>}
   {saved.vision && <p className="vision-fallback-saved">Saved: {savedProvider?.name ?? saved.vision.providerId} / {savedModel?.name ?? saved.vision.modelId}</p>}
   <label htmlFor="vision-connection">Connection</label>
   <select id="vision-connection" value={chosen?.providerId ?? ''} disabled={busy || !!pending} onChange={e => choose(e.target.value ? {providerId:e.target.value,modelId:''} : null)}>
    <option value="">Not configured</option>
    {chosen && !provider && <option value={chosen.providerId}>Unavailable saved connection</option>}
    {saved.providers.map(p => <option key={p.id} value={p.id} disabled={!p.enabled}>{p.name}{!p.enabled ? ' · Unavailable' : ''}</option>)}
   </select>
   <label htmlFor="vision-model">Model</label>
   <select id="vision-model" value={chosen?.modelId ?? ''} disabled={busy || !!pending || !provider} onChange={e => choose({providerId:chosen!.providerId,modelId:e.target.value})}>
    <option value="">Select a Vision model</option>
    {chosen?.modelId && !model && <option value={chosen.modelId}>Unavailable saved model: {chosen.modelId}</option>}
    {provider?.models.map(m => <option key={m.id} value={m.id} disabled={!m.available}>{m.name}{m.available ? '' : ' · Unavailable'}</option>)}
   </select>
   {(model?.reason || provider?.reason) && <p>{model?.reason ?? provider?.reason}</p>}
   {conflict && <p role="alert">The saved revision changed. Your draft was retained. Cancel it to load the current selection.</p>}
  </>}
  {error && <p className="system-prompt-error" role="alert">{error}</p>}
  {pending ? <div className="system-prompt-actions">
   <button type="button" disabled={busy} onClick={() => setEpoch(n => n+1)}>Check original save</button>
   {retry && <button type="button" disabled={busy} onClick={() => void save(pending.vision,pending)}>Retry original save</button>}
  </div> : saved ? <div className="system-prompt-actions">
   <button type="button" disabled={busy || !saved.vision} onClick={() => void save(null)}>Clear</button>
   <div className="system-prompt-save-actions">
    <button type="button" disabled={busy || !dirty && !conflict} onClick={() => { sessionStorage.removeItem(DRAFT); setChosen(saved.vision); setBaseRevision(saved.revision); setError(''); }}>Cancel</button>
    <button type="submit" className="system-prompt-primary" disabled={busy || !dirty || conflict || !chosen || !model?.available}>{busy ? 'Saving…' : 'Save'}</button>
   </div>
  </div> : <button type="button" onClick={() => setEpoch(n => n+1)}>Reload settings</button>}
 </form>;
}
