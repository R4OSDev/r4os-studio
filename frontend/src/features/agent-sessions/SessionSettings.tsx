import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { AgentSession, AgentToolId, SessionOptions, NativeImageCapability } from '../../../../shared/agent-sessions';
import { ProjectField } from '../projects/ProjectField';
import { useSessionApi, sessionPath, busyRun, toolLabels, updateToolIds, remoteToolIds, imageToolIds } from './api';

const tools = Object.keys(toolLabels) as AgentToolId[];
const sections = ['General', 'Tools', 'Skills'] as const;
const editable = (s: AgentSession) => JSON.stringify([s.name, s.providerId, s.model, s.effort, s.fastMode, s.webSearchEnabled ?? true, s.imageGenerationEnabled ?? true, s.roadmapEnabled ?? true, tools.map((id) => s.permissions[id]), Object.entries(s.skillOverrides ?? {}).sort()]);
export function SessionSettings({ session, token, projectId, close, saved, reloaded, dirtyChanged, busyChanged }: {
  session: AgentSession; token: string; projectId: string; close: () => void; saved: (session: AgentSession) => void;
  dirtyChanged: (value: boolean) => void; busyChanged: (value: boolean) => void;
  reloaded?: (session: AgentSession) => void;
}) {
  const { request: projectRequest, scope } = useSessionApi();
  const [draft, setDraft] = useState(session), [options, setOptions] = useState<SessionOptions | null>(null);
  const [imageCapability, setImageCapability] = useState<{ key: string; value?: NativeImageCapability; error?: string } | null>(null);
  const [baseline, setBaseline] = useState(session);
  const [error, setError] = useState(''), [saving, setSaving] = useState(false), [reloading, setReloading] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null), [tab, setTab] = useState<typeof sections[number]>('General');
  const dirty = editable(draft) !== editable(baseline);
  const developmentTools = ['studio-tools-v2', 'studio-tools-v3', 'studio-tools-v4', 'studio-tools-v5', 'studio-tools-v6', 'studio-tools-v7', 'studio-tools-v8', 'studio-tools-v9', 'studio-tools-v10', 'studio-tools-v11'].includes(draft.engine.profile);
  const provider = options?.providers.find((p) => p.id === draft.providerId), model = provider?.models.find((m) => m.id === draft.model);
  useEffect(() => { dirtyChanged(dirty); return () => dirtyChanged(false); }, [dirty, dirtyChanged]);
  useEffect(() => { busyChanged(saving || reloading); return () => busyChanged(false); }, [saving, reloading, busyChanged]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  const requestClose = () => { if (!saving && !reloading && (!dirty || window.confirm('Discard unsaved session settings?'))) close(); };
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
  }, [projectId, projectRequest]);
  const hasImageTools = 'studio.list_generated_images' in draft.permissions;
  const imageKey = draft.providerId + ':' + draft.model + ':' + draft.engine.profile;
  useEffect(() => {
    if (tab !== 'Tools' || draft.imageGenerationEnabled === false || !hasImageTools) return;
    const controller = new AbortController(), query = new URLSearchParams({ providerId: draft.providerId, model: draft.model });
    void projectRequest<NativeImageCapability>(sessionPath(projectId, session.id) + '/image-capability?' + query, '', 'GET', undefined, controller.signal)
      .then(value => { if (!controller.signal.aborted) setImageCapability({ key: imageKey, value }); })
      .catch((failure: Error) => { if (!controller.signal.aborted) setImageCapability({ key: imageKey, error: failure.message }); });
    return () => controller.abort();
  }, [tab, draft.imageGenerationEnabled, hasImageTools, draft.providerId, draft.model, imageKey, projectId, session.id, projectRequest]);
  const patch = (values: Partial<AgentSession>) => setDraft((old) => ({ ...old, ...values }));
  async function submit(e: FormEvent) {
    e.preventDefault(); if (saving || reloading) return;
    setSaving(true); setError('');
    try {
      const { revision, name, permissions, providerId, model, effort, fastMode } = draft;
      const result = await projectRequest<{ session: AgentSession }>(sessionPath(projectId, session.id) + '/settings', token, 'PATCH', { revision, name: name.trim(), permissions, providerId, model, effort, fastMode, webSearchEnabled: draft.webSearchEnabled ?? true, imageGenerationEnabled: draft.imageGenerationEnabled ?? true, ...(scope === 'project' ? { roadmapEnabled: draft.roadmapEnabled ?? true } : {}), skillOverrides: draft.skillOverrides ?? {} });
      saved(result.session);
    } catch (e) { setError((e as Error).message); }
    finally { setSaving(false); }
  }
  async function reload() {
    if (!window.confirm('Reload saved settings and discard these changes?')) return;
    setReloading(true);
    try { const r = await projectRequest<{ session: AgentSession }>(sessionPath(projectId, session.id)); setDraft(r.session); setBaseline(r.session); reloaded?.(r.session); setError(''); }
    catch (e) { setError((e as Error).message); }
    finally { setReloading(false); }
  }
  return <dialog className="project-dialog agent-settings-dialog" ref={dialog} aria-labelledby="session-settings-title" onCancel={(e) => { e.preventDefault(); requestClose(); }}>
    <form onSubmit={(e) => void submit(e)}>
      <header className="project-dialog-header"><h2 id="session-settings-title">Session settings</h2><button type="button" className="project-close" aria-label="Close" disabled={saving || reloading} onClick={requestClose}>×</button></header>
      <div className="agent-settings-tabs" role="tablist" aria-label="Session settings sections">{sections.map((name) => <button type="button" key={name} role="tab" tabIndex={tab === name ? 0 : -1} aria-selected={tab === name} aria-controls={`session-settings-${name}`} className={tab === name ? 'selected' : ''} onClick={() => setTab(name)} onKeyDown={(e) => {
        if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) { e.preventDefault(); const index = e.key === 'Home' ? 0 : e.key === 'End' ? sections.length - 1 : (sections.indexOf(tab) + (e.key === 'ArrowRight' ? 1 : sections.length - 1)) % sections.length; setTab(sections[index]); e.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('button')?.[index].focus(); }
      }}>{name}</button>)}</div>
      <fieldset className="project-fields" disabled={saving || reloading} id={`session-settings-${tab}`} role="tabpanel" aria-label={tab}>
        {tab === 'General' ? <>
          <ProjectField id="settings-session-name" label="Name"><input id="settings-session-name" required maxLength={120} value={draft.name} onChange={(e) => patch({ name: e.target.value })} /></ProjectField>
          <ProjectField id="settings-session-provider" label="Provider"><select id="settings-session-provider" value={draft.providerId} onChange={(e) => {
            const next = options?.providers.find((p) => p.id === e.target.value), selected = next?.models.find((m) => m.id === draft.model) ?? next?.models[0];
            patch({ providerId: e.target.value, model: selected?.id ?? '', effort: selected?.efforts.includes(draft.effort) ? draft.effort : selected?.defaultEffort ?? '', fastMode: draft.fastMode && !!selected?.fastModeAvailable });
          }}>{!provider && <option value={draft.providerId}>Unavailable provider</option>}{options?.providers.map((p) => <option key={p.id} value={p.id} disabled={!p.models.length}>{p.name}</option>)}</select></ProjectField>
          <ProjectField id="settings-session-model" label="Model"><select id="settings-session-model" value={draft.model} onChange={(e) => {
            const next = provider?.models.find((m) => m.id === e.target.value); patch({ model: e.target.value, effort: next?.efforts.includes(draft.effort) ? draft.effort : next?.defaultEffort ?? '', fastMode: draft.fastMode && !!next?.fastModeAvailable });
          }}>{!model && <option value={draft.model}>{draft.model}</option>}{provider?.models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></ProjectField>
          <ProjectField id="settings-session-effort" label="Reasoning"><select id="settings-session-effort" value={draft.effort} onChange={(e) => patch({ effort: e.target.value })}>{!model?.efforts.includes(draft.effort) && <option value={draft.effort}>{draft.effort}</option>}{model?.efforts.map((effort) => <option key={effort}>{effort}</option>)}</select></ProjectField>
          <ProjectField id="settings-session-fast" label="Fast Mode"><select id="settings-session-fast" value={draft.fastMode ? 'on' : 'off'} onChange={(e) => patch({ fastMode: e.target.value === 'on' })}><option value="off">Off</option><option value="on" disabled={!model?.fastModeAvailable}>On</option></select></ProjectField>
        </> : tab === 'Skills' ? <div className="agent-skill-choices">
          <p>Global skills are enabled by default. Saved choices apply from the next run.</p>
          <p>Disabling a skill removes its next-run catalog and resource access. Earlier conversation content remains in the native history.</p>
          {!options && <p role="status">Loading global skills…</p>}
          {options && !options.skills?.length && <p>No global skills are available.</p>}
          {options?.skills?.map((skill) => <label key={skill.id} className="agent-permission" data-skill-id={skill.id}>
            <span><strong>{skill.name}</strong><small>{skill.available ? skill.description : skill.reason}</small></span>
            <input type="checkbox" role="switch" aria-label={'Skill ' + skill.name} checked={(draft.skillOverrides ?? {})[skill.id] !== false} onChange={(e) => {
              const choices = { ...draft.skillOverrides }; if (e.target.checked) delete choices[skill.id]; else choices[skill.id] = false; patch({ skillOverrides: choices });
            }} /><span className="agent-switch" aria-hidden="true" />
          </label>)}
        </div> : <div className="agent-permissions"><fieldset><legend>Web</legend>
          <label className="agent-permission"><span>Web search</span><input type="checkbox" role="switch" aria-label="Web search" checked={draft.webSearchEnabled ?? true} onChange={(e) => patch({ webSearchEnabled: e.target.checked })} /><span className="agent-switch" aria-hidden="true" /></label>
          <p className="agent-terminal-hint">Search the web, open pages and find text. On by default. Changes apply from the next run. Availability depends on the selected model and account.</p>
        </fieldset>{scope === 'project' && <fieldset><legend>Roadmap</legend>
          <label className="agent-permission"><span>Roadmap</span><input type="checkbox" role="switch" aria-label="Roadmap" checked={draft.roadmapEnabled ?? true} onChange={(e) => patch({ roadmapEnabled: e.target.checked })} /><span className="agent-switch" aria-hidden="true" /></label>
          <p className="agent-terminal-hint">Use this project’s shared roadmap. On by default. Changes apply from the next run. Earlier conversation content remains in the native history.</p>
          <p className="agent-terminal-hint" role="status">{draft.roadmapAccess?.available ? 'Roadmap tools available in this session.' : draft.roadmapAccess?.reason ?? 'New session required for Roadmap tools. This conversation keeps its original native tool profile.'}</p>
        </fieldset>}{(scope === 'skill' ? ['Files', 'Terminal', 'Skills', 'Images'] : ['Files', 'Terminal', 'Build', 'VM', 'Updates', 'GitHub', 'Remote Hosts', 'Images']).map((group) => <fieldset key={group}><legend>{group}</legend>
          {group === 'Images' && <><label className="agent-permission"><span>Image generation</span><input type="checkbox" role="switch" aria-label="Image generation" checked={draft.imageGenerationEnabled ?? true} onChange={event => patch({ imageGenerationEnabled: event.target.checked })} /><span className="agent-switch" aria-hidden="true" /></label>
            <p className="agent-terminal-hint">On by default. Effective only when this account, provider, model and worker support native image generation. Changes apply from the next run; saving settings does not generate images.</p>
            <p className="agent-terminal-hint" role="status">{draft.imageGenerationEnabled === false ? 'Image generation is off for the next run.' : !hasImageTools ? 'New session required for generated-image tools. This conversation keeps its original profile.' : imageCapability?.key === imageKey ? imageCapability.value?.reason ?? imageCapability.error : 'Checking native image capability…'}</p>
            <p className="agent-terminal-hint">{scope === 'project' ? 'Project import also needs Write file, and Create directory for new folders. Register the asset and verify its finished R4X resources.' : 'These images belong to this skill session. No project import or project filesystem is available.'}</p></>}

          {tools.filter((id) => (scope === 'skill' ? id in draft.permissions : !['studio.validate_skill', 'studio.save_skill'].includes(id)) && (imageToolIds.includes(id) ? 'Images' : remoteToolIds.includes(id) ? 'Remote Hosts' : id === 'studio.push_project' ? 'GitHub' : updateToolIds.includes(id) ? 'Updates' : ['studio.validate_skill', 'studio.save_skill'].includes(id) ? 'Skills' : ['studio.exec_command', 'studio.write_stdin', 'studio.terminate_process'].includes(id) ? 'Terminal' : ['studio.build_project', 'studio.deploy_project', 'studio.run_project', 'studio.read_development_job', 'studio.stop_development_job', 'studio.complete_development_job'].includes(id) ? 'Build' : ['studio.capture_vm', 'studio.send_vm_input', 'studio.start_project_vm'].includes(id) ? 'VM' : 'Files') === group).map((id) => <label key={id} className="agent-permission">
            <span>{toolLabels[id]}</span><input type="checkbox" role="switch" aria-label={toolLabels[id]} checked={!!draft.permissions[id]} disabled={!(id in draft.permissions)} onChange={(e) => patch({ permissions: { ...draft.permissions, [id]: e.target.checked } })} /><span className="agent-switch" aria-hidden="true" />
          </label>)}
          {group === 'Files' && <p className="agent-terminal-hint">{'studio.read_attachment' in draft.permissions ? 'Read attachment is readonly and also needs Read file. Long document contents require this tool; earlier conversation content remains available.' : 'New session required for the long-document attachment tool. Short documents can be sent as text.'}</p>}
          {group === 'VM' && developmentTools && <p className="agent-terminal-hint">{['studio-tools-v7', 'studio-tools-v8', 'studio-tools-v9', 'studio-tools-v10', 'studio-tools-v11'].includes(draft.engine.profile) ? 'GUI text, printable keys, arrows and navigation are available with a current screenshot and a newly deployed helper. Key repeat is limited to 16 events.' : 'This conversation keeps its original key list. Full navigation keys require a new session. GUI text can use Text with a current frame ID and a newly deployed helper.'}</p>}
          {group === 'Updates' && <p className="agent-terminal-hint">{['studio-tools-v5', 'studio-tools-v6', 'studio-tools-v7', 'studio-tools-v8', 'studio-tools-v9', 'studio-tools-v10', 'studio-tools-v11'].includes(draft.engine.profile) ? 'Commit and rollback default off. Enable only for the intended VM update and possible reboot. Batch resume also needs Commit permission. Skills do not grant rights.' : 'Create a new project session for update tools. This conversation keeps its existing profile.'}</p>}{group === 'Build' && !developmentTools && <p className="agent-terminal-hint">New session required for Build and VM tools.</p>}{group === 'Build' && developmentTools && (!options?.development || !options.development.execute.available) && <p className="agent-terminal-hint">{options?.development?.execute.reason ?? 'Development host unavailable.'}</p>}{group === 'VM' && !['studio-tools-v3', 'studio-tools-v4', 'studio-tools-v5', 'studio-tools-v6', 'studio-tools-v7', 'studio-tools-v8', 'studio-tools-v9', 'studio-tools-v10', 'studio-tools-v11'].includes(draft.engine.profile) && <p className="agent-terminal-hint">New session required for Start project VM.</p>}{group === 'VM' && ['studio-tools-v3', 'studio-tools-v4', 'studio-tools-v5', 'studio-tools-v6', 'studio-tools-v7', 'studio-tools-v8', 'studio-tools-v9', 'studio-tools-v10', 'studio-tools-v11'].includes(draft.engine.profile) && !options?.development?.startVm?.available && <p className="agent-terminal-hint">{options?.development?.startVm?.reason ?? 'VM start host unavailable.'}</p>}{group === 'VM' && options?.development && !options.development.input.available && developmentTools && <p className="agent-terminal-hint">{options.development.input.reason}</p>}{group === 'GitHub' && <p className="agent-terminal-hint">{['studio-tools-v6', 'studio-tools-v7', 'studio-tools-v8', 'studio-tools-v9', 'studio-tools-v10', 'studio-tools-v11'].includes(draft.engine.profile) ? 'Default off. Push uses this project’s bound repository and saved changes, requires a commit description and keeps tokens on the host. Changes apply from the next run.' : 'New session required for GitHub push. This conversation keeps its existing native tool profile.'}</p>}{group === 'Remote Hosts' && <p className="agent-terminal-hint" role="status">{draft.remoteHostAccess?.hostName ? `Assigned: ${draft.remoteHostAccess.hostName}. ` : ''}{draft.remoteHostAccess?.reason ?? 'New session required for Remote Host tools.'} Remote permissions default on for new compatible project sessions. File transfers also require the matching Workspace file permission. Changes apply from the next run; assignment alone starts no connection.</p>}{group === 'Terminal' && <p className="agent-terminal-hint">Terminal commands can read and change files in this workspace.</p>}</fieldset>)}</div>}
      </fieldset>
      {busyRun(draft.latestRun?.state) && <p className="project-dialog-error">Stop the current run before saving settings.</p>}
      {error && <p className="project-dialog-error" role="alert">{error}</p>}
      <footer className="project-actions">{error && <button type="button" disabled={saving || reloading} onClick={() => void reload()}>Reload saved</button>}<button type="button" disabled={saving || reloading} onClick={requestClose}>Cancel</button><button className="project-primary" disabled={saving || reloading || busyRun(draft.latestRun?.state)}>{saving ? 'Saving…' : 'Save changes'}</button></footer>
    </form>
  </dialog>;
}
