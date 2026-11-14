import { deferView } from '../../app/DeferredView';
import { flushSync } from 'react-dom';
import { applyDeltas, SessionDeltas } from './sessionDeltas';
import { publishSessionActivity } from './sessionActivity';
import { invalidateSessionReads } from './sessionReads';
import { useEnvironmentNotes } from './useEnvironmentNotes';
import { SessionStatistics, GoalRuntime } from '../statistics/SessionStatistics';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { AgentEvent, AgentRun, AgentSession, SessionContext, SessionHistory, SessionItem } from '../../../../shared/agent-sessions';
import { useSessionApi, sessionPath, busyRun, isLocalReadBusy, ProjectRequestError } from './api';
import { clearDeletedSession, pendingDeletion } from './sessionDeletionStorage';
import { Icon } from '../../app/Icon';
import { SessionTranscript } from './SessionTranscript';
import { QuotaWaitStatus } from './QuotaWaitStatus';
import { useQuotaWait } from './useQuotaWait';
import type { SessionQuotaWait } from '../../../../shared/agent-sessions';
import { ProviderRetryStatus } from './ProviderRetryStatus';
import { ComposerSettings } from './ComposerSettings';
import { useGoal } from './useGoal';
import { GoalControls, GoalEditor, goalLabel } from './GoalControls';
import type { SessionGoal } from '../../../../shared/agent-inputs';
import { useAttachments } from './useAttachments';
import { AttachmentButton, AttachmentCards } from './AttachmentComposer';
import { useMessageComposer } from './useMessageComposer';
import { useMessageInbox } from './useMessageInbox';
import { MessageQueue } from './MessageQueue';
import { useTranscriptFollow } from './useTranscriptFollow';
import {mergeSession} from './sessionState';

const EnvironmentNotes = deferView(() => import('./EnvironmentNotes').then(module => ({default: module.EnvironmentNotes})), props => props.close());
const ScreenshotGallery = deferView(() => import('./ScreenshotGallery').then(module => ({default: module.ScreenshotGallery})), props => props.close());
const DeleteSessionDialog = deferView(() => import('./DeleteSessionDialog').then(module => ({default: module.DeleteSessionDialog})));
const SessionSettings = deferView(() => import('./SessionSettings').then(module => ({default: module.SessionSettings})), props => props.close());
const itemKey = (item: SessionItem) => item.runId + ':' + item.id;
function merge(previous: SessionItem[], value: SessionItem) {
  return previous.some((p) => itemKey(p) === itemKey(value)) ? previous.map((p) => itemKey(p) === itemKey(value) ? value : p) : [...previous, value];
}

export function SessionPanel({ projectId, sessionId, token, changed, refreshAuth, dirtyChanged, busyChanged, removed }: {
  projectId: string; sessionId: string; token: string; changed: () => void; refreshAuth: () => Promise<void>;
  dirtyChanged: (value: boolean) => void; busyChanged: (value: boolean) => void;
  removed: () => void;
}) {
  const { request: projectRequest, base: apiBase, scope } = useSessionApi();
  const base = sessionPath(projectId, sessionId);
  const selectionScope=scope+':'+projectId+':'+sessionId,currentScope=useRef(selectionScope);
  useLayoutEffect(()=>{currentScope.current=selectionScope;},[selectionScope]);
  const [session, setSession] = useState<AgentSession | null>(null), [items, setItems] = useState<SessionItem[]>([]);
  const [before, setBefore] = useState<number | null>(null), [error, setError] = useState('');
  const [connection, setConnection] = useState('Connecting'), [stopping, setStopping] = useState(false);
  const log = useRef<HTMLDivElement>(null), transcriptContent = useRef<HTMLDivElement>(null), last = useRef(0);
  const projectSession = scope === 'project', transcript = useTranscriptFollow(log, transcriptContent, items, true);
  const scheduleTranscript = transcript.schedule;
  const [older, setOlder] = useState(false);
  const [settings, setSettings] = useState(false);
  const [gallery,setGallery]=useState(false);
  const [liveText,setLiveText]=useState<{runId:string;itemId:string}|null>(null);
  const assistantIds=useRef(new Set<string>());
  const [deltas] = useState(() => new SessionDeltas(values => {
    setItems(old => applyDeltas(old, values));
    const last = values.at(-1);
    if (last?.live && last.field === 'text')
      setLiveText(old => old?.runId === last.runId && old.itemId === last.itemId ? old : {runId:last.runId,itemId:last.itemId});
  }));
  const flushDeltas = () => flushSync(deltas.flush);
  const [deleting, setDeleting] = useState(() => !!pendingDeletion(scope, projectId, sessionId));
  const removedRef = useRef(removed), retired = useRef(false);
  useEffect(() => { removedRef.current = removed; }, [removed]);
  const deleted = useCallback(() => {
    if (retired.current) return;
    retired.current = true;
    try { clearDeletedSession(scope, projectId, sessionId); } catch { /* Confirmed deletion still clears the selection. */ }
    setDeleting(false); setSettings(false); setGallery(false); setLiveText(null); dirtyChanged(false); busyChanged(false); changed(); removedRef.current();
  }, [scope, projectId, sessionId, dirtyChanged, busyChanged, changed]);
  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return;
    const channel = new BroadcastChannel('studio-session-lifetimes');
    channel.onmessage = event => { const value = event.data; if (value?.deleted === true && value.scope === scope && value.owner === projectId && value.sid === sessionId) deleted(); };
    return () => channel.close();
  }, [scope, projectId, sessionId, deleted]);
  const [statistics, setStatistics] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const notes = useEnvironmentNotes(projectId, sessionId, refreshAuth, showNotes);
  const observeNotes = notes.observe;
  const [choiceSaving, setChoiceSaving] = useState(false);
  const [choiceUnconfirmed,setChoiceUnconfirmed]=useState(false);
  const [goalEditor, setGoalEditor] = useState(false);
  const [dragging, setDragging] = useState(false), dragDepth = useRef(0);
  const attachments = useAttachments(projectId, sessionId, session, token, refreshAuth);
  const acceptAttachments = attachments.accepted;
  const resumeTranscript=transcript.resume;
  const accepted = useCallback((ids: string[], acceptedRun?: AgentRun) => {
    acceptAttachments(ids); if (acceptedRun) setSession(old => old ? { ...old, latestRun: acceptedRun } : old);
    if (scope !== 'project') resumeTranscript();
    changed();
  }, [acceptAttachments, changed, scope, resumeTranscript]);
  const composer = useMessageComposer(projectId, sessionId, session, token, refreshAuth, accepted);
  const { text, pending, sending } = composer;
  const inbox = useMessageInbox(projectId, sessionId, token, refreshAuth);

  const refreshSession = useCallback(async () => {
    const result = await projectRequest<{ session: AgentSession }>(base);
    if(currentScope.current===selectionScope)setSession(old=>mergeSession(old,result.session));
  }, [base, projectRequest,selectionScope]);
  const acceptQuota=useCallback((value:SessionQuotaWait,snapshot?:AgentSession)=>{
    if(retired.current||currentScope.current!==selectionScope)return;
    if(value.owner&&(value.owner.type!==scope||value.owner.id!==projectId)||value.sessionId&&value.sessionId!==sessionId)return;
    setSession(old=>{
      const current=snapshot&&snapshot.id===sessionId&&snapshot.owner.id===projectId&&snapshot.owner.type===scope?mergeSession(old,snapshot):old;
      return current&&value.revision>(current.quotaWait?.revision??0)?{...current,quotaWait:value}:current;
    });
  },[selectionScope,scope,projectId,sessionId]);
  const quotaControl=useQuotaWait(projectId,sessionId,token,session?.quotaWait,acceptQuota,refreshAuth);
  const goal = useGoal(projectId, sessionId, session, token, refreshAuth, refreshSession);
  const observeGoal = goal.observe;
  useEffect(() => {
    busyChanged(choiceSaving || sending || stopping || goal.posting || quotaControl.busy); return () => busyChanged(false);
  }, [choiceSaving, sending, stopping, goal.posting, quotaControl.busy, busyChanged]);
  const load = useCallback(async (signal: AbortSignal) => {
    const [h, r] = await Promise.all([projectRequest<SessionHistory>(base + '/history', '', 'GET', undefined, signal),
      projectRequest<{ session: AgentSession }>(base, '', 'GET', undefined, signal)]);
    if (signal.aborted||currentScope.current!==selectionScope) return;
    deltas.clear(); last.current = h.cursor; assistantIds.current=new Set(h.items.filter(i=>i.type==='assistant').map(itemKey));setLiveText(null);setItems(h.items); setBefore(h.before); setSession(old=>mergeSession(old,r.session)); setError('');
  }, [base, projectRequest, deltas,selectionScope]);
  useEffect(() => {
    const controller = new AbortController(); let source: EventSource | undefined, timer: number | undefined, attempt = 0, loaded = false, connected = false;
    const receive = (event: AgentEvent) => {
      if (event.seq <= last.current) return;
      last.current = event.seq;
      if (event.kind !== 'delta') deltas.flush();
      publishSessionActivity({scope,ownerId:projectId,sessionId,event});
      const live=event.delivery==='live'&&!document.hidden;
      if(!live)setLiveText(old=>old===null?old:null);
      if (projectSession && ['run', 'goal', 'nativeTurn'].includes(event.kind)) window.dispatchEvent(new Event('studio-project-activity'));
      if (event.kind === 'item') {
        const item=event.payload as SessionItem,key=itemKey(item);
        if(item.type==='assistant')assistantIds.current.add(key);else assistantIds.current.delete(key);
        if(live&&item.type==='assistant'&&item.status==='running')setLiveText({runId:item.runId,itemId:item.id});
        else if(item.type==='tool'||item.type==='terminal')setLiveText(null);
        else setLiveText(old=>old?.runId===item.runId&&old.itemId===item.id?null:old);
        setItems(old=>merge(old,item));if(item.tool==='studio.save_skill'&&item.status==='completed')changed();
      }
      if (event.kind === 'itemStatus') {
        const p = event.payload as { itemId: string; status: string; error: string };
        setItems((old) => old.map((i) => i.id === p.itemId && i.runId === event.runId ? { ...i, status: p.status, error: p.error } : i));
      }
      if (event.kind === 'delta') {
        const p = event.payload as { itemId: string; text: string; field?: string };
        const field = p.field === 'output' ? 'output' : 'text';
        if (event.runId) deltas.push({runId:event.runId,itemId:p.itemId,field,text:p.text,live:live&&field==='text'&&assistantIds.current.has(event.runId+':'+p.itemId)});
      }
      if (event.kind === 'run') {
        const run=event.payload as AgentRun;
        setSession(s => s ? {...s,latestRun:run,...(run.state==='unknown' && s.context ? {context:{...s.context,state:'stale',reason:'The latest execution is unconfirmed. This is the last measured context.'}} : {})} : s);
        changed();
      }
      if (event.kind === 'context') {
        const value=event.payload as SessionContext;
        if (value.schema===1 && value.sessionId===sessionId && value.owner.type===scope && value.owner.id===projectId)
          setSession(s => s && value.revision>(s.context?.revision ?? 0) ? {...s,context:value} : s);
      }
      if(event.kind==='quotaWait')acceptQuota(event.payload as SessionQuotaWait);
      if(event.kind==='modelChoice')void projectRequest<{session:AgentSession}>(base,'','GET',undefined,controller.signal).then(result=>{
        if(!controller.signal.aborted&&currentScope.current===selectionScope&&result.session.id===sessionId&&result.session.owner.type===scope&&result.session.owner.id===projectId)
          setSession(old=>mergeSession(old,result.session));
      }).catch(()=>{/* Original choice stays visible until its next confirmed read. */});
      if (event.kind === 'environmentNotes') observeNotes(event.payload as { revision: number; count: number });
      if (event.kind === 'goal') observeGoal(event.payload as SessionGoal);
      if (event.kind === 'notice') {
        const notice = event.payload as { text: string };
        setItems((old) => merge(old, { id: 'notice-' + event.seq, runId: event.runId ?? '', type: 'notice', text: notice.text }));
      }
    };
    const connect = () => {
      if (controller.signal.aborted) return;
      source = new EventSource(`${apiBase}${base}/events?after=${last.current}`);
      source.onopen = () => {
        if (controller.signal.aborted) return;
        if (connected) invalidateSessionReads('capabilities');
        connected = true;
        publishSessionActivity({scope, ownerId: projectId, sessionId, connected: true});
        setConnection('Connected'); attempt = 0;
        scheduleTranscript();
        if (projectSession) window.dispatchEvent(new Event('studio-project-activity'));
      };
      source.onmessage = (e) => { if(controller.signal.aborted)return;try { receive(JSON.parse(e.data)); } catch { deltas.flush();setLiveText(null);source?.close(); retry(); } };
      source.onerror = () => { deltas.flush();setLiveText(null);source?.close(); retry(); };
    };
    const retry = () => {
      if (controller.signal.aborted) return;
      window.clearTimeout(timer); setConnection('Reconnecting');
      timer = window.setTimeout(() => { void refreshAuth().then(async () => {
        // A closed SSE can also mean another browser tab deleted this session.
        try {
          const current = await projectRequest<{ session: AgentSession }>(base, '', 'GET', undefined, controller.signal);
          if (controller.signal.aborted || currentScope.current !== selectionScope) return;
          setSession(old => mergeSession(old, current.session));
        } catch (error) {
          if (error instanceof ProjectRequestError && error.status === 410) { deleted(); return; }
          throw error;
        }
        if (!loaded) { await load(controller.signal); loaded = true; } connect();
      }).catch(retry); }, Math.min(1000 * 2 ** attempt++, 10000));
    };
    void load(controller.signal).then(() => { loaded = true; connect(); }).catch((error: Error) => {
      if (controller.signal.aborted) return;
      if (error instanceof ProjectRequestError && error.status === 410) { deleted(); return; }
      if (!isLocalReadBusy(error)) setError(error.message);
      retry();
    });
    return () => { controller.abort(); source?.close(); window.clearTimeout(timer); deltas.clear(); };
  }, [base, load, changed, refreshAuth, apiBase, observeGoal, observeNotes, deleted, projectRequest, projectSession, projectId, sessionId, scope, deltas,selectionScope,acceptQuota,scheduleTranscript]);
  useEffect(()=>{const hidden=()=>{deltas.flush();if(document.hidden)setLiveText(null);};document.addEventListener('visibilitychange',hidden);return()=>document.removeEventListener('visibilitychange',hidden);},[deltas]);
  const run = session?.latestRun;
  const nativeActive = goal.goal?.goal?.status === 'active' && goal.goal.phase !== 'unknown';
  const active = busyRun(run?.state) || nativeActive;
  const waiting = inbox.inbox?.messages.some(value => value.mode === 'queue' && ['queued','dispatching'].includes(value.state)) ?? false;
  const queueMode = active || waiting;
  const blocked = choiceSaving ||choiceUnconfirmed|| settings || deleting || goalEditor || (goal.changing && !goal.claude) || goal.goal?.phase === 'unknown';
  const empty = !text.trim() && !attachments.hasFiles;
  const direct = !!run?.messageSupport && !!run.threadId && !!run.turnId && !attachments.hasFiles;
  const afterResponse = (session?.engine.kind === 'studio' || inbox.boundWaiting && session?.engine.kind === 'claude-code') && run?.messageWaitTarget;
  async function send(now = false, after = false) {
    if (!session || sending || (!pending && (blocked || empty || !!attachments.issue))) return;
    if (now && active && !direct && !afterResponse) { setError('The current turn cannot accept this full input. Use Queue message or wait for its next turn.'); return; }
    if (!pending && queueMode && !inbox.available) { setError('The coordinator cannot queue messages yet. Your draft was preserved.'); return; }
    setError('');
    const steering = now && active && direct && !after;
    await composer.submit(steering ? 'steer' : queueMode ? 'queue' : 'run', attachments.selected.map(value => value.id),
      steering && run?.threadId && run.turnId ? { runId:run.id,threadId:run.threadId,turnId:run.turnId } : undefined,
      false,now && active && !steering && afterResponse ? afterResponse : undefined);
    void inbox.refresh().catch(() => undefined);
  }
  async function stop() {
    deltas.flush(); if (!run || stopping) return; setStopping(true); setError('');
    try {
      const r = await projectRequest<{ run: AgentRun }>(base + '/runs/' + run.id + '/stop', token, 'POST');
      setSession((s) => s ? { ...s, latestRun: r.run } : s); changed();
    } catch (e) { setError((e as Error).message); await refreshAuth(); }
    finally { setStopping(false); }
  }
  async function loadOlder() {
    if (!before || older) return; setOlder(true); setError('');
    try {
      const h = await projectRequest<SessionHistory>(base + `/history?before=${before}`);
      for(const value of h.items)if(value.type==='assistant')assistantIds.current.add(itemKey(value));
      setItems(old => { const known = new Set(old.map(itemKey)); return [...h.items.filter(i => !known.has(itemKey(i))), ...old]; }); setBefore(h.before);
    } catch (error) {
      if (!isLocalReadBusy(error)) setError((error as Error).message);
    } finally { setOlder(false); }
  }
  return <section className="agent-session" aria-label="Agent session" onPointerDownCapture={flushDeltas} onFocusCapture={flushDeltas} onKeyDownCapture={flushDeltas} onCopyCapture={flushDeltas}>
    <header className="agent-header"><h1>{session?.name ?? 'Session'}</h1>
      <div className="agent-header-actions"><span className={`agent-state ${active ? 'active' : ''}`} role="status">{connection === 'Connected' ? (run?.mode === 'goal' && goal.goal?.runId === run.id ? 'Goal · ' + goalLabel(goal, run) : run?.state ? ({queued:'Queued',starting:'Starting',running:'Running',stopping:'Stopping',completed:'Complete',failed:'Failed',interrupted:'Stopped',unknown:'Unconfirmed'} as Record<string,string>)[run.state]??run.state : 'Ready') : connection}</span>
        <button type="button" className="agent-settings-button" aria-label="Screenshot gallery" title="Screenshot gallery" aria-haspopup="dialog" aria-expanded={gallery} disabled={!session} onClick={()=>setGallery(true)}><Icon name="image"/></button>
        <button type="button" className="agent-settings-button" aria-label="Session statistics" title="Session statistics" disabled={!session} onClick={()=>setStatistics(true)}><Icon name="statistics" /></button>
        <button type="button" className={'agent-settings-button agent-notes-button' + (notes.count ? ' has-notes' : '')} aria-label={`Environment notes (${notes.count})`} title="Environment notes" aria-haspopup="dialog" aria-expanded={showNotes} disabled={!session} onClick={() => setShowNotes(true)}><Icon name="note" />{notes.count > 0 && <span className="agent-notes-marker" aria-hidden="true">{notes.count}</span>}</button>
        <button type="button" className="agent-settings-button" aria-label="Session settings" disabled={!session || active || sending || choiceSaving ||choiceUnconfirmed|| !!pending || goal.changing || goalEditor} onClick={() => setSettings(true)}><Icon name="settings" /></button></div></header>
    {session && session.engine.kind !== 'studio' && <p className="agent-plan-usage" role="status">Native {session.engine.kind === 'claude-code' ? 'Claude' : 'OpenAI'} conversation. Review an explicit conversion under Session settings → Conversation to use the Studio runtime.</p>}
    {session?.engine.kind==='studio'&&session.engine.api?.kind==='chatgpt-plan'&&<p className="agent-plan-usage">ChatGPT plan · Remaining allowance is not reported here. <a href="https://chatgpt.com/settings/usage" target="_blank" rel="noopener noreferrer">Manage plan usage</a></p>}
    <div className="agent-log" ref={log} role="log" aria-label="Session messages" aria-live="off" tabIndex={0} data-following={transcript.following}
      onWheel={transcript.onWheel} onScroll={transcript.onScroll} onKeyDown={transcript.onKeyDown}
      onPointerDown={transcript.onPointerDown} onTouchStart={transcript.onTouchStart} onTouchMove={transcript.onTouchMove}>
      <div ref={transcriptContent}>
      {!items.length && session && <p className="agent-empty">Start a conversation.</p>}
      <SessionTranscript before={before} older={older} loadOlder={loadOlder} log={log} following={transcript.following} pauseFollowing={transcript.pause} resumeFollowing={transcript.resume} viewChanged={transcript.viewChanged} items={items} projectId={projectId} sessionId={sessionId} token={token} liveText={active&&run?.id===liveText?.runId?liveText:null}/>
      </div>
    </div>
    <ProviderRetryStatus key={base} run={run}/>
    <QuotaWaitStatus wait={session?.quotaWait} run={run} control={quotaControl}/>
    {run?.error && !items.some((i) => i.runId === run.id && i.type === 'notice' && i.text === run.error) && <p className="agent-error" role="alert">{run.error}</p>}
    {error && <p className="agent-error" role="alert">{error}</p>}
    {composer.error && <p className="agent-error" role="status">{composer.error}</p>}
    <MessageQueue control={inbox} />
    <form className={'agent-composer' + (projectSession && transcript.following ? ' agent-following' : '') + (dragging ? ' dragging' : '')}
      data-following={projectSession ? transcript.following : undefined}
      title={projectSession ? transcript.following ? 'Following latest messages. Scroll up to pause.' : 'Following paused. Scroll to the bottom to resume.' : undefined}
      onSubmit={(e) => { e.preventDefault(); void send(); }}
      onDragEnter={event => { if (event.dataTransfer.types.includes('Files')) { event.preventDefault(); dragDepth.current++; setDragging(true); } }}
      onDragOver={event => { if (event.dataTransfer.types.includes('Files')) { event.preventDefault(); event.dataTransfer.dropEffect = sending || pending ? 'none' : 'copy'; } }}
      onDragLeave={event => { if (event.dataTransfer.types.includes('Files')) { event.preventDefault(); if (--dragDepth.current <= 0) { dragDepth.current = 0; setDragging(false); } } }}
      onDrop={event => { if (event.dataTransfer.files.length) { event.preventDefault(); dragDepth.current = 0; setDragging(false); if (session && !sending && !pending && !settings && !goalEditor) attachments.add(Array.from(event.dataTransfer.files)); } }}>
      <textarea aria-label="Message" placeholder="Message the agent…" rows={3} maxLength={65536} value={text} disabled={!session}
        onChange={(e) => composer.edit(e.target.value)}
        onPaste={event => {
          const images = Array.from(event.clipboardData.items).filter(item => item.kind === 'file' && item.type.startsWith('image/')).flatMap(item => { const file = item.getAsFile(); return file ? [file] : []; });
          if (images.length) { event.preventDefault(); if (session && !sending && !pending && !settings && !goalEditor) attachments.add(images); }
        }}
        onKeyDown={(e) => {
          if (e.key !== 'Enter' || e.nativeEvent.isComposing || e.nativeEvent.keyCode === 229) return;
          if (e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey) return;
          e.preventDefault();
          if (e.repeat || e.shiftKey || e.metaKey || e.altKey) return;
          void send(e.ctrlKey);
        }} />
      <AttachmentCards control={attachments} disabled={sending || !!pending} />
      <div className="agent-composer-footer">
        <GoalControls control={goal} run={run} disabled={!session || choiceSaving ||choiceUnconfirmed|| settings || stopping} inputBusy={sending || !!pending}
          runtime={<GoalRuntime ownerId={projectId} sessionId={sessionId} reauth={refreshAuth} goal={goal.goal} pending={goal.pending} active={goal.goal?.goal?.status === 'active' || goal.goal?.phase === 'pending' || goal.goal?.phase === 'pausing'} />} editor={goalEditor} openEditor={() => setGoalEditor(true)} />
        {session && <ComposerSettings key={base} session={session} projectId={projectId} token={token} active={active} disabled={sending || !!pending || settings || goal.changing || goalEditor}
          busyChanged={setChoiceSaving} unconfirmedChanged={setChoiceUnconfirmed} refreshAuth={refreshAuth} saved={(value) => {
            if(currentScope.current===selectionScope&&value.id===sessionId&&value.owner.id===projectId&&value.owner.type===scope){setSession(old=>mergeSession(old,value));changed();}
          }} />}
        <AttachmentButton control={attachments} disabled={!session || sending || !!pending || settings || goalEditor} />
        <div className="agent-compose-actions">{busyRun(run?.state) && <button type="button" className="agent-stop" disabled={stopping || run?.state === 'stopping'} title="Stop the current run" onClick={() => void stop()}>{stopping || run?.state === 'stopping' ? 'Stopping…' : 'Stop'}</button>}
          {active && <button type="button" title={direct && session?.engine.kind === 'studio' ? 'Accept before the next model turn; the current request stays unchanged' : afterResponse ? 'Wait for this response, then continue the same conversation' : 'Append to the original active turn'} disabled={sending || !!pending || blocked || empty || !!attachments.issue || (!direct && !afterResponse)} onClick={() => void send(true)}>{direct ? 'Send now' : afterResponse ? 'After response' : 'Send now'}</button>}
          {active && direct && afterResponse && <button type="button" disabled={sending || !!pending || blocked || empty || !!attachments.issue} onClick={() => void send(true,true)}>After response</button>}
          <button className="agent-send" disabled={sending || !session || (!pending && (blocked || empty || !!attachments.issue || queueMode && !inbox.available))}>{sending ? 'Sending…' : pending ? 'Check original request' : queueMode ? 'Queue message' : 'Send'}</button></div>
      </div>
      {active && attachments.hasFiles && <p className="agent-keyboard-hint">{afterResponse ? 'The complete input and its attachments will wait for this response.' : 'Queue the complete input with its attachments. Direct delivery supports text only.'}</p>}
      {pending && <div className="agent-pending-message" aria-label="Preserved original message">
        <details><summary>Original request · {composer.receipt?.state ?? 'checking'}</summary><p>{pending.input.text}</p></details>
        {composer.receipt?.state === 'unknown' && <p>Acceptance is unconfirmed. Check the original request before submitting another copy.</p>}
        <button type="button" disabled={sending} onClick={() => void composer.submit('run', [], undefined, true)}>Retry same request</button>
        <button type="button" disabled={sending || composer.receipt?.state === 'pending' || composer.receipt?.state === 'dispatching'} onClick={composer.restore}>Use preserved input</button>
      </div>}
      {goal.goal?.phase === 'pausing' && <p className="agent-goal-message" role="status">Pausing after current turn.</p>}
      {!goal.execution && goal.available && <p className="agent-goal-message" role="status">Finish current runs before starting a Goal.</p>}
      {goal.goal?.phase === 'unknown' && <p className="agent-goal-message" role="status">The original Goal state is unconfirmed. Pause or Stop before resuming.</p>}
      {goal.error && <p className="agent-goal-message error" role="alert">{goal.error}</p>}
      {(goal.checkAgain || !goal.available || goal.goal?.phase === 'unknown') && <div className="agent-goal-recovery"><button type="button" disabled={goal.posting || goal.checking} onClick={() => void goal.check()}>Check Goal status</button>
        {goal.pending && <button type="button" disabled={goal.posting} onClick={() => void goal.retry()}>Retry same Goal request</button>}</div>}
    </form>
    {goalEditor && <GoalEditor control={goal} run={run} close={() => setGoalEditor(false)} dirtyChanged={dirtyChanged} />}
    {showNotes && session && <EnvironmentNotes key={notes.key} session={session} notes={notes} token={token} reauth={refreshAuth} close={() => setShowNotes(false)} run={run} stop={stop} />}
    {statistics && <SessionStatistics ownerId={projectId} sessionId={sessionId} reauth={refreshAuth} close={()=>setStatistics(false)} run={run} stop={stop} />}
    {gallery&&<ScreenshotGallery key={base} ownerId={projectId} sessionId={sessionId} reauth={refreshAuth} close={()=>setGallery(false)} run={run} stop={stop}/>}
    {settings && session && <SessionSettings session={session} projectId={projectId} token={token} reloaded={value=>setSession(old=>mergeSession(old,value))} dirtyChanged={dirtyChanged} busyChanged={busyChanged} deleteSession={() => setDeleting(true)} close={() => setSettings(false)} saved={(s) => { setSession(old=>mergeSession(old,s)); setSettings(false); changed(); }} />}
    {deleting && <DeleteSessionDialog projectId={projectId} sessionId={sessionId} token={token} reauth={refreshAuth} close={() => setDeleting(false)} deleted={deleted} />}
  </section>;
}
