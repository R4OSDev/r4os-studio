import { EnvironmentNotes } from './EnvironmentNotes';
import { useEnvironmentNotes } from './useEnvironmentNotes';
import { SessionClaudeLimits } from './SessionClaudeLimits';
import {ScreenshotGallery} from './ScreenshotGallery';
import type { ClaudeRateObservation } from '../../../../shared/claude-subscription';
import { SessionStatistics, GoalRuntime } from '../statistics/SessionStatistics';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentEvent, AgentRun, AgentSession, SessionContext, SessionHistory, SessionItem } from '../../../../shared/agent-sessions';
import { useSessionApi, sessionPath, busyRun, ProjectRequestError } from './api';
import { DeleteSessionDialog } from './DeleteSessionDialog';
import { clearDeletedSession, pendingDeletion } from './sessionDeletionStorage';
import { SessionSettings } from './SessionSettings';
import { Icon } from '../../app/Icon';
import { SessionTranscript } from './SessionTranscript';
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
  const [session, setSession] = useState<AgentSession | null>(null), [items, setItems] = useState<SessionItem[]>([]);
  const [claudeQuota, setClaudeQuota] = useState<ClaudeRateObservation | null>(null);
  const [before, setBefore] = useState<number | null>(null), [error, setError] = useState('');
  const [connection, setConnection] = useState('Connecting'), [stopping, setStopping] = useState(false);
  const log = useRef<HTMLDivElement>(null), transcriptContent = useRef<HTMLDivElement>(null), follow = useRef(true), last = useRef(0);
  const projectSession = scope === 'project', transcript = useTranscriptFollow(log, transcriptContent, items, projectSession);
  const [older, setOlder] = useState(false);
  const [settings, setSettings] = useState(false);
  const [deleting, setDeleting] = useState(() => !!pendingDeletion(scope, projectId, sessionId));
  const removedRef = useRef(removed), retired = useRef(false);
  useEffect(() => { removedRef.current = removed; }, [removed]);
  const deleted = useCallback(() => {
    if (retired.current) return;
    retired.current = true;
    try { clearDeletedSession(scope, projectId, sessionId); } catch { /* Confirmed deletion still clears the selection. */ }
    setDeleting(false); setSettings(false); dirtyChanged(false); busyChanged(false); changed(); removedRef.current();
  }, [scope, projectId, sessionId, dirtyChanged, busyChanged, changed]);
  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return;
    const channel = new BroadcastChannel('studio-session-lifetimes');
    channel.onmessage = event => { const value = event.data; if (value?.deleted === true && value.scope === scope && value.owner === projectId && value.sid === sessionId) deleted(); };
    return () => channel.close();
  }, [scope, projectId, sessionId, deleted]);
  const [statistics, setStatistics] = useState(false);
  const [gallery,setGallery]=useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const notes = useEnvironmentNotes(projectId, sessionId, refreshAuth);
  const observeNotes = notes.observe;
  const [choiceSaving, setChoiceSaving] = useState(false);
  const [goalEditor, setGoalEditor] = useState(false);
  const [dragging, setDragging] = useState(false), dragDepth = useRef(0);
  const attachments = useAttachments(projectId, sessionId, session, token, refreshAuth);
  const acceptAttachments = attachments.accepted;
  const accepted = useCallback((ids: string[], acceptedRun?: AgentRun) => {
    acceptAttachments(ids); if (acceptedRun) setSession(old => old ? { ...old, latestRun: acceptedRun } : old);
    if (scope !== 'project') follow.current = true;
    changed();
  }, [acceptAttachments, changed, scope]);
  const composer = useMessageComposer(projectId, sessionId, session, token, refreshAuth, accepted);
  const { text, pending, sending } = composer;
  const inbox = useMessageInbox(projectId, sessionId, token, refreshAuth);

  const refreshSession = useCallback(async () => {
    const result = await projectRequest<{ session: AgentSession }>(base);
    setSession(result.session);
  }, [base, projectRequest]);
  const goal = useGoal(projectId, sessionId, session, token, refreshAuth, refreshSession);
  const observeGoal = goal.observe;
  useEffect(() => {
    busyChanged(choiceSaving || sending || stopping || goal.posting); return () => busyChanged(false);
  }, [choiceSaving, sending, stopping, goal.posting, busyChanged]);
  const load = useCallback(async (signal: AbortSignal) => {
    const h = await projectRequest<SessionHistory>(base + '/history', '', 'GET', undefined, signal);
    const r = await projectRequest<{ session: AgentSession }>(base, '', 'GET', undefined, signal);
    if (signal.aborted) return;
    last.current = h.cursor; setItems(h.items); setBefore(h.before); setSession(r.session); setError('');
  }, [base, projectRequest]);
  useEffect(() => {
    const controller = new AbortController(); let source: EventSource | undefined, timer: number | undefined, attempt = 0, loaded = false;
    const receive = (event: AgentEvent) => {
      if (event.seq <= last.current) return;
      last.current = event.seq;
      if (projectSession && ['run', 'goal', 'nativeTurn'].includes(event.kind)) window.dispatchEvent(new Event('studio-project-activity'));
      if (event.kind === 'item') { const item = event.payload as SessionItem; setItems((old) => merge(old, item)); if (item.tool === 'studio.save_skill' && item.status === 'completed') changed(); }
      if (event.kind === 'itemStatus') {
        const p = event.payload as { itemId: string; status: string; error: string };
        setItems((old) => old.map((i) => i.id === p.itemId && i.runId === event.runId ? { ...i, status: p.status, error: p.error } : i));
      }
      if (event.kind === 'delta') {
        const p = event.payload as { itemId: string; text: string; field?: string };
        const field = p.field === 'output' ? 'output' : 'text';
        setItems((old) => old.map((i) => i.id === p.itemId && i.runId === event.runId ? { ...i, [field]: String(i[field] ?? '') + p.text } : i));
      }
      if (event.kind === 'run') {
        const run=event.payload as AgentRun;
        setSession(s => s ? {...s,latestRun:run,...(run.state==='unknown' && s.context ? {context:{...s.context,state:'stale',reason:'The latest native execution is unconfirmed. This is the last measured context.'}} : {})} : s);
        changed();
      }
      if (event.kind === 'context') {
        const value=event.payload as SessionContext;
        if (value.schema===1 && value.sessionId===sessionId && value.owner.type===scope && value.owner.id===projectId)
          setSession(s => s && value.revision>(s.context?.revision ?? 0) ? {...s,context:value} : s);
      }
      if (event.kind === 'environmentNotes') observeNotes(event.payload as { revision: number; count: number });
      if (event.kind === 'claudeQuota') setClaudeQuota(event.payload as ClaudeRateObservation);
      if (event.kind === 'goal') observeGoal(event.payload as SessionGoal);
      if (event.kind === 'notice') {
        const notice = event.payload as { text: string };
        setItems((old) => merge(old, { id: 'notice-' + event.seq, runId: event.runId ?? '', type: 'notice', text: notice.text }));
      }
    };
    const connect = () => {
      if (controller.signal.aborted) return;
      source = new EventSource(`${apiBase}${base}/events?after=${last.current}`);
      source.onopen = () => { if (!controller.signal.aborted) { setConnection('Connected'); attempt = 0; if (projectSession) window.dispatchEvent(new Event('studio-project-activity')); } };
      source.onmessage = (e) => { try { receive(JSON.parse(e.data)); } catch { source?.close(); retry(); } };
      source.onerror = () => { source?.close(); retry(); };
    };
    const retry = () => {
      if (controller.signal.aborted) return;
      window.clearTimeout(timer); setConnection('Reconnecting');
      timer = window.setTimeout(() => { void refreshAuth().then(async () => {
        // A closed SSE can also mean another browser tab deleted this session.
        try { await projectRequest(base); } catch (failure) { if ((failure as ProjectRequestError).status === 410) { deleted(); return; } throw failure; }
        if (!loaded) { await load(controller.signal); loaded = true; } connect();
      }).catch(retry); }, Math.min(1000 * 2 ** attempt++, 10000));
    };
    void load(controller.signal).then(() => { loaded = true; connect(); }).catch((e: ProjectRequestError) => { if (!controller.signal.aborted) { if (e.status === 410) { deleted(); return; } setError(e.message); retry(); } });
    return () => { controller.abort(); source?.close(); window.clearTimeout(timer); };
  }, [base, load, changed, refreshAuth, apiBase, observeGoal, observeNotes, deleted, projectRequest, projectSession, projectId, sessionId, scope]);
  useEffect(() => {
    if (!projectSession && follow.current) log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [items, projectSession, log]);
  const run = session?.latestRun;
  const nativeActive = goal.goal?.goal?.status === 'active' && goal.goal.phase !== 'unknown';
  const active = busyRun(run?.state) || nativeActive;
  const waiting = inbox.inbox?.messages.some(value => value.mode === 'queue' && ['queued','dispatching'].includes(value.state)) ?? false;
  const queueMode = active || waiting;
  const blocked = choiceSaving || settings || deleting || goalEditor || goal.changing || goal.goal?.phase === 'unknown';
  const empty = !text.trim() && !attachments.hasFiles;
  const direct = !!run?.messageSupport && !!run.threadId && !!run.turnId && !attachments.hasFiles;
  async function send(now = false) {
    if (!session || sending || (!pending && (blocked || empty || !!attachments.issue))) return;
    if (now && active && !direct) { setError('The original native turn cannot accept this full input. Use Queue message or wait for its next turn.'); return; }
    if (!pending && queueMode && !inbox.available) { setError('The coordinator cannot queue messages yet. Your draft was preserved.'); return; }
    setError('');
    await composer.submit(now && active ? 'steer' : queueMode ? 'queue' : 'run', attachments.selected.map(value => value.id),
      now && run?.threadId && run.turnId ? { runId:run.id,threadId:run.threadId,turnId:run.turnId } : undefined);
    void inbox.refresh().catch(() => undefined);
  }
  async function stop() {
    if (!run || stopping) return; setStopping(true); setError('');
    try {
      const r = await projectRequest<{ run: AgentRun }>(base + '/runs/' + run.id + '/stop', token, 'POST');
      setSession((s) => s ? { ...s, latestRun: r.run } : s); changed();
    } catch (e) { setError((e as Error).message); await refreshAuth(); }
    finally { setStopping(false); }
  }
  async function loadOlder() {
    if (!before || older) return; setOlder(true);
    const element = log.current, height = element?.scrollHeight ?? 0;
    try {
      const h = await projectRequest<SessionHistory>(base + `/history?before=${before}`);
      setItems((old) => [...h.items.filter((i) => !old.some((p) => itemKey(p) === itemKey(i))), ...old]); setBefore(h.before);
      requestAnimationFrame(() => { if (element) element.scrollTop += element.scrollHeight - height; });
    } catch (e) { setError((e as Error).message); } finally { setOlder(false); }
  }
  return <section className="agent-session" aria-label="Agent session">
    <header className="agent-header"><h1>{session?.name ?? 'Session'}</h1>
      <div className="agent-header-actions"><span className={`agent-state ${active ? 'active' : ''}`} role="status">{connection === 'Connected' ? (run?.mode === 'goal' && goal.goal?.runId === run.id ? 'Goal · ' + goalLabel(goal) : run?.state ?? 'Ready') : connection}</span>
        <button type="button" className="agent-settings-button" aria-label="Screenshot gallery" title="Screenshot gallery" aria-haspopup="dialog" aria-expanded={gallery} disabled={!session} onClick={()=>setGallery(true)}><Icon name="image"/></button>
        <button type="button" className="agent-settings-button" aria-label="Session statistics" title="Session statistics" disabled={!session} onClick={()=>setStatistics(true)}><Icon name="statistics" /></button>
        <button type="button" className={'agent-settings-button agent-notes-button' + (notes.count ? ' has-notes' : '')} aria-label={`Environment notes (${notes.count})`} title="Environment notes" aria-haspopup="dialog" aria-expanded={showNotes} disabled={!session} onClick={() => setShowNotes(true)}><Icon name="note" />{notes.count > 0 && <span className="agent-notes-marker" aria-hidden="true">{notes.count}</span>}</button>
        <button type="button" className="agent-settings-button" aria-label="Session settings" disabled={!session || active || sending || choiceSaving || !!pending || goal.changing || goalEditor} onClick={() => setSettings(true)}><Icon name="settings" /></button></div></header>
    {session?.engine.kind === 'claude-code' && <SessionClaudeLimits key={base} base={base} token={token} observation={claudeQuota?.studioSessionId === sessionId ? claudeQuota : null} />}
    <div className="agent-log" ref={log} role="log" aria-label="Session messages" aria-live="off" tabIndex={projectSession ? 0 : undefined}
      onWheel={projectSession ? transcript.onWheel : undefined}
      onScroll={projectSession ? transcript.onScroll : (e) => { const el = e.currentTarget; follow.current = el.scrollHeight-el.scrollTop-el.clientHeight < 90; }}>
      <div ref={transcriptContent}>
      {before && <button className="agent-older" disabled={older} onClick={() => void loadOlder()}>{older ? 'Loading…' : 'Load earlier messages'}</button>}
      {!items.length && session && <p className="agent-empty">Start a conversation.</p>}
      <SessionTranscript items={items} projectId={projectId} sessionId={sessionId} token={token} />
      </div>
    </div>
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
        <GoalControls control={goal} run={run} disabled={!session || choiceSaving || settings || stopping} inputBusy={sending || !!pending}
          runtime={<GoalRuntime ownerId={projectId} sessionId={sessionId} reauth={refreshAuth} />} editor={goalEditor} openEditor={() => setGoalEditor(true)} stopRun={stop} />
        {session && <ComposerSettings session={session} projectId={projectId} token={token} disabled={active || sending || !!pending || settings || goal.changing || goalEditor}
          busyChanged={setChoiceSaving} refreshAuth={refreshAuth} saved={(value) => { setSession(value); changed(); }} />}
        <AttachmentButton control={attachments} disabled={!session || sending || !!pending || settings || goalEditor} />
        <div className="agent-compose-actions">{busyRun(run?.state) && (run?.mode !== 'goal' || !goal.available || !!goal.error) && <button type="button" className="agent-stop" disabled={stopping} onClick={() => void stop()}>{stopping || run?.state === 'stopping' ? 'Stopping…' : 'Stop'}</button>}
          {active && <button type="button" title={attachments.hasFiles ? 'Queue the complete input with its attachments' : 'Ctrl+Enter: append to the original active turn'} disabled={sending || !!pending || blocked || empty || !direct} onClick={() => void send(true)}>Send now</button>}
          <button className="agent-send" disabled={sending || !session || (!pending && (blocked || empty || !!attachments.issue || queueMode && !inbox.available))}>{sending ? 'Sending…' : pending ? 'Check original request' : queueMode ? 'Queue message' : 'Send'}</button></div>
      </div>
      {!queueMode && <p className="agent-keyboard-hint">Enter: send · Shift+Enter: new line</p>}
      {active && attachments.hasFiles && <p className="agent-keyboard-hint">Queue the complete input with its attachments. Direct delivery supports text only.</p>}
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
    {goalEditor && <GoalEditor control={goal} run={run} stopRun={stop} close={() => setGoalEditor(false)} dirtyChanged={dirtyChanged} />}
    {showNotes && session && <EnvironmentNotes key={notes.key} session={session} notes={notes} token={token} reauth={refreshAuth} close={() => setShowNotes(false)} run={run} stop={stop} />}
    {statistics && <SessionStatistics ownerId={projectId} sessionId={sessionId} reauth={refreshAuth} close={()=>setStatistics(false)} run={run} stop={stop} />}
    {gallery&&<ScreenshotGallery key={base} ownerId={projectId} sessionId={sessionId} reauth={refreshAuth} close={()=>setGallery(false)} run={run} stop={stop}/>}
    {settings && session && <SessionSettings session={session} projectId={projectId} token={token} reloaded={setSession} dirtyChanged={dirtyChanged} busyChanged={busyChanged} deleteSession={() => setDeleting(true)} close={() => setSettings(false)} saved={(s) => { setSession(s); setSettings(false); changed(); }} />}
    {deleting && <DeleteSessionDialog projectId={projectId} sessionId={sessionId} token={token} reauth={refreshAuth} close={() => setDeleting(false)} deleted={deleted} />}
  </section>;
}
