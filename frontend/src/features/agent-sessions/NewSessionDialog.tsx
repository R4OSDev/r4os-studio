import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { AgentSession, SessionCreate, SessionOptions } from '../../../../shared/agent-sessions';
import { availableModels, effortLabel, providerLabel } from './modelChoices';
import { ProjectField } from '../projects/ProjectField';
import { useSessionApi, projectRequestId, ProjectRequestError, sessionPath } from './api';

export function NewSessionDialog({ projectId, token, close, created, dirtyChanged, busyChanged }: { projectId: string; token: string; close: () => void; created: (session: AgentSession) => void; dirtyChanged?: (value: boolean) => void; busyChanged?: (value: boolean) => void }) {
  const { request: projectRequest, scope } = useSessionApi();
  const key = (scope === 'skill' ? 'studio.skill.session.create.' : 'studio.session.create.') + projectId;
  const [pending, setPending] = useState<SessionCreate | null>(() => { try { return JSON.parse(sessionStorage.getItem(key) ?? 'null'); } catch { return null; } });
  const [name, setName] = useState(pending?.name ?? ''), [providerId, setProvider] = useState(pending?.providerId ?? '');
  const [model, setModel] = useState(pending?.model ?? ''), [effort, setEffort] = useState(pending?.effort ?? '');
  const [fastMode, setFast] = useState(pending?.fastMode ?? false);
  const [options, setOptions] = useState<SessionOptions | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dirtyChanged?.(!!name || !!pending); return () => dirtyChanged?.(false); }, [name, pending, dirtyChanged]);
  useEffect(() => { busyChanged?.(busy); return () => busyChanged?.(false); }, [busy, busyChanged]);
  const requestClose = () => { if (!busy && (!name || window.confirm('Discard the new session form?'))) close(); };
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
        const provider = r.providers.find((p) => availableModels(p).length), chosen = availableModels(provider)[0];
        setProvider(provider?.id ?? ''); setModel(chosen?.id ?? ''); setEffort(chosen?.defaultEffort ?? '');
      }
    }).catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [projectId, pending, projectRequest]);
  const provider = options?.providers.find((p) => p.id === providerId), chosen = provider?.models.find((m) => m.id === model);
  const selectedEngine = provider?.engine ?? options?.engine;
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    const data = pending ?? { requestId: projectRequestId(), name: name.trim(), providerId, model, effort, fastMode };
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
  return <dialog className="project-dialog" ref={dialog} aria-labelledby="new-session-title" onCancel={(e) => { e.preventDefault(); requestClose(); }}>
    <form onSubmit={(e) => void submit(e)}>
      <header className="project-dialog-header"><h2 id="new-session-title">New Session</h2><button type="button" className="project-close" aria-label="Close" disabled={busy} onClick={requestClose}>×</button></header>
      <fieldset className="project-fields" disabled={busy || !!pending}>
        <ProjectField id="session-name" label="Name"><input id="session-name" required autoComplete="off" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></ProjectField>
        <ProjectField id="session-provider" label="Provider"><select id="session-provider" required value={providerId} onChange={(e) => {
          const p = options?.providers.find((p) => p.id === e.target.value), m = availableModels(p)[0]; setProvider(e.target.value); setModel(m?.id ?? ''); setEffort(m?.defaultEffort ?? ''); setFast(false);
        }}><option value="" disabled>Select provider</option>{options?.providers.map((p) => <option key={p.id} value={p.id} disabled={!availableModels(p).length}>{providerLabel(p)}</option>)}</select></ProjectField>
        <div className="project-form-row">
          <ProjectField id="session-model" label="Model"><select id="session-model" required value={model} onChange={(e) => { const next = provider?.models.find((m) => m.id === e.target.value); setModel(e.target.value); setEffort(next?.defaultEffort ?? ''); setFast((fast) => fast && !!next?.fastModeAvailable); }}>
            <option value="" disabled>Select model</option>{provider?.models.map((m) => <option key={m.id} value={m.id} disabled={m.available === false}>{m.name}{m.available === false ? ' · unavailable' : ''}</option>)}</select></ProjectField>
          <ProjectField id="session-effort" label="Reasoning"><select id="session-effort" required={!chosen?.efforts.includes('')} value={effort} onChange={(e) => setEffort(e.target.value)}>{!chosen?.efforts.includes('') && <option value="" disabled>Select effort</option>}{chosen?.efforts.map((v) => <option key={v} value={v}>{effortLabel(v, provider)}</option>)}</select></ProjectField>
        </div>
        <ProjectField id="session-fast-mode" label="Fast Mode"><select id="session-fast-mode" value={fastMode ? 'on' : 'off'} onChange={(e) => setFast(e.target.value === 'on')}><option value="off">Off</option><option value="on" disabled={!chosen?.fastModeAvailable}>On</option></select></ProjectField>
      </fieldset>
      {!options && !error && <p className="project-dialog-status" role="status">Loading…</p>}
      {provider?.type === 'claude-subscription' && <p className="field-help">Claude subscription · Text, documents and Studio tools. {chosen?.imageInputs === 'supported' ? 'PNG/JPEG/WebP images are qualified for this model (4 MiB each, 8 MiB per send).' : 'Image input is not qualified for this model.'} Each send checks the native account and included usage. Fast Mode is unavailable.</p>}
      {selectedEngine && !selectedEngine.available && <p className="project-dialog-error" role="alert">{selectedEngine.reason}</p>}
      {options && !options.providers.some((p) => availableModels(p).length) && <p className="project-dialog-error">Connect a provider and configure an available model in System settings.</p>}
      {error && <p className="project-dialog-error" role="alert">{error}</p>}
      <footer className="project-actions"><button type="button" disabled={busy} onClick={requestClose}>Cancel</button><button className="project-primary" disabled={busy || (!pending && (!selectedEngine?.available || !chosen || chosen.available === false))}>{busy ? 'Creating…' : pending ? 'Retry create' : 'Create session'}</button></footer>
    </form>
  </dialog>;
}
