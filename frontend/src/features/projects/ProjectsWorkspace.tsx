import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { Icon } from '../../app/Icon';
import { useProjects } from './useProjects';
import { NewProjectDialog } from './NewProjectDialog';
import { RunTestSettings } from './RunTestSettings';
import { ProjectSettings } from './ProjectSettings';
import { ProjectAgentsSettings } from './ProjectAgentsSettings';
import type { ProjectSettingsView } from './ProjectSettings';
import { useSessions } from '../agent-sessions/useSessions';
import { NewSessionDialog } from '../agent-sessions/NewSessionDialog';
import { SessionPanel } from '../agent-sessions/SessionPanel';
import { busyRun } from '../agent-sessions/api';
import '../agent-sessions/styles.css';
import './styles.css';
import { editorRegistry } from '../project-editor/registry';
const EditorPanel = lazy(() => import('../project-editor/EditorPanel'));
const EditorFiles = lazy(() => import('../project-editor/EditorFiles'));

export interface ProjectNavigation {
  section: 'Sessions' | 'Editor' | 'Settings'; settingsView: ProjectSettingsView; sessionId?: string;
}
export function ProjectsWorkspace({ selectedId, select, navigation, navigate, setLeaveGuard }: {
  selectedId: string | null; select: (id: string | null) => void;
  navigation: Record<string, ProjectNavigation>; navigate: (id: string, value: ProjectNavigation) => void;
  setLeaveGuard: (guard: () => boolean) => void;
}) {
  const api = useProjects();
  const selected = api.projects.find((project) => project.id === selectedId);
  const current: ProjectNavigation = selected?.deleting ? { section: 'Settings', settingsView: 'General' } : navigation[selectedId ?? ''] ?? { section: 'Sessions', settingsView: 'General' };
  const [newProject, setNewProject] = useState(false);
  const [newSession, setNewSession] = useState(false);
  const sessions = useSessions(selected?.id ?? null);
  const chooseSession = (id: string) => {
    if (!selected || !leave()) return;
    navigate(selected.id, { ...current, section: 'Sessions', sessionId: id });
    window.history.replaceState(null, '', `#projects/${selected.id}/sessions/${id}`);
  };
  const [dirty, setDirty] = useState(false), [saving, setSaving] = useState(false), [epoch, setEpoch] = useState(0);
  const leave = useCallback(() => !saving && (!dirty || window.confirm('Discard unsaved changes?')), [dirty, saving]);
  useEffect(() => { setLeaveGuard(leave); return () => setLeaveGuard(() => true); }, [leave, setLeaveGuard]);

  return <>
    <aside className="navigation" aria-label="Projects navigation">
      <nav className="nav-column" aria-label="Projects">
        <div className="column-heading">Projects</div>
        <div className="nav-items" aria-busy={api.loading}>
          <button type="button" className="nav-item project-new" disabled={!api.token || saving} onClick={() => {
            if (leave()) { setEpoch((value) => value + 1); setDirty(false); setNewProject(true); }
          }}><span className="project-plus" aria-hidden="true">+</span><span>New Project</span></button>
          {api.loading ? <p className="project-nav-message" role="status">Loading projects…</p>
            : api.error ? <><p className="project-nav-message" role="alert">{api.error}</p><button className="nav-item" onClick={() => void api.reload()}>Retry</button></>
              : api.projects.length === 0 ? <p className="project-nav-message" role="status">No projects yet.</p>
                : api.projects.map((project) => <button type="button" key={project.id} disabled={saving}
                  className={`nav-item ${selectedId === project.id ? 'selected' : ''}`}
                  aria-current={selectedId === project.id ? 'true' : undefined}
                  onClick={() => { if (project.id !== selectedId && leave()) select(project.id); }}>
                  <Icon name="folder" /><span>{project.name}{project.deleting ? ' · Deleting…' : ''}</span>
                </button>)}
        </div>
      </nav>
      {selected ? <nav className="nav-column" aria-label="Project sections">
        <div className="column-heading" aria-hidden="true" />
        <div className="nav-items">{(['Sessions', 'Editor', 'Settings'] as const).map((section) =>
          <button key={section} type="button" disabled={saving || selected.deleting} className={`nav-item ${current.section === section ? 'selected' : ''}`}
            aria-current={current.section === section ? 'true' : undefined} onClick={() => {
              if (section !== current.section && leave()) navigate(selected.id, { ...current, section, settingsView: 'General' });
            }}><Icon name={section === 'Sessions' ? 'terminal' : section === 'Editor' ? 'book' : 'settings'} /><span>{section}</span></button>)}</div>
      </nav> : <div className="nav-column" aria-hidden="true" />}
      {selected && current.section === 'Editor' ? <Suspense fallback={<div className="nav-column" />}><EditorFiles key={selected.id} id={selected.id} token={api.token} /></Suspense> : selected && current.section === 'Settings' ? <nav className="nav-column" aria-label="Project settings">
        <div className="column-heading" aria-hidden="true" />
        <div className="nav-items">{(['General', 'Virtual machine', 'Run & Test', 'Agents.md'] as const).map((view) => <button key={view} type="button" disabled={saving || selected.deleting}
          className={`nav-item ${current.settingsView === view ? 'selected' : ''}`} aria-current={current.settingsView === view ? 'page' : undefined}
          onClick={() => { if (view !== current.settingsView && leave()) navigate(selected.id, { ...current, settingsView: view }); }}><span>{view}</span></button>)}</div>
      </nav> : selected && current.section === 'Sessions' ? <nav className="nav-column" aria-label="Project sessions">
        <div className="column-heading" aria-hidden="true" />
        <div className="nav-items">
          <button type="button" className="nav-item project-new" disabled={!api.token || saving} onClick={() => { if (leave()) setNewSession(true); }}><span className="project-plus" aria-hidden="true">+</span><span>New Session</span></button>
          {sessions.error ? <><p className="project-nav-message" role="alert">{sessions.error}</p><button className="nav-item" onClick={sessions.reload}>Retry</button></>
            : sessions.loading ? <p className="project-nav-message" role="status">Loading sessions…</p>
              : sessions.sessions.map((s) => <button key={s.id} type="button" className={`nav-item ${current.sessionId === s.id ? 'selected' : ''}`} aria-current={current.sessionId === s.id ? 'page' : undefined} onClick={() => chooseSession(s.id)}>
                <span className="provider-view-name">{s.name}</span>{busyRun(s.latestRun?.state) && <span className="session-nav-status" aria-label="Run active" />}</button>)}
        </div>
      </nav> : <div className="nav-column" aria-hidden="true" />}
    </aside>
    <main className={`main-area ${current.section === 'Editor' ? 'editor-main' : ''}`} aria-label="Project content">
      {selected && <>
        {current.section !== 'Editor' && !(current.section === 'Sessions' && current.sessionId) && <div className="page-heading"><h1>{selected.name}</h1><span className="page-rule" /></div>}
        {current.section === 'Editor' && <Suspense fallback={<p className="session-empty">Loading editor…</p>}><EditorPanel key={selected.id} id={selected.id} token={api.token} /></Suspense>}
        {current.section === 'Settings' && current.settingsView === 'Run & Test' && <RunTestSettings key={selected.id + ':' + epoch} id={selected.id} token={api.token} dirtyChanged={setDirty} busyChanged={setSaving} />}
        {current.section === 'Settings' && current.settingsView === 'Agents.md' && <ProjectAgentsSettings key={`${selected.id}:${epoch}`}
          id={selected.id} token={api.token} dirtyChanged={setDirty} busyChanged={setSaving} />}
        {current.section === 'Settings' && current.settingsView !== 'Run & Test' && current.settingsView !== 'Agents.md' && <ProjectSettings key={`${selected.id}:${current.settingsView}:${epoch}`}
          id={selected.id} view={current.settingsView} token={api.token} dirtyChanged={setDirty} busyChanged={setSaving} saved={api.reload}
          deleted={(id) => {
            editorRegistry.forget(id); api.forget(id); select(null); setDirty(false); setSaving(false);
            window.history.replaceState(null, '', window.location.pathname);
            try {
              const keys = new Set(sessions.sessions.flatMap((session) => ['studio.session.run.' + session.id, 'studio.session.draft.' + session.id]));
              for (let index = sessionStorage.length - 1; index >= 0; index--) {
                const key = sessionStorage.key(index);
                if (key && ((key.startsWith('studio.') && key.includes(id)) || keys.has(key))) sessionStorage.removeItem(key);
              }
            } catch { /* Server deletion does not depend on browser storage access. */ }
          }} />}
        {current.section === 'Sessions' && (current.sessionId ? <SessionPanel key={`${selected.id}:${current.sessionId}`} projectId={selected.id} sessionId={current.sessionId} token={api.token} changed={sessions.reload} refreshAuth={api.reload} dirtyChanged={setDirty} busyChanged={setSaving} /> : <p className="session-empty">Select a session or create one.</p>)}
      </>}
    </main>
    {newProject && <NewProjectDialog token={api.token} close={() => setNewProject(false)} created={async (project) => {
      api.remember(project); await api.reload(); select(project.id);
      navigate(project.id, { section: 'Sessions', settingsView: 'General' }); setNewProject(false);
    }} />}
    {newSession && selected && <NewSessionDialog key={selected.id} projectId={selected.id} token={api.token} close={() => setNewSession(false)} created={(session) => { sessions.reload(); chooseSession(session.id); setNewSession(false); }} />}
  </>;
}
