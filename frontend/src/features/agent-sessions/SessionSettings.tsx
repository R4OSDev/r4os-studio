import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { AgentSession, AgentToolId, SessionOptions } from '../../../../shared/agent-sessions';
import { ProjectField } from '../projects/ProjectField';
import { projectRequest, sessionPath, busyRun, toolLabels } from './api';

const tools = Object.keys(toolLabels) as AgentToolId[];
export function SessionSettings({ session, token, projectId, close, saved }: {
  session: AgentSession; token: string; projectId: string; close: () => void; saved: (session: AgentSession) => void;
}) {
  const [draft, setDraft] = useState(session), [options, setOptions] = useState<SessionOptions | null>(null);
  const [error, setError] = useState(''), [saving, setSaving] = useState(false), [reloading, setReloading] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null), [tab, setTab] = useState<'General' | 'Tools'>('General');
  useEffect(() => {
    const element = dialog.current!, opener = document.activeElement; element.showModal();
    return () => { element.close(); if (opener instanceof HTMLElement && opener.isConnected) opener.focus(); };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void projectRequest<SessionOptions>(sessionPath(projectId) + '/options', '', 'GET', undefined, controller.signal)
      .then((r) => { if (!controller.signal.aborted) setOptions(r); })
      .catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [projectId]);
  const provider = options?.providers.find((p) => p.id === draft.providerId), model = provider?.models.find((m) => m.id === draft.model);
  const patch = (values: Partial<AgentSession>) => setDraft((old) => ({ ...old, ...values }));
  async function submit(e: FormEvent) {
    e.preventDefault(); if (saving || reloading) return;
    setSaving(true); setError('');
    try {
      const { revision, name, providerId, model, effort, permissions } = draft;
      const result = await projectRequest<{ session: AgentSession }>(sessionPath(projectId, session.id) + '/settings', token, 'PATCH', { revision, name: name.trim(), providerId, model, effort, permissions });
      saved(result.session);
    } catch (e) { setError((e as Error).message); }
    finally { setSaving(false); }
  }
  async function reload() {
    if (!window.confirm('Reload saved settings and discard these changes?')) return;
    setReloading(true);
    try { const r = await projectRequest<{ session: AgentSession }>(sessionPath(projectId, session.id)); setDraft(r.session); setError(''); }
    catch (e) { setError((e as Error).message); }
    finally { setReloading(false); }
  }
  return <dialog className="project-dialog agent-settings-dialog" ref={dialog} aria-labelledby="session-settings-title" onCancel={(e) => { e.preventDefault(); if (!saving) close(); }}>
    <form onSubmit={(e) => void submit(e)}>
      <header className="project-dialog-header"><h2 id="session-settings-title">Session settings</h2><button type="button" className="project-close" aria-label="Close" disabled={saving} onClick={close}>×</button></header>
      <div className="agent-settings-tabs" role="tablist" aria-label="Session settings sections">{(['General', 'Tools'] as const).map((name) => <button type="button" key={name} role="tab" tabIndex={tab === name ? 0 : -1} aria-selected={tab === name} aria-controls={`session-settings-${name}`} className={tab === name ? 'selected' : ''} onClick={() => setTab(name)} onKeyDown={(e) => {
        if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) { e.preventDefault(); const next = e.key === 'Home' ? 'General' : e.key === 'End' ? 'Tools' : tab === 'General' ? 'Tools' : 'General'; setTab(next); const buttons = e.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('button'); buttons?.[next === 'General' ? 0 : 1].focus(); }
      }}>{name}</button>)}</div>
      <fieldset className="project-fields" disabled={saving || reloading} id={`session-settings-${tab}`} role="tabpanel" aria-label={tab}>
        {tab === 'General' ? <>
          <ProjectField id="settings-session-name" label="Name"><input id="settings-session-name" required maxLength={120} value={draft.name} onChange={(e) => patch({ name: e.target.value })} /></ProjectField>
          <ProjectField id="settings-session-provider" label="Provider"><select id="settings-session-provider" value={draft.providerId} onChange={(e) => {
            const p = options?.providers.find((p) => p.id === e.target.value), m = p?.models[0]; patch({ providerId: e.target.value, model: m?.id ?? '', effort: m?.defaultEffort ?? '' });
          }}>{!provider && <option value={draft.providerId}>Unavailable provider</option>}{options?.providers.map((p) => <option key={p.id} value={p.id} disabled={!p.models.length}>{p.name}</option>)}</select></ProjectField>
          <div className="project-form-row">
            <ProjectField id="settings-session-model" label="Model"><select id="settings-session-model" value={draft.model} onChange={(e) => patch({ model: e.target.value, effort: provider?.models.find((m) => m.id === e.target.value)?.defaultEffort ?? '' })}>
              {!model && <option value={draft.model}>{draft.model}</option>}{provider?.models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></ProjectField>
            <ProjectField id="settings-session-effort" label="Reasoning"><select id="settings-session-effort" value={draft.effort} onChange={(e) => patch({ effort: e.target.value })}>{!model?.efforts.includes(draft.effort) && <option value={draft.effort}>{draft.effort}</option>}{model?.efforts.map((e) => <option key={e} value={e}>{e}</option>)}</select></ProjectField>
          </div>
        </> : <div className="agent-permissions">{(['Files', 'Terminal'] as const).map((group) => <fieldset key={group}><legend>{group}</legend>
          {tools.filter((id) => ['studio.exec_command', 'studio.write_stdin', 'studio.terminate_process'].includes(id) === (group === 'Terminal')).map((id) => <label key={id} className="agent-permission">
            <span>{toolLabels[id]}</span><input type="checkbox" role="switch" aria-label={toolLabels[id]} checked={draft.permissions[id]} onChange={(e) => patch({ permissions: { ...draft.permissions, [id]: e.target.checked } })} /><span className="agent-switch" aria-hidden="true" />
          </label>)}</fieldset>)}</div>}
      </fieldset>
      {busyRun(draft.latestRun?.state) && <p className="project-dialog-error">Stop the current run before saving settings.</p>}
      {error && <p className="project-dialog-error" role="alert">{error}</p>}
      <footer className="project-actions">{error && <button type="button" disabled={saving || reloading} onClick={() => void reload()}>Reload saved</button>}<button type="button" disabled={saving} onClick={close}>Cancel</button><button className="project-primary" disabled={saving || reloading || busyRun(draft.latestRun?.state)}>{saving ? 'Saving…' : 'Save changes'}</button></footer>
    </form>
  </dialog>;
}
