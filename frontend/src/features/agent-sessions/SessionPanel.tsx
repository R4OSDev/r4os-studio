import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { AgentEvent, AgentRun, AgentSession, SessionHistory, SessionItem } from '../../../../shared/agent-sessions';
import { projectRequest, projectRequestId, ProjectRequestError, sessionPath, busyRun, toolLabels } from './api';

type Pending = { requestId: string; revision: number; text: string };
function readPending(key: string): Pending | null {
  try { const v = JSON.parse(sessionStorage.getItem(key) ?? 'null'); return v && typeof v.requestId === 'string' && typeof v.text === 'string' && Number.isInteger(v.revision) ? v : null; } catch { return null; }
}
const itemKey = (item: SessionItem) => item.runId + ':' + item.id;
function merge(previous: SessionItem[], value: SessionItem) {
  return previous.some((p) => itemKey(p) === itemKey(value)) ? previous.map((p) => itemKey(p) === itemKey(value) ? value : p) : [...previous, value];
}

export function SessionPanel({ projectId, sessionId, token, changed, refreshAuth }: {
  projectId: string; sessionId: string; token: string; changed: () => void; refreshAuth: () => Promise<void>;
}) {
  const base = sessionPath(projectId, sessionId), pendingKey = 'studio.session.run.' + sessionId, draftKey = 'studio.session.draft.' + sessionId;
  const [session, setSession] = useState<AgentSession | null>(null), [items, setItems] = useState<SessionItem[]>([]);
  const [before, setBefore] = useState<number | null>(null), [error, setError] = useState('');
  const [connection, setConnection] = useState('Connecting'), [sending, setSending] = useState(false), [stopping, setStopping] = useState(false);
  const [pending, setPending] = useState(() => readPending(pendingKey));
  const [text, setText] = useState(() => { try { return sessionStorage.getItem(draftKey) ?? ''; } catch { return ''; } });
  const log = useRef<HTMLDivElement>(null), follow = useRef(true), last = useRef(0);
  const [older, setOlder] = useState(false);
  const load = useCallback(async (signal: AbortSignal) => {
    const h = await projectRequest<SessionHistory>(base + '/history', '', 'GET', undefined, signal);
    const r = await projectRequest<{ session: AgentSession }>(base, '', 'GET', undefined, signal);
    if (signal.aborted) return;
    last.current = h.cursor; setItems(h.items); setBefore(h.before); setSession(r.session); setError('');
  }, [base]);
  useEffect(() => {
    const controller = new AbortController(); let source: EventSource | undefined, timer: number | undefined, attempt = 0, loaded = false;
    const receive = (event: AgentEvent) => {
      if (event.seq <= last.current) return;
      last.current = event.seq;
      if (event.kind === 'item') setItems((old) => merge(old, event.payload as SessionItem));
      if (event.kind === 'delta') {
        const p = event.payload as { itemId: string; text: string; field?: string };
        const field = p.field === 'output' ? 'output' : 'text';
        setItems((old) => old.map((i) => i.id === p.itemId && i.runId === event.runId ? { ...i, [field]: String(i[field] ?? '') + p.text } : i));
      }
      if (event.kind === 'run') { setSession((s) => s ? { ...s, latestRun: event.payload as AgentRun } : s); changed(); }
      if (event.kind === 'notice') {
        const notice = event.payload as { text: string };
        setItems((old) => merge(old, { id: 'notice-' + event.seq, runId: event.runId ?? '', type: 'notice', text: notice.text }));
      }
    };
    const connect = () => {
      if (controller.signal.aborted) return;
      source = new EventSource(`/api/projects${base}/events?after=${last.current}`);
      source.onopen = () => { if (!controller.signal.aborted) { setConnection('Connected'); attempt = 0; } };
      source.onmessage = (e) => { try { receive(JSON.parse(e.data)); } catch { source?.close(); retry(); } };
      source.onerror = () => { source?.close(); retry(); };
    };
    const retry = () => {
      if (controller.signal.aborted) return;
      window.clearTimeout(timer); setConnection('Reconnecting');
      timer = window.setTimeout(() => { void refreshAuth().then(async () => { if (!loaded) { await load(controller.signal); loaded = true; } connect(); }).catch(retry); }, Math.min(1000 * 2 ** attempt++, 10000));
    };
    void load(controller.signal).then(() => { loaded = true; connect(); }).catch((e: Error) => { if (!controller.signal.aborted) { setError(e.message); retry(); } });
    return () => { controller.abort(); source?.close(); window.clearTimeout(timer); };
  }, [base, load, changed, refreshAuth]);
  useEffect(() => {
    if (follow.current) log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [items]);
  const run = session?.latestRun, active = busyRun(run?.state);
  async function send(event: FormEvent) {
    event.preventDefault(); if (!session || sending || (!pending && (active || !text.trim()))) return;
    const data = pending ?? { requestId: projectRequestId(), revision: session.revision, text };
    try { sessionStorage.setItem(pendingKey, JSON.stringify(data)); } catch { setError('Enable session storage before sending.'); return; }
    setPending(data); setSending(true); setError('');
    try {
      const r = await projectRequest<{ run: AgentRun }>(base + '/runs', token, 'POST', data);
      setSession((s) => s ? { ...s, latestRun: r.run } : s); sessionStorage.removeItem(pendingKey); sessionStorage.removeItem(draftKey);
      setPending(null); setText(''); follow.current = true; changed();
    } catch (e) {
      const failure = e as ProjectRequestError;
      if (failure.status && failure.status < 500) { sessionStorage.removeItem(pendingKey); setPending(null); }
      setError(failure.message);
      if (failure.status === 403) await refreshAuth();
    } finally { setSending(false); }
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
    <header className="agent-header"><div><h2>{session?.name ?? 'Session'}</h2><span className="agent-model">{session?.model}</span></div>
      <span className={`agent-state ${active ? 'active' : ''}`} role="status">{connection === 'Connected' ? (run?.state ?? 'Ready') : connection}</span></header>
    <div className="agent-log" ref={log} role="log" aria-label="Session messages" aria-live="off" onScroll={(e) => { const el = e.currentTarget; follow.current = el.scrollHeight-el.scrollTop-el.clientHeight < 90; }}>
      {before && <button className="agent-older" disabled={older} onClick={() => void loadOlder()}>{older ? 'Loading…' : 'Load earlier messages'}</button>}
      {!items.length && session && <p className="agent-empty">Start a conversation.</p>}
      {items.map((i) => i.type === 'tool' || i.type === 'terminal' ? <details key={itemKey(i)} className={`agent-tool ${i.status ?? ''}`}>
        <summary><span>{i.type === 'terminal' ? 'Terminal' : toolLabels[i.tool ?? ''] ?? 'Tool call'}</span><span className="agent-tool-status">{i.status}</span></summary>
        <pre className="agent-arguments">{JSON.stringify(i.arguments, null, 2)}</pre>
        {i.output && <pre>{i.output}</pre>}{i.truncated === true && <p>Output truncated.</p>}
        {i.exitCode != null && <p>Exit code {i.exitCode}</p>}{i.error && <p>{i.error}</p>}
      </details> : <article key={itemKey(i)} className={`agent-message ${i.type}`}>
        {i.type !== 'notice' && <div className="agent-message-role">{i.type === 'user' ? 'You' : 'Agent'}</div>}<div className="agent-message-text">{i.text}</div>
      </article>)}
    </div>
    {run?.error && <p className="agent-error" role="alert">{run.error}</p>}
    {error && <p className="agent-error" role="alert">{error}</p>}
    <form className="agent-composer" onSubmit={(e) => void send(e)}>
      <textarea aria-label="Message" placeholder="Message the agent…" rows={3} maxLength={65536} value={pending?.text ?? text} disabled={sending || !!pending || active || !session}
        onChange={(e) => { setText(e.target.value); try { sessionStorage.setItem(draftKey, e.target.value); } catch { /* send reports storage failure */ } }}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} />
      <div className="agent-compose-actions">{active && <button type="button" className="agent-stop" disabled={stopping} onClick={() => void stop()}>{stopping || run?.state === 'stopping' ? 'Stopping…' : 'Stop'}</button>}
        <button className="agent-send" disabled={sending || !session || (!pending && (active || !text.trim()))}>{sending ? 'Sending…' : pending ? 'Retry send' : 'Send'}</button></div>
    </form>
  </section>;
}
