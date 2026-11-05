import { useEditorSnapshot } from '../project-editor/useEditorProject';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ProjectPinChoice, ProjectPinOptions, ProjectPinReceipt, ProjectPins, ProjectPinUpdate } from '../../../../shared/projects';
import { projectRequest, projectRequestId, ProjectRequestError } from './api';
import { editorRegistry } from '../project-editor/registry';
import './pins.css';

const storageKey = (id: string) => 'studio.project.pins.' + id;
function remembered(id: string): ProjectPinUpdate | null {
  try {
    const raw = sessionStorage.getItem(storageKey(id));
    if (!raw || raw.length > 4096) return null;
    const value = JSON.parse(raw) as ProjectPinUpdate;
    if (/^[a-f0-9-]{36}$/.test(value.requestId) && Number.isSafeInteger(value.revision)
      && /^[a-f0-9]{40}$/.test(value.sdkId) && /^[a-f0-9]{64}$/.test(value.selectionId)) return value;
  } catch { /* The host keeps authoritative original receipts. */ }
  return null;
}

type Components = NonNullable<ProjectPinChoice['components']> | ProjectPins;
function PinList({ pins }: { pins: Components }) {
  return <dl className="project-pin-list">
    <div><dt>SDK</dt><dd>{pins.sdk.version}</dd></div>
    <div><dt>Contract</dt><dd>{pins.contract.version}</dd></div>
    {pins.libraries && <div><dt>Libraries</dt><dd>{pins.libraries.version}</dd></div>}
    <div><dt>Zig</dt><dd>{pins.zig.version}</dd></div>
    {pins.rust && <div><dt>Rust</dt><dd>{pins.rust.version}<small>{pins.rust.id}</small></dd></div>}
  </dl>;
}
function PinDetails({ pins }: { pins: ProjectPins }) {
  return <details className="project-pin-details"><summary>Revisions &amp; checksums</summary>
    {Object.entries(pins).map(([name, value]) => <section key={name}>
      <h4>{name === 'sdkTools' ? 'SDK tools' : name === 'sdk' ? 'SDK' : name[0].toUpperCase() + name.slice(1)}</h4>
      <dl>{Object.entries(value).map(([key, field]) => <div key={key}><dt>{key}</dt><dd>{typeof field === 'object'
        ? Object.entries(field as Record<string, string>).map(([k, v]) => <span key={k}>{k}: {v}</span>) : String(field)}</dd></div>)}</dl>
    </section>)}
  </details>;
}

export function ProjectPinsSettings({ id, token, dirtyChanged, busyChanged }: {
  id: string; token: string; dirtyChanged: (value: boolean) => void; busyChanged: (value: boolean) => void;
}) {
  const [options, setOptions] = useState<ProjectPinOptions | null>(null);
  const [selected, setSelected] = useState(''), [pending, setPending] = useState<ProjectPinUpdate | null>(() => remembered(id));
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const working = useRef(false);
  useEditorSnapshot(id);
  const editorBusy = editorRegistry.hasUnsavedFor(id);
  const target = options?.choices.find(choice => choice.sdkId === selected);
  const changed = !!options && !!target?.components && (selected !== options.project.pins.sdk.revision
    || target.components.contract.revision !== options.project.pins.contract.revision
    || target.components.zig.version !== options.project.pins.zig.version
    || target.components.rust?.id !== options.project.pins.rust?.id);
  const dirty = changed || !!pending;
  useEffect(() => { dirtyChanged(dirty); return () => dirtyChanged(false); }, [dirty, dirtyChanged]);
  useEffect(() => { busyChanged(busy); return () => busyChanged(false); }, [busy, busyChanged]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty || busy) event.preventDefault(); };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [dirty, busy]);

  const load = useCallback(async (signal?: AbortSignal) => {
    const value = await projectRequest<ProjectPinOptions>(`/${id}/pins`, '', 'GET', undefined, signal);
    const saved = remembered(id), requestId = value.pendingRequestId ?? saved?.requestId;
    let original = saved;
    if (requestId) {
      const receipt = await projectRequest<ProjectPinReceipt>(`/${id}/pins/requests/${requestId}`, '', 'GET', undefined, signal);
      if (receipt.requestId !== requestId) throw new Error('The original pin-change receipt could not be confirmed.');
      if (receipt.state === 'complete' && !value.pendingRequestId) {
        original = null;
        try { sessionStorage.removeItem(storageKey(id)); } catch { /* Original host receipt remains idempotent. */ }
        if (!signal?.aborted) { setNotice('Pins updated. Build the project to check source compatibility.'); editorRegistry.pinsChanged(id); }
      } else original = receipt.input ?? saved;
      if (!original && receipt.state !== 'complete') throw new Error('The original pin change needs recovery. Its request could not be loaded.');
    }
    if (!signal?.aborted) {
      setOptions(value); setSelected(original?.sdkId ?? value.project.pins.sdk.revision); setPending(original); setError('');
    }
    return value;
  }, [id]);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(() => load(controller.signal)).catch(cause => { if (!controller.signal.aborted) setError((cause as Error).message); });
    return () => controller.abort();
  }, [load]);

  function retain(input: ProjectPinUpdate) {
    sessionStorage.setItem(storageKey(id), JSON.stringify(input)); setPending(input);
  }
  async function reload() {
    if (working.current) return;
    working.current = true; setBusy(true);
    try { await load(); } catch (cause) { setError((cause as Error).message); }
    finally { working.current = false; setBusy(false); }
  }
  async function apply() {
    if (working.current || editorBusy || !options || !token || (!pending && (!changed || !target?.available || !options.available))) return;
    const input = pending ?? { requestId: projectRequestId(), revision: options.project.revision, sdkId: selected, selectionId: target!.selectionId! };
    try { retain(input); } catch { setError('The pin change could not be retained. Enable browser session storage before applying.'); return; }
    working.current = true; setBusy(true); setError(''); setNotice('');
    try {
      const receipt = await projectRequest<ProjectPinReceipt>(`/${id}/pins`, token, 'POST', input);
      if (receipt.requestId !== input.requestId || receipt.state !== 'complete') throw new Error('The pin change is unconfirmed. Check its status or retry the original change.');
      try { sessionStorage.removeItem(storageKey(id)); } catch { /* Completed original request is harmless on retry. */ }
      setPending(null); editorRegistry.pinsChanged(id);
      setNotice('Pins updated. Build the project to check source compatibility.');
      setOptions(null);
      await load();
    } catch (cause) {
      // A definite rejection plus a missing journal proves no publication began.
      if (cause instanceof ProjectRequestError && cause.status >= 400 && cause.status < 500) {
        try {
          const receipt = await projectRequest<ProjectPinReceipt>(`/${id}/pins/requests/${input.requestId}`);
          if (receipt.requestId === input.requestId && receipt.state === 'missing') {
            sessionStorage.removeItem(storageKey(id)); setPending(null);
          }
        } catch { /* Lost responses retain the original request. */ }
      }
      setError((cause as Error).message);
    } finally { working.current = false; setBusy(false); }
  }

  return <section className="project-settings project-pins-settings" aria-label="Project Pins settings" aria-busy={busy}>
    <div className="project-pins-heading"><h2>Pins</h2><button type="button" className="project-reload" disabled={busy}
      onClick={() => { if (!changed || pending || window.confirm('Discard the selected SDK and reload Pins?')) void reload(); }}>Refresh</button></div>
    <p className="project-message">Choose a complete installed SDK package. Its profiles determine tools, Contract and system libraries.</p>
    {!options && !error && <p className="project-message" role="status">Loading project pins…</p>}
    {options && <div className="project-pins-columns">
      <section className="project-pin-card" aria-label="Current project pins"><h3>Current pins</h3><PinList pins={options.project.pins} /><PinDetails pins={options.project.pins} /></section>
      <section className="project-pin-card" aria-label="Selected project pins"><h3>SDK selection</h3>
        <label className="project-field" htmlFor="project-pin-sdk">Installed SDK<select id="project-pin-sdk" value={selected} disabled={busy || !!pending}
          onChange={event => { setSelected(event.target.value); setNotice(''); }}>
          {!options.choices.some(choice => choice.sdkId === options.project.pins.sdk.revision) && <option value={options.project.pins.sdk.revision}>Current SDK {options.project.pins.sdk.version}</option>}
          {options.choices.map(choice => <option key={choice.sdkId} value={choice.sdkId} disabled={!choice.available}>
            {choice.version ?? choice.sdkId.slice(0, 12)}{choice.isDefault ? ' · System default' : ''}{choice.available ? '' : ' · Unavailable'}</option>)}
        </select></label>
        {target?.components && <PinList pins={target.components} />}
        {target && !target.available && <p className="project-message">{target.reason}</p>}
        <p className="project-message">Applies only to this project. Build afterwards to check source compatibility.</p>
        {options.choices.some(choice => !choice.available) && <details className="project-pin-details"><summary>Unavailable SDKs</summary>
          {options.choices.filter(choice => !choice.available).map(choice => <p key={choice.sdkId}><strong>{choice.version ?? choice.sdkId.slice(0, 12)}</strong> — {choice.reason}</p>)}
        </details>}
      </section>
    </div>}
    {options && !options.available && <p className="project-message" role="status">Wait for active agent runs and development jobs to finish, then refresh.</p>}
    {editorBusy && <p className="project-message" role="status">Save or close this project’s editor drafts and finish pending file operations before changing pins.</p>}
    {pending && <p className="project-message" role="status">A pin change needs confirmation. Check its status or retry the original change.</p>}
    {error && <p className="project-error" role="alert">{error}</p>}
    {notice && <p className="project-message" role="status">{notice}</p>}
    <div className="project-actions">
      {pending ? <button type="button" disabled={busy} onClick={() => void reload()}>Check status</button>
        : <button type="button" disabled={busy || !changed} onClick={() => { setSelected(options?.project.pins.sdk.revision ?? ''); setNotice(''); setError(''); }}>Cancel</button>}
      <button type="button" className="project-primary" disabled={busy || editorBusy || !token || !options || (!pending && (!changed || !target?.available || !options.available))}
        onClick={() => void apply()}>{busy ? 'Checking pins…' : pending ? 'Retry original change' : 'Apply pins'}</button>
    </div>
  </section>;
}
