import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { AgentSession, SessionCreate, SessionOptions } from '../../../../shared/agent-sessions';
import { ProjectField } from '../projects/ProjectField';
import { projectRequest, projectRequestId, ProjectRequestError, sessionPath } from './api';

export function NewSessionDialog({ projectId, token, close, created }: { projectId: string; token: string; close: () => void; created: (session: AgentSession) => void }) {
  const key = 'studio.session.create.' + projectId;
  const [pending, setPending] = useState<SessionCreate | null>(() => { try { return JSON.parse(sessionStorage.getItem(key) ?? 'null'); } catch { return null; } });
  const [name, setName] = useState(pending?.name ?? ''), [providerId, setProvider] = useState(pending?.providerId ?? '');
  const [model, setModel] = useState(pending?.model ?? ''), [effort, setEffort] = useState(pending?.effort ?? '');
  const [options, setOptions] = useState<SessionOptions | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = dialog.current!, opener = document.activeElement; el.showModal();
    el.querySelector<HTMLInputElement>('input')?.focus();
    return () => { el.close(); if (opener instanceof HTMLElement && opener.isConnected) opener.focus(); };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void projectRequest<SessionOptions>(sessionPath(projectId) + '/options', '', 'GET', undefined, controller.signal).then((r) => {
      if (controller.signal.aborted) return;
      setOptions(r);
      if (!pending) {
        const provider = r.providers.find((p) => p.models.length), chosen = provider?.models[0];
        setProvider(provider?.id ?? ''); setModel(chosen?.id ?? ''); setEffort(chosen?.defaultEffort ?? '');
      }
    }).catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [projectId, pending]);
  const provider = options?.providers.find((p) => p.id === providerId), chosen = provider?.models.find((m) => m.id === model);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    const data = pending ?? { requestId: projectRequestId(), name: name.trim(), providerId, model, effort };
    try { sessionStorage.setItem(key, JSON.stringify(data)); } catch { setError('Enable session storage before creating a session.'); return; }
    setPending(data); setBusy(true); setError('');
    try {
      const r = await projectRequest<{ session: AgentSession }>(sessionPath(projectId), token, 'POST', data);
      sessionStorage.removeItem(key); created(r.session);
    } catch (e) {
      const error = e as ProjectRequestError;
      if (error.status && error.status < 500) { sessionStorage.removeItem(key); setPending(null); }
      setError(error.message);
    } finally { setBusy(false); }
  }
  return <dialog className="project-dialog" ref={dialog} aria-labelledby="new-session-title" onCancel={(e) => { e.preventDefault(); if (!busy) close(); }}>
    <form onSubmit={(e) => void submit(e)}>
      <header className="project-dialog-header"><h2 id="new-session-title">New Session</h2><button type="button" className="project-close" aria-label="Close" disabled={busy} onClick={close}>×</button></header>
      <fieldset className="project-fields" disabled={busy || !!pending}>
        <ProjectField id="session-name" label="Name"><input id="session-name" required autoComplete="off" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></ProjectField>
        <ProjectField id="session-provider" label="Provider"><select id="session-provider" required value={providerId} onChange={(e) => {
          const p = options?.providers.find((p) => p.id === e.target.value), m = p?.models[0]; setProvider(e.target.value); setModel(m?.id ?? ''); setEffort(m?.defaultEffort ?? '');
        }}><option value="" disabled>Select provider</option>{options?.providers.map((p) => <option key={p.id} value={p.id} disabled={!p.models.length}>{p.name}</option>)}</select></ProjectField>
        <div className="project-form-row">
          <ProjectField id="session-model" label="Model"><select id="session-model" required value={model} onChange={(e) => { setModel(e.target.value); setEffort(provider?.models.find((m) => m.id === e.target.value)?.defaultEffort ?? ''); }}>
            <option value="" disabled>Select model</option>{provider?.models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></ProjectField>
          <ProjectField id="session-effort" label="Reasoning"><select id="session-effort" required value={effort} onChange={(e) => setEffort(e.target.value)}><option value="" disabled>Select effort</option>{chosen?.efforts.map((v) => <option key={v} value={v}>{v}</option>)}</select></ProjectField>
        </div>
      </fieldset>
      {!options && !error && <p className="project-dialog-status" role="status">Loading…</p>}
      {options && !options.engine.available && <p className="project-dialog-error" role="alert">{options.engine.reason}</p>}
      {options && !options.providers.some((p) => p.models.length) && <p className="project-dialog-error">Connect a provider in System settings.</p>}
      {error && <p className="project-dialog-error" role="alert">{error}</p>}
      <footer className="project-actions"><button type="button" disabled={busy} onClick={close}>Cancel</button><button className="project-primary" disabled={busy || (!pending && (!options?.engine.available || !chosen))}>{busy ? 'Creating…' : pending ? 'Retry create' : 'Create session'}</button></footer>
    </form>
  </dialog>;
}
