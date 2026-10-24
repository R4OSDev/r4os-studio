import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { AgentSession, AgentToolId, SessionOptions } from '../../../../shared/agent-sessions';
import { ProjectField } from '../projects/ProjectField';
import { projectRequest, sessionPath, busyRun, toolLabels } from './api';

const tools = Object.keys(toolLabels) as AgentToolId[];
const editable = (s: AgentSession) => JSON.stringify([s.name, tools.map((id) => s.permissions[id])]);
export function SessionSettings({ session, token, projectId, close, saved, dirtyChanged, busyChanged }: {
  session: AgentSession; token: string; projectId: string; close: () => void; saved: (session: AgentSession) => void;
  dirtyChanged: (value: boolean) => void; busyChanged: (value: boolean) => void;
}) {
  const [draft, setDraft] = useState(session), [options, setOptions] = useState<SessionOptions | null>(null);
  const [baseline, setBaseline] = useState(session);
  const [error, setError] = useState(''), [saving, setSaving] = useState(false), [reloading, setReloading] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null), [tab, setTab] = useState<'General' | 'Tools'>('General');
  const dirty = editable(draft) !== editable(baseline);
  const developmentTools = ['studio-tools-v2', 'studio-tools-v3'].includes(draft.engine.profile);
  useEffect(() => { dirtyChanged(dirty); return () => dirtyChanged(false); }, [dirty, dirtyChanged]);
  useEffect(() => { busyChanged(saving || reloading); return () => busyChanged(false); }, [saving, reloading, busyChanged]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  const requestClose = () => { if (!saving && (!dirty || window.confirm('Discard unsaved session settings?'))) close(); };
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
  const patch = (values: Partial<AgentSession>) => setDraft((old) => ({ ...old, ...values }));
  async function submit(e: FormEvent) {
    e.preventDefault(); if (saving || reloading) return;
    setSaving(true); setError('');
    try {
      const { revision, name, permissions } = draft;
      const result = await projectRequest<{ session: AgentSession }>(sessionPath(projectId, session.id) + '/settings', token, 'PATCH', { revision, name: name.trim(), permissions });
      saved(result.session);
    } catch (e) { setError((e as Error).message); }
    finally { setSaving(false); }
  }
  async function reload() {
    if (!window.confirm('Reload saved settings and discard these changes?')) return;
    setReloading(true);
    try { const r = await projectRequest<{ session: AgentSession }>(sessionPath(projectId, session.id)); setDraft(r.session); setBaseline(r.session); setError(''); }
    catch (e) { setError((e as Error).message); }
    finally { setReloading(false); }
  }
  return <dialog className="project-dialog agent-settings-dialog" ref={dialog} aria-labelledby="session-settings-title" onCancel={(e) => { e.preventDefault(); requestClose(); }}>
    <form onSubmit={(e) => void submit(e)}>
      <header className="project-dialog-header"><h2 id="session-settings-title">Session settings</h2><button type="button" className="project-close" aria-label="Close" disabled={saving} onClick={requestClose}>×</button></header>
      <div className="agent-settings-tabs" role="tablist" aria-label="Session settings sections">{(['General', 'Tools'] as const).map((name) => <button type="button" key={name} role="tab" tabIndex={tab === name ? 0 : -1} aria-selected={tab === name} aria-controls={`session-settings-${name}`} className={tab === name ? 'selected' : ''} onClick={() => setTab(name)} onKeyDown={(e) => {
        if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) { e.preventDefault(); const next = e.key === 'Home' ? 'General' : e.key === 'End' ? 'Tools' : tab === 'General' ? 'Tools' : 'General'; setTab(next); const buttons = e.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('button'); buttons?.[next === 'General' ? 0 : 1].focus(); }
      }}>{name}</button>)}</div>
      <fieldset className="project-fields" disabled={saving || reloading} id={`session-settings-${tab}`} role="tabpanel" aria-label={tab}>
        {tab === 'General' ? <>
          <ProjectField id="settings-session-name" label="Name"><input id="settings-session-name" required maxLength={120} value={draft.name} onChange={(e) => patch({ name: e.target.value })} /></ProjectField>
        </> : <div className="agent-permissions">{(['Files', 'Terminal', 'Build', 'VM'] as const).map((group) => <fieldset key={group}><legend>{group}</legend>
          {tools.filter((id) => (['studio.exec_command', 'studio.write_stdin', 'studio.terminate_process'].includes(id) ? 'Terminal' : ['studio.build_project', 'studio.deploy_project', 'studio.run_project', 'studio.read_development_job', 'studio.stop_development_job'].includes(id) ? 'Build' : ['studio.capture_vm', 'studio.send_vm_input', 'studio.start_project_vm'].includes(id) ? 'VM' : 'Files') === group).map((id) => <label key={id} className="agent-permission">
            <span>{toolLabels[id]}</span><input type="checkbox" role="switch" aria-label={toolLabels[id]} checked={!!draft.permissions[id]} disabled={!(id in draft.permissions)} onChange={(e) => patch({ permissions: { ...draft.permissions, [id]: e.target.checked } })} /><span className="agent-switch" aria-hidden="true" />
          </label>)}{group === 'Build' && !developmentTools && <p className="agent-terminal-hint">New session required for Build and VM tools.</p>}{group === 'Build' && developmentTools && (!options?.development || !options.development.execute.available) && <p className="agent-terminal-hint">{options?.development?.execute.reason ?? 'Development host unavailable.'}</p>}{group === 'VM' && draft.engine.profile !== 'studio-tools-v3' && <p className="agent-terminal-hint">New session required for Start project VM.</p>}{group === 'VM' && draft.engine.profile === 'studio-tools-v3' && !options?.development?.startVm?.available && <p className="agent-terminal-hint">{options?.development?.startVm?.reason ?? 'VM start host unavailable.'}</p>}{group === 'VM' && options?.development && !options.development.input.available && developmentTools && <p className="agent-terminal-hint">{options.development.input.reason}</p>}{group === 'Terminal' && <p className="agent-terminal-hint">Terminal commands can read and change files in this workspace.</p>}</fieldset>)}</div>}
      </fieldset>
      {busyRun(draft.latestRun?.state) && <p className="project-dialog-error">Stop the current run before saving settings.</p>}
      {error && <p className="project-dialog-error" role="alert">{error}</p>}
      <footer className="project-actions">{error && <button type="button" disabled={saving || reloading} onClick={() => void reload()}>Reload saved</button>}<button type="button" disabled={saving} onClick={close}>Cancel</button><button className="project-primary" disabled={saving || reloading || busyRun(draft.latestRun?.state)}>{saving ? 'Saving…' : 'Save changes'}</button></footer>
    </form>
  </dialog>;
}
