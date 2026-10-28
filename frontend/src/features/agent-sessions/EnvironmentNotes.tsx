import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { AgentRun, AgentSession } from '../../../../shared/agent-sessions';
import type { EnvironmentNote, EnvironmentNoteDeletion } from '../../../../shared/environment-notes';
import { busyRun, projectRequestId, useSessionApi } from './api';
import { useEnvironmentNotes } from './useEnvironmentNotes';
import { environmentNoteRequestKey } from './environmentNoteStorage';
import './environment-notes.css';

type Pending = { requestId: string; noteId?: string; body: Record<string, string | number> };
const uuid = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;
function stored(key: string): Pending | null {
  try {
    const value = JSON.parse(localStorage.getItem(key) ?? 'null') as Pending | null;
    return value && uuid.test(value.requestId) && value.body?.requestId === value.requestId && (!value.noteId || uuid.test(value.noteId)) ? value : null;
  } catch { return null; }
}
export function EnvironmentNotes({ session, notes, token, reauth, close, run, stop }: {
  session: AgentSession; notes: ReturnType<typeof useEnvironmentNotes>; token: string; reauth: () => Promise<void>;
  close: () => void; run?: AgentRun | null; stop: () => Promise<void>;
}) {
  const { request, scope } = useSessionApi(), dialog = useRef<HTMLDialogElement>(null), closeButton = useRef<HTMLButtonElement>(null);
  const storageKey = environmentNoteRequestKey(scope, session.owner.id, session.id);
  const [pending, setPending] = useState<Pending | null>(() => stored(storageKey));
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const [confirm, setConfirm] = useState<{ revision: number; count: number; name: string } | null>(null);
  const [filter, setFilter] = useState({ query: String(notes.query.query ?? ''), kind: String(notes.query.kind ?? ''), category: String(notes.query.category ?? '') });
  const refresh = notes.refresh, observe = notes.observe;
  const finish = useCallback((value: EnvironmentNoteDeletion) => {
    if (value.state !== 'confirmed') throw new Error('The original deletion is not confirmed.');
    localStorage.removeItem(storageKey); setPending(null); setConfirm(null); observe(value); refresh();
    setMessage(`${value.deleted} ${value.deleted === 1 ? 'note' : 'notes'} deleted.`);
  }, [storageKey, observe, refresh]);
  const check = useCallback(async (original: Pending, signal?: AbortSignal) => {
    try {
      const value = await request<EnvironmentNoteDeletion>(notes.path + '/requests/' + original.requestId, '', 'GET', undefined, signal);
      if (!signal?.aborted) finish(value);
    } catch (error) {
      if (signal?.aborted) return;
      setMessage((error as { status?: number }).status === 404 ? 'The original request has no confirmed receipt. Retry the same request or check again.' : 'Original deletion status unavailable. Existing notes were preserved.');
      if ((error as { status?: number }).status === 403) await reauth().catch(() => undefined);
    }
  }, [request, notes.path, finish, reauth]);
  useEffect(() => {
    if (!pending || busy) return;
    const controller = new AbortController(); const initial = window.setTimeout(() => void check(pending, controller.signal), 0);
    const timer = window.setInterval(() => { if (!document.hidden) void check(pending, controller.signal); }, 4000);
    return () => { controller.abort(); window.clearTimeout(initial); window.clearInterval(timer); };
  }, [pending, busy, check]);
  useEffect(() => {
    const element = dialog.current!, opener = document.activeElement; element.showModal(); closeButton.current?.focus();
    return () => { element.close(); if (opener instanceof HTMLElement && opener.isConnected) opener.focus(); };
  }, []);
  async function submit(original: Pending) {
    if (busy) return;
    try { localStorage.setItem(storageKey, JSON.stringify(original)); }
    catch { setMessage('The deletion request could not be preserved in this browser. No deletion was sent.'); return; }
    setPending(original); setBusy(true); setMessage('');
    const controller = new AbortController(), timer = window.setTimeout(() => controller.abort(), 15000);
    try {
      const value = await request<EnvironmentNoteDeletion>(notes.path + (original.noteId ? '/' + original.noteId : '/delete-all'), token, original.noteId ? 'DELETE' : 'POST', original.body, controller.signal);
      finish(value);
    } catch (error) {
      const status = (error as { status?: number }).status;
      if (status && status >= 400 && status < 500 && status !== 403) {
        localStorage.removeItem(storageKey); setPending(null); setConfirm(null); refresh();
        setMessage('The notes changed or this request was rejected. Review the refreshed list and confirm a new deletion.');
      } else {
        setMessage('Deletion response unavailable. Checking the original request; no second deletion was submitted.');
        if (status === 403) await reauth().catch(() => undefined);
      }
    } finally { window.clearTimeout(timer); setBusy(false); }
  }
  function remove(note: EnvironmentNote) {
    if (!notes.page || !notes.current || pending || busy) return;
    const requestId = projectRequestId(); void submit({ requestId, noteId: note.id, body: { requestId, collectionRevision: notes.page.revision, revision: note.revision } });
  }
  const changed = !!confirm && (!notes.page || notes.page.revision !== confirm.revision || session.name !== confirm.name);
  const canDelete = notes.current && !pending && !busy;
  return createPortal(<dialog ref={dialog} className="project-dialog environment-notes-dialog" aria-labelledby="environment-notes-title" onCancel={event => { event.preventDefault(); close(); }}>
    <header className="project-dialog-header"><h2 id="environment-notes-title">Environment notes</h2><button ref={closeButton} type="button" className="project-close" aria-label="Close" onClick={close}>×</button></header>
    <div className="environment-notes-content">
      <p>Studio environment observations for <strong>{session.name}</strong> · {notes.count} {notes.count === 1 ? 'note' : 'notes'}</p>
      {!session.environmentNotesAccess?.available ? <p className="environment-notes-help">{session.environmentNotesAccess?.reason ?? 'New session required for agent note tools.'} Existing notes remain available here.</p> : session.environmentNotesEnabled === false && <p className="environment-notes-help">Agent note tools are off. You can still view and delete notes.</p>}
      <form className="environment-notes-filters" onSubmit={event => { event.preventDefault(); notes.setQuery(Object.fromEntries(Object.entries(filter).filter(([, value]) => value))); }}>
        <label>Search<input aria-label="Search notes" maxLength={160} value={filter.query} onChange={event => setFilter(old => ({ ...old, query: event.target.value }))} /></label>
        <label>Type<select value={filter.kind} onChange={event => setFilter(old => ({ ...old, kind: event.target.value }))}><option value="">All types</option><option value="problem">Problem</option><option value="suggestion">Suggestion</option></select></label>
        <label>Category<select value={filter.category} onChange={event => setFilter(old => ({ ...old, category: event.target.value }))}><option value="">All categories</option>{['tools', 'capabilities', 'workflow', 'interface', 'documentation'].map(value => <option key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</option>)}</select></label>
        <button type="submit">Apply filter</button>
      </form>
      {notes.error && <p role="alert" className="project-dialog-error">{navigator.onLine ? 'Notes unavailable: ' : 'Offline: '}{notes.error}</p>}
      {!notes.page && !notes.error && <p role="status">Loading notes…</p>}
      {notes.page && !notes.current && !notes.error && <p role="status">Refreshing the changed collection…</p>}
      {notes.page && !notes.page.entries.length && <p>{notes.count ? 'No notes match this filter.' : 'No environment notes.'}</p>}
      <div className="environment-notes-list">{notes.page?.entries.map(note => <article key={note.id} className="environment-note">
        <div className="environment-note-meta"><span>{note.kind === 'problem' ? 'Problem' : 'Suggestion'} · {note.category}</span><time dateTime={note.createdAt}>{new Date(note.createdAt).toLocaleString('en-GB')}</time></div>
        <h3>{note.title}</h3><p>{note.description}</p>
        {(['impact', 'workaround', 'suggestion'] as const).map(field => note[field] && <div key={field} className="environment-note-detail"><strong>{field[0].toUpperCase() + field.slice(1)}</strong><p>{note[field]}</p></div>)}
        <button type="button" disabled={!canDelete} aria-label={'Delete note: ' + note.title} onClick={() => remove(note)}>Delete</button>
      </article>)}</div>
      {notes.page && (notes.query.before || notes.page.nextBefore) && <nav className="environment-notes-pages" aria-label="Note pages"><button type="button" disabled={!notes.query.before} onClick={() => { const next = { ...notes.query }; delete next.before; notes.setQuery(next); }}>First page</button><button type="button" disabled={!notes.page.nextBefore} onClick={() => notes.setQuery({ ...notes.query, before: notes.page!.nextBefore! })}>Next page</button></nav>}
      {message && <p role="status">{message}</p>}
      {pending && <div className="environment-notes-pending"><p>Original deletion is awaiting confirmation.</p><button type="button" disabled={busy} onClick={() => void check(pending)}>Check original request</button><button type="button" disabled={busy} onClick={() => void submit(pending)}>Retry same request</button></div>}
      {confirm && <div className="environment-notes-confirm" role="group" aria-label="Confirm delete all notes"><p>Delete all <strong>{confirm.count}</strong> notes from <strong>{confirm.name}</strong>?</p>{changed && <p role="alert">The notes changed. Review the current list and confirm again.</p>}<button type="button" disabled={!canDelete || changed} onClick={() => { const requestId = projectRequestId(); void submit({ requestId, body: { requestId, collectionRevision: confirm.revision, confirmName: confirm.name, count: confirm.count } }); }}>Confirm delete all</button><button type="button" disabled={busy} onClick={() => setConfirm(null)}>Cancel</button></div>}
      <p className="environment-notes-help">Deletion removes active notes. Earlier conversation/tool history and separate backups are unchanged.</p>
    </div>
    <footer className="project-actions">{busyRun(run?.state) && <button type="button" disabled={run?.state === 'stopping'} onClick={() => void stop()}>Stop current run</button>}<button type="button" disabled={!canDelete || !notes.count} onClick={() => setConfirm({ revision: notes.page!.revision, count: notes.count, name: session.name })}>Delete all</button><button type="button" onClick={refresh}>Refresh</button><button type="button" onClick={close}>Close</button></footer>
  </dialog>, document.body);
}
