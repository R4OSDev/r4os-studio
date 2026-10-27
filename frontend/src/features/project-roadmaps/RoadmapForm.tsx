import { useEffect, useId, useState } from 'react';
import type { FormEvent } from 'react';
import type { RoadmapBinding, RoadmapMutation, RoadmapMutationResult, RoadmapTarget } from '../../../../shared/project-roadmaps';
import { ProjectRequestError, projectRequestId } from '../projects/api';
import { mutate } from './api';

type Input = NonNullable<RoadmapMutation['input']>;
function savedRequest(key: string, target: RoadmapTarget, action: string): RoadmapMutation | null {
  const saved = sessionStorage.getItem(key);
  if (!saved) return null;
  const value = JSON.parse(saved) as RoadmapMutation;
  if (value.action !== action || JSON.stringify(value.target) !== JSON.stringify(target)
    || typeof value.requestId !== 'string' || !Number.isSafeInteger(value.expectedRevision)
    || typeof value.currentVersionId !== 'string' || !value.input || typeof value.input !== 'object') {
    throw new Error('This browser has an unrecognized roadmap request. Its data was preserved.');
  }
  return value;
}

export function RoadmapForm({ id, token, binding, target, initial, create = false, saved, cancel, dirtyChanged, busyChanged }: {
  id: string; token: string; binding: RoadmapBinding; target: RoadmapTarget; initial: Input; create?: boolean;
  saved: (result: RoadmapMutationResult) => void; cancel: () => void;
  dirtyChanged: (value: boolean) => void; busyChanged: (value: boolean) => void;
}) {
  const key = `studio.roadmap.request.${id}.${target.kind}.${target.id ?? 'new'}`;
  const formId = useId();
  const action = create ? 'create' : 'update';
  const [recovery] = useState(() => {
    try { return { request: savedRequest(key, target, action), error: '' }; }
    catch (cause) { return { request: null, error: (cause as Error).message }; }
  });
  const [pending, setPending] = useState(recovery.request);
  const [draft, setDraft] = useState<Input>(recovery.request?.input ?? initial);
  const [base] = useState(binding);
  const [busy, setBusy] = useState(false), [error, setError] = useState(recovery.error), [conflict, setConflict] = useState(false);
  const dirty = !!pending || JSON.stringify(draft) !== JSON.stringify(initial);
  useEffect(() => { dirtyChanged(dirty); return () => dirtyChanged(false); }, [dirty, dirtyChanged]);
  useEffect(() => { busyChanged(busy); return () => busyChanged(false); }, [busy, busyChanged]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty || busy) event.preventDefault(); };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [dirty, busy]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || conflict || recovery.error) return;
    const input = { ...draft };
    if (create && !input.number) delete input.number;
    for (const [field, value] of Object.entries(input)) {
      if (typeof value === 'string' && new TextEncoder().encode(value).byteLength > (field === 'title' ? 240 : 32768)) {
        setError('Enter at most 240 UTF-8 bytes for a title and 32 KiB for each text field.'); return;
      }
    }
    const body: RoadmapMutation = pending ?? { requestId: projectRequestId(), expectedRevision: base.revision,
      currentVersionId: base.currentVersionId, action, target, input };
    try { sessionStorage.setItem(key, JSON.stringify(body)); }
    catch { setError('The browser could not retain this request. Enable session storage before saving.'); return; }
    setPending(body); setBusy(true); setError('');
    try {
      const result = await mutate(id, token, body);
      sessionStorage.removeItem(key); setPending(null); saved(result);
    } catch (cause) {
      const failure = cause as ProjectRequestError;
      if (failure.status >= 400 && failure.status < 500) {
        sessionStorage.removeItem(key); setPending(null); setConflict(failure.status === 409);
      }
      setError(failure.message || 'The result could not be confirmed. Retry the original request.');
    } finally { setBusy(false); }
  }
  const field = (name: 'number' | 'title' | 'description' | 'vision' | 'notes', label: string, multiline = false) => <div className="project-field" key={name}>
    <label htmlFor={formId + '-' + name}>{label}</label>{multiline ? <textarea id={formId + '-' + name} rows={name === 'notes' ? 6 : 4} maxLength={32768}
      value={String(draft[name] ?? '')} onChange={(event) => setDraft({ ...draft, [name]: event.target.value })} />
      : <input id={formId + '-' + name} required={name === 'title' || (name === 'number' && !create)} maxLength={name === 'title' ? 240 : 35}
        placeholder={name === 'number' && create ? 'Next version, or enter e.g. 0.2.X' : undefined}
        value={String(draft[name] ?? '')} onChange={(event) => setDraft({ ...draft, [name]: event.target.value })} />}</div>;
  return <form className="roadmap-form" aria-label={create ? 'New roadmap version' : target.kind === 'roadmap' ? 'Roadmap overview settings' : 'Main version settings'} onSubmit={(event) => void submit(event)}>
    <fieldset className="project-fields" disabled={busy || !!pending || !!recovery.error}>
      {target.kind === 'roadmap' ? field('description', 'Roadmap description', true) : <>
        {field('number', create ? 'Version number (optional)' : 'Version number')}
        {field('title', 'Title')}
        <div className="project-field"><label htmlFor={formId + '-status'}>Status</label><select id={formId + '-status'} value={draft.status ?? 'open'} onChange={(event) => setDraft({ ...draft, status: event.target.value as 'open' | 'complete' | 'discarded' })}>
          <option value="open">Open</option><option value="complete">Complete</option><option value="discarded">Discarded</option>
        </select></div>
        {field('vision', 'Vision', true)}
      </>}
      {field('notes', target.kind === 'roadmap' ? 'Roadmap notes' : 'Version notes', true)}
    </fieldset>
    {error && <p className="project-error" role="alert">{error}</p>}
    {pending && !busy && <p className="project-message" role="status">An original request needs confirmation. Retry it before editing this entry.</p>}
    {conflict && <p className="project-message" role="status">Your input is retained. Refresh the roadmap when you are ready to discard it and load the current version.</p>}
    <div className="project-actions">
      <button type="button" disabled={busy || !!pending} onClick={cancel}>Cancel</button>
      <button type="submit" className="project-primary" disabled={busy || conflict || !!recovery.error || (!dirty && !create)}>
        {busy ? 'Saving…' : pending ? 'Retry original request' : create ? 'Create version' : 'Save changes'}
      </button>
    </div>
  </form>;
}
