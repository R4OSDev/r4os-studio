import { deferView } from '../../app/DeferredView';
import { Suspense, useCallback, useEffect, useState } from 'react';
import { Icon } from '../../app/Icon';
import { WorkspaceNavigation } from '../../app/WorkspaceNavigation';
import { useProjects } from './useProjects';
import { ProjectNavigationList } from './ProjectNavigationList';
import { useProjectActivity } from './useProjectActivity';
import type { ProjectSettingsView } from './ProjectSettings';
import { useSessions } from '../agent-sessions/useSessions';
import { busyRun } from '../agent-sessions/api';
import '../agent-sessions/styles.css';
import './styles.css';
import { editorRegistry } from '../project-editor/registry';
import {GithubNavigation,ProjectIssues} from '../github-connections/ProjectIssues';
import {useProjectIssues} from '../github-connections/useProjectIssues';
import { useIssueCounts } from '../github-connections/useIssueCounts';
import { useProjectOpening } from '../github-connections/useProjectOpening';
import { useRoadmap } from '../project-roadmaps/useRoadmap';
import { RoadmapNavigation } from '../project-roadmaps/RoadmapNavigation';
import { useBoards } from '../project-boards/useBoards';
import { BoardNavigation } from '../project-boards/BoardNavigation';
const StatisticsPanel = deferView(() => import('../statistics/StatisticsPanel').then(module => ({default: module.StatisticsPanel})));
const NewProjectDialog = deferView(() => import('./NewProjectDialog').then(module => ({default: module.NewProjectDialog})), props => props.close());
const RunTestSettings = deferView(() => import('./RunTestSettings').then(module => ({default: module.RunTestSettings})));
const ProjectSettings = deferView(() => import('./ProjectSettings').then(module => ({default: module.ProjectSettings})));
const ProjectAgentsSettings = deferView(() => import('./ProjectAgentsSettings').then(module => ({default: module.ProjectAgentsSettings})));
const ProjectPinsSettings = deferView(() => import('./ProjectPinsSettings').then(module => ({default: module.ProjectPinsSettings})));
const NewSessionDialog = deferView(() => import('../agent-sessions/NewSessionDialog').then(module => ({default: module.NewSessionDialog})), props => props.close());
const SessionPanel = deferView(() => import('../agent-sessions/SessionPanel').then(module => ({default: module.SessionPanel})));
const ProjectGithubPanel = deferView(() => import('../github-connections/ProjectGithubPanel').then(module => ({default: module.ProjectGithubPanel})));
const UpdateProjectDialog = deferView(() => import('../github-connections/UpdateProjectDialog').then(module => ({default: module.UpdateProjectDialog})));
const RoadmapPanel = deferView(() => import('../project-roadmaps/RoadmapPanel').then(module => ({default: module.RoadmapPanel})));
const BoardPanel = deferView(() => import('../project-boards/BoardPanel').then(module => ({default: module.BoardPanel})));
const EditorPanel = deferView(() => import('../project-editor/EditorPanel'));
const EditorFiles = deferView(() => import('../project-editor/EditorFiles'));

export interface ProjectNavigation {
  section: 'Sessions' | 'Editor' | 'GitHub' | 'Roadmap' | 'Boards' | 'Statistics' | 'Settings'; settingsView: ProjectSettingsView; sessionId?: string; roadmapVersionId?: string; boardId?: string;
  githubView?:'Connection'|'Issues'; roadmapSubversionId?: string;
}
export function ProjectsWorkspace({ selectedId, select, navigation, navigate, setLeaveGuard }: {
  selectedId: string | null; select: (id: string | null) => void;
  navigation: Record<string, ProjectNavigation>; navigate: (id: string, value: ProjectNavigation) => void;
  setLeaveGuard: (guard: () => boolean) => void;
}) {
  const api = useProjects();
  const activity = useProjectActivity(Boolean(api.token));
  const selected = api.projects.find((project) => project.id === selectedId);
  const opening = useProjectOpening(selected && !selected.deleting ? selected.id : null, api.token);
  const current: ProjectNavigation = selected?.deleting ? { section: 'Settings', settingsView: 'General' } : navigation[selectedId ?? ''] ?? { section: 'Sessions', settingsView: 'General' };
  const [newProject, setNewProject] = useState(false);
  const [newSession, setNewSession] = useState(false);
  const [newRoadmapVersion, setNewRoadmapVersion] = useState(false);
  const [newBoard, setNewBoard] = useState(false);
  const boards = useBoards(selected && current.section === 'Boards' ? selected.id : null, current.boardId);
  const roadmap = useRoadmap(selected && current.section === 'Roadmap' ? selected.id : null, current.roadmapVersionId);
  const sessions = useSessions(selected && current.section === 'Sessions' ? selected.id : null);
  const github=useProjectIssues(selected&&current.section==='GitHub'&&!selected.deleting?selected.id:null);
  const issueCounts=useIssueCounts(!!api.token);
  const githubView=current.githubView==='Issues'&&github.binding!==null?'Issues':'Connection';
  const chooseSession = (id: string) => {
    if (!selected || !leave()) return;
    navigate(selected.id, { ...current, section: 'Sessions', sessionId: id });
    window.history.replaceState(null, '', `#projects/${selected.id}/sessions/${id}`);
  };
  const [dirty, setDirty] = useState(false), [saving, setSaving] = useState(false), [epoch, setEpoch] = useState(0);
  const leave = useCallback(() => {
    const allowed = !saving && !opening.deciding && (!dirty || window.confirm('Discard unsaved changes?'));
    if (allowed) { setNewRoadmapVersion(false); setNewBoard(false); }
    return allowed;
  }, [dirty, saving, opening.deciding, setNewRoadmapVersion, setNewBoard]);
  useEffect(() => { setLeaveGuard(leave); return () => setLeaveGuard(() => true); }, [leave, setLeaveGuard]);

  return <>
    <WorkspaceNavigation className={current.section === 'Statistics' ? 'statistics-project' : ''} fixed={current.section === 'Statistics'} label="Projects navigation">
      <ProjectNavigationList api={api} activity={activity} selectedId={selectedId} saving={saving} counts={issueCounts}
        createProject={() => { if (leave()) { setEpoch(value => value + 1); setDirty(false); setNewProject(true); } }}
        choose={id => { if (id !== selectedId && leave()) select(id); }} />
      {selected ? <nav className="nav-column" aria-label="Project sections">
        <div className="nav-items">{(['Sessions', 'Editor', 'GitHub', 'Roadmap', 'Boards', 'Statistics', 'Settings'] as const).map((section) =>
          <button key={section} type="button" disabled={saving || selected.deleting} className={`nav-item ${current.section === section ? 'selected' : ''}`}
            aria-current={current.section === section ? 'true' : undefined} onClick={() => {
              if (section !== current.section && leave()) navigate(selected.id, { ...current, section, settingsView: 'General' });
            }}><Icon name={section === 'Statistics' ? 'statistics' : section === 'Boards' ? 'board' : section === 'Sessions' ? 'terminal' : section === 'Editor' || section === 'Roadmap' ? 'book' : 'settings'} /><span>{section}</span></button>)}</div>
      </nav> : <div className="nav-column" aria-hidden="true" />}
      {selected&&current.section==='GitHub'?<GithubNavigation model={github} count={issueCounts[selected.id]} selected={githubView} disabled={saving||!!selected.deleting} choose={view=>{
        if(view!==githubView&&(view!=='Issues'||github.binding)&&leave())navigate(selected.id,{...current,githubView:view});
      }}/>:selected && current.section === 'Boards' ? <BoardNavigation model={boards} disabled={saving} choose={id => {
        if (leave()) { setDirty(false); navigate(selected.id, { ...current, boardId: id }); }
      }} create={() => { if (leave()) { setDirty(false); setNewBoard(true); } }} />
        : selected && current.section === 'Roadmap' ? <RoadmapNavigation model={roadmap} selected={current.roadmapVersionId} disabled={saving}
        choose={(id) => { if (leave()) { setEpoch((value) => value + 1); setDirty(false); navigate(selected.id, { ...current, roadmapVersionId: id, roadmapSubversionId:undefined }); } }}
        create={() => { if (leave()) { setEpoch((value) => value + 1); setDirty(false); setNewRoadmapVersion(true); } }} />
        : selected && current.section === 'Editor' ? <Suspense fallback={<div className="nav-column" />}><EditorFiles key={selected.id} id={selected.id} token={api.token} /></Suspense> : selected && current.section === 'Settings' ? <nav className="nav-column" aria-label="Project settings">
        <div className="nav-items">{(['General', 'Pins', 'Virtual machine', 'Remote host', 'Run & Test', 'Agents.md'] as const).map((view) => <button key={view} type="button" disabled={saving || selected.deleting}
          className={`nav-item ${current.settingsView === view ? 'selected' : ''}`} aria-current={current.settingsView === view ? 'page' : undefined}
          onClick={() => { if (view !== current.settingsView && leave()) navigate(selected.id, { ...current, settingsView: view }); }}><span>{view}</span></button>)}</div>
      </nav> : selected && current.section === 'Sessions' ? <nav className="nav-column" aria-label="Project sessions">
        <div className="nav-items">
          <button type="button" className="nav-item project-new" disabled={!api.token || saving} onClick={() => { if (leave()) setNewSession(true); }}><span className="project-plus" aria-hidden="true">+</span><span>New Session</span></button>
          {sessions.error ? <><p className="project-nav-message" role="alert">{sessions.error}</p><button className="nav-item" onClick={sessions.reload}>Retry</button></>
            : sessions.loading ? <p className="project-nav-message" role="status">Loading sessions…</p>
              : sessions.sessions.map((s) => <button key={s.id} type="button" className={`nav-item ${current.sessionId === s.id ? 'selected' : ''}`} aria-current={current.sessionId === s.id ? 'page' : undefined} onClick={() => chooseSession(s.id)}>
                <span className="provider-view-name">{s.name}</span>{sessions.fresh && busyRun(s.latestRun?.state) && <span className="session-nav-status" aria-label="Run active" />}</button>)}
        </div>
      </nav> : current.section === 'Statistics' ? null : <div className="nav-column" aria-hidden="true" />}
    </WorkspaceNavigation>
    <main className={`main-area ${current.section === 'Editor' ? 'editor-main' : current.section === 'Boards' ? 'boards-main' : ''}`} aria-label="Project content">
      {opening.notice && <p className="project-message project-background-status" role="status">{opening.notice} <button className="project-reload" type="button" onClick={opening.refresh}>Refresh GitHub status</button></p>}
      {selected && <>
        {current.section !== 'Editor' && !(current.section === 'Sessions' && current.sessionId) && <div className={`page-heading${current.section==='Roadmap'?' roadmap-page-heading':''}`}><h1>{selected.name}{current.section==='Roadmap'?' Roadmap':''}</h1><span className="page-rule" />
          {current.section==='Roadmap'&&<button type="button" className="roadmap-page-refresh" disabled={saving} onClick={()=>{if(!dirty||window.confirm('Discard unsaved roadmap changes and refresh?'))roadmap.reload();}}>Refresh</button>}
        </div>}
        {current.section === 'Statistics' && <StatisticsPanel key={selected.id} projectId={selected.id} reauth={api.reload} />}
        {current.section === 'Editor' && <Suspense fallback={<p className="session-empty">Loading editor…</p>}><EditorPanel key={selected.id} id={selected.id} token={api.token} /></Suspense>}
        {current.section === 'GitHub' && (githubView==='Connection'?<ProjectGithubPanel key={selected.id} id={selected.id} token={api.token} dirtyChanged={setDirty} busyChanged={setSaving} />:
          <ProjectIssues key={selected.id} model={github} token={api.token} busyChanged={setSaving} openRoadmap={link=>{
            if(leave())navigate(selected.id,{...current,section:'Roadmap',roadmapVersionId:link.versionId,roadmapSubversionId:link.subversionId});
          }}/>)}
        {current.section === 'Boards' && <BoardPanel key={selected.id + ':' + (current.boardId ?? 'auto')} id={selected.id} token={api.token} renewAuth={api.reload} model={boards} creating={newBoard}
          closeCreate={() => { setNewBoard(false); setDirty(false); }} created={id => { setNewBoard(false); setDirty(false); navigate(selected.id, { ...current, boardId: id }); }}
          removed={() => { setDirty(false); navigate(selected.id, { ...current, boardId: undefined }); boards.reload(); }} dirtyChanged={setDirty} busyChanged={setSaving} />}
        {current.section === 'Roadmap' && <RoadmapPanel key={selected.id + ':' + (current.roadmapVersionId ?? 'overview') + ':' + epoch} id={selected.id} token={api.token} model={roadmap}
          selectedVersionId={current.roadmapVersionId} selectedSubversionId={current.roadmapSubversionId} creating={newRoadmapVersion} closeCreate={() => setNewRoadmapVersion(false)}
          created={(id) => { setNewRoadmapVersion(false); setDirty(false); navigate(selected.id, { ...current, roadmapVersionId: id }); }}
          dirty={dirty} dirtyChanged={setDirty} busyChanged={setSaving} />}
        {current.section === 'Settings' && current.settingsView === 'Run & Test' && <RunTestSettings key={selected.id + ':' + epoch} id={selected.id} token={api.token} dirtyChanged={setDirty} busyChanged={setSaving} />}
        {current.section === 'Settings' && current.settingsView === 'Agents.md' && <ProjectAgentsSettings key={`${selected.id}:${epoch}`}
          id={selected.id} token={api.token} dirtyChanged={setDirty} busyChanged={setSaving} />}
        {current.section === 'Settings' && current.settingsView === 'Pins' && <ProjectPinsSettings key={`${selected.id}:${epoch}`}
          id={selected.id} token={api.token} dirtyChanged={setDirty} busyChanged={setSaving} />}
        {current.section === 'Settings' && current.settingsView !== 'Run & Test' && current.settingsView !== 'Agents.md' && current.settingsView !== 'Pins' && <ProjectSettings key={`${selected.id}:${current.settingsView}:${epoch}`}
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
        {current.section === 'Sessions' && (current.sessionId ? <SessionPanel key={`${selected.id}:${current.sessionId}`} projectId={selected.id} ownerName={selected.name} sessionId={current.sessionId} token={api.token} changed={sessions.reload} refreshAuth={api.reload} dirtyChanged={setDirty} busyChanged={setSaving} removed={() => {
          navigate(selected.id, { ...current, sessionId: undefined }); window.history.replaceState(null, '', `#projects/${selected.id}/sessions`);
        }} /> : <p className="session-empty">Select a session or create one.</p>)}
      </>}
    </main>
    {selected && opening.deciding && opening.status && <UpdateProjectDialog key={selected.id} id={selected.id} name={selected.name} status={opening.status} blockedReason={dirty ? 'Keep or save your current draft before updating. Ignore to continue local work.' : saving ? 'Wait for the current session or save operation before updating.' : undefined} busy={opening.updating} error={opening.error} update={() => { if(!dirty&&!saving)void opening.update(); }} ignore={opening.ignore} />}
    {newProject && <NewProjectDialog token={api.token} close={() => setNewProject(false)} created={async (project) => {
      api.remember(project); await api.reload(); select(project.id);
      navigate(project.id, { section: 'Sessions', settingsView: 'General' }); setNewProject(false);
    }} />}
    {newSession && selected && <NewSessionDialog key={selected.id} projectId={selected.id} token={api.token} close={() => setNewSession(false)} created={(session) => { sessions.reload(); chooseSession(session.id); setNewSession(false); }} />}
  </>;
}
