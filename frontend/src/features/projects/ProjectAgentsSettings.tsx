import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type { ProjectAgents } from '../../../../shared/projects';
import { projectRequest, ProjectRequestError } from './api';

export function ProjectAgentsSettings({ id, token, dirtyChanged, busyChanged }: {
  id: string; token: string; dirtyChanged: (value: boolean) => void; busyChanged: (value: boolean) => void;
}) {
  const [saved, setSaved] = useState<ProjectAgents | null>(null), [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false), [editable, setEditable] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [conflict, setConflict] = useState(false), [epoch, setEpoch] = useState(0);
  const dirty = saved !== null && draft !== saved.text;
  useEffect(() => { dirtyChanged(dirty); return () => dirtyChanged(false); }, [dirty, dirtyChanged]);
  useEffect(() => { busyChanged(busy); return () => busyChanged(false); }, [busy, busyChanged]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty || busy) event.preventDefault(); };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [dirty, busy]);
  useEffect(() => {
    const controller = new AbortController();
    void projectRequest<ProjectAgents>(`/${id}/agents`, '', 'GET', undefined, controller.signal).then((value) => {
      if (controller.signal.aborted) return;
      setSaved(value); setDraft(value.text); setEditable(value.editable); setError(''); setNotice(''); setConflict(false);
    }).catch((cause: Error) => { if (!controller.signal.aborted) setError(cause.message); });
    return () => controller.abort();
  }, [id, epoch]);
  useEffect(() => {
    if (busy) return;
    const controller = new AbortController(); let pending = false;
    const timer = window.setInterval(() => {
      if (document.hidden || pending) return;
      pending = true;
      void projectRequest<ProjectAgents>(`/${id}/agents`, '', 'GET', undefined, controller.signal)
        .then((value) => { if (!controller.signal.aborted) setEditable(value.editable); })
        .catch(() => { if (!controller.signal.aborted) setEditable(false); }).finally(() => { pending = false; });
    }, 5000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [id, busy]);
  async function save(event: FormEvent) {
    event.preventDefault(); if (!saved || busy || !editable || conflict) return;
    if (new TextEncoder().encode(draft).byteLength > 32768) { setError('Enter at most 32 KiB of UTF-8 text.'); return; }
    setBusy(true); setError(''); setNotice('');
    try {
      const value = await projectRequest<ProjectAgents>(`/${id}/agents`, token, 'PATCH', { text: draft, sha256: saved.sha256 });
      setSaved(value); setDraft(value.text); setEditable(value.editable); setNotice('Saved.');
    } catch (cause) { setError((cause as Error).message); setConflict((cause as ProjectRequestError).status === 409); }
    finally { setBusy(false); }
  }
  return <form className="project-settings" aria-label="Agents.md settings" onSubmit={(event) => void save(event)}>
    <h2>Agents.md</h2>
    {!saved && !error && <p role="status">Loading Agents.md…</p>}
    {saved && <textarea className="project-agents-editor" aria-label="Project instructions" spellCheck={false}
      maxLength={32768} disabled={busy} value={draft} onChange={(event) => { setDraft(event.target.value); setNotice(''); }} />}
    {saved && !editable && <p className="project-message" role="status">Wait for active runs and development jobs to finish before saving.</p>}
    {error && <p className="project-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {(error || conflict) && <button type="button" disabled={busy} onClick={() => {
      if (!dirty || window.confirm('Reload Agents.md and discard unsaved changes?')) setEpoch((value) => value + 1);
    }}>Reload file</button>}
    <div className="project-actions">
      <button type="button" disabled={busy || !dirty} onClick={() => { if (saved) setDraft(saved.text); setNotice(''); }}>Cancel</button>
      <button type="submit" className="project-primary" disabled={busy || !saved || !editable || conflict || (!dirty && saved.exists)}>{busy ? 'Saving…' : 'Save changes'}</button>
    </div>
  </form>;
}
