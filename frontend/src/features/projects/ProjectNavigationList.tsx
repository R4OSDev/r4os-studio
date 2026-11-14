import { useRef, useState } from 'react';
import type { DragEvent, ReactNode } from 'react';
import type { ProjectGroup, ProjectSummary } from '../../../../shared/projects';
import { Icon } from '../../app/Icon';
import type { useProjects } from './useProjects';
import { ProjectGroupDialog } from './ProjectGroupDialog';

const projectDragType = 'application/x-studio-project';
const ungrouped = 'ungrouped';
const groupStorageKey = (id: string) => 'studio.project-group.open.' + id;

function ProjectGroupRow({ group, edit, disabled, children }: {
  group: ProjectGroup; edit: (group: ProjectGroup) => void; disabled: boolean; children: ReactNode;
}) {
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem(groupStorageKey(group.id)) === 'true'; }
    catch { return false; }
  });
  const listId = 'project-group-projects-' + group.id;
  function toggle() {
    const next = !open;
    setOpen(next);
    try {
      if (next) localStorage.setItem(groupStorageKey(group.id), 'true');
      else localStorage.removeItem(groupStorageKey(group.id));
    } catch { /* The current tab keeps its open state. */ }
  }
  return <>
    <div className="project-group-row">
      <button type="button" className="nav-item project-group-toggle" aria-expanded={open} aria-controls={listId}
        title={group.name} onClick={toggle}>
        <Icon name="group" /><span>{group.name}</span><Icon name="chevron" className="project-group-chevron" />
      </button>
      <button type="button" className="project-group-edit" aria-label={`Edit group ${group.name}`} title="Edit group"
        aria-haspopup="dialog" disabled={disabled} onClick={() => edit(group)}><Icon name="pencil" /></button>
    </div>
    <div className="project-group-members" id={listId} hidden={!open}>{open && children}</div>
  </>;
}

export function ProjectNavigationList({ api, activity, selectedId, saving, createProject, choose }: {
  api: ReturnType<typeof useProjects>; activity: ReadonlySet<string>; selectedId: string | null; saving: boolean;
  createProject: () => void; choose: (id: string) => void;
}) {
  const [editor, setEditor] = useState<ProjectGroup | 'create' | null>(null);
  const [draggedProject, setDraggedProject] = useState<{ id: string; groupId: string | null } | null>(null);
  const [target, setTarget] = useState<string | null>(null);
  const [moving, setMoving] = useState(false);
  const [moveError, setMoveError] = useState('');
  const navigation = useRef<HTMLElement>(null);
  const { memberships, groups } = api.grouping;
  const projectsByGroup = new Map<string, ProjectSummary[]>();
  for (const project of api.projects) {
    const id = memberships[project.id] ?? ungrouped;
    const list = projectsByGroup.get(id);
    if (list) list.push(project);
    else projectsByGroup.set(id, [project]);
  }
  const disabled = !api.token || moving || saving;

  function endDrag() {
    setDraggedProject(null);
    setTarget(null);
  }

  function dragStart(event: DragEvent, project: ProjectSummary) {
    event.dataTransfer.setData(projectDragType, project.id);
    event.dataTransfer.effectAllowed = 'move';
    setMoveError('');
    setDraggedProject({ id: project.id, groupId: memberships[project.id] ?? null });
  }

  async function drop(event: DragEvent, groupId: string | null) {
    const source = draggedProject;
    if (!source) return;
    event.preventDefault();
    const matches = source.id === event.dataTransfer.getData(projectDragType);
    endDrag();
    if (!matches || disabled || source.groupId === groupId) return;
    setMoving(true);
    try { await api.changeGrouping(`/${source.id}/group`, 'PUT', { groupId, previousGroupId: source.groupId }); }
    catch (cause) { setMoveError(cause instanceof Error ? cause.message : 'The project could not be moved.'); }
    finally { setMoving(false); }
  }

  function dropTarget(id: string) {
    return {
      'data-target': id,
      'data-project-drop-active': target === id ? true : undefined,
      onDragOver: (event: DragEvent) => {
        if (!draggedProject || disabled || !event.dataTransfer.types.includes(projectDragType)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        setTarget(id);
      },
      onDragLeave: (event: DragEvent) => {
        if (event.relatedTarget instanceof Node && event.currentTarget.contains(event.relatedTarget)) return;
        setTarget(previous => previous === id ? null : previous);
      },
      onDrop: (event: DragEvent) => void drop(event, id === ungrouped ? null : id),
    };
  }

  function projectRow(project: ProjectSummary) {
    const running = activity.has(project.id) && !project.deleting;
    const canDrag = !disabled && !project.deleting && groups.length > 0;
    return <button type="button" key={project.id} disabled={saving} className={`nav-item ${selectedId === project.id ? 'selected' : ''}`}
      aria-current={selectedId === project.id ? 'true' : undefined} aria-label={running ? `${project.name}, Session running` : undefined}
      title={running ? 'Session running' : undefined} draggable={canDrag} onDragStart={event => {
        if (canDrag) dragStart(event, project); else event.preventDefault();
      }} onDragEnd={endDrag} onClick={() => choose(project.id)}>
      <Icon name="folder" energyPulse={running} /><span>{project.name}{project.deleting ? ' · Deleting…' : ''}</span>
    </button>;
  }

  function fallbackFocus() {
    const column = navigation.current;
    if (column?.closest('[inert]')) column.closest('.workspace-navigation')?.querySelector<HTMLButtonElement>('.navigation-grip')?.focus();
    else column?.querySelector<HTMLButtonElement>('.project-new-group')?.focus();
  }

  return <nav className="nav-column" aria-label="Projects" ref={navigation}>
    <div className="nav-items project-navigation-list" aria-busy={api.loading || moving}>
      <button type="button" className="nav-item project-new project-new-group" disabled={disabled || api.loading}
        aria-haspopup="dialog" onClick={() => setEditor('create')}><span className="project-plus" aria-hidden="true">+</span><span>New Group</span></button>
      <button type="button" className="nav-item project-new" disabled={!api.token || saving}
        onClick={createProject}><span className="project-plus" aria-hidden="true">+</span><span>New Project</span></button>
      {moveError && <p className="project-nav-message project-error" role="alert">{moveError}</p>}
      {api.loading ? <p className="project-nav-message" role="status">Loading projects…</p>
        : api.error ? <><p className="project-nav-message" role="alert">{api.error}</p><button className="nav-item" onClick={() => void api.reload()}>Retry</button></>
          : <>
            {draggedProject && <div className="project-group-ungrouped nav-item" {...dropTarget(ungrouped)}>Ungrouped</div>}
            {[...groups].sort((a, b) => a.name.localeCompare(b.name, 'en', { numeric: true })).map(group =>
              <div className="project-group" key={group.id} {...dropTarget(group.id)}>
                <ProjectGroupRow group={group} edit={setEditor} disabled={disabled}>{projectsByGroup.get(group.id)?.map(projectRow)}</ProjectGroupRow>
              </div>)}
            {projectsByGroup.get(ungrouped)?.map(projectRow)}
            {api.projects.length === 0 && <p className="project-nav-message" role="status">No projects yet.</p>}
          </>}
    </div>
    {editor && <ProjectGroupDialog group={editor === 'create' ? null : editor} change={api.changeGrouping}
      close={() => setEditor(null)} fallbackFocus={fallbackFocus} />}
  </nav>;
}
