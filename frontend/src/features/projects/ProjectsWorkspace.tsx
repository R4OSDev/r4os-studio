import { Icon } from '../../app/Icon';
import { useProjects } from './useProjects';
import './styles.css';

export function ProjectsWorkspace({ selectedId, select }: {
  selectedId: string | null; select: (id: string) => void;
}) {
  const { projects, loading, error } = useProjects();
  const selected = projects.find((project) => project.id === selectedId);

  return <>
    <aside className="navigation" aria-label="Projects navigation">
      <nav className="nav-column" aria-label="Projects">
        <div className="column-heading">Projects</div>
        <div className="nav-items" aria-busy={loading}>
          {loading ? <p className="project-nav-message" role="status">Loading projects…</p>
            : error ? <p className="project-nav-message" role="alert">{error}</p>
              : projects.length === 0 ? <p className="project-nav-message" role="status">No projects yet.</p>
                : projects.map((project) => <button type="button" key={project.id}
                  className={`nav-item ${selectedId === project.id ? 'selected' : ''}`}
                  aria-current={selectedId === project.id ? 'true' : undefined}
                  onClick={() => select(project.id)}>
                  <Icon name="folder" /><span>{project.name}</span>
                </button>)}
        </div>
      </nav>
      <div className="nav-column" aria-hidden="true" />
      <div className="nav-column" aria-hidden="true" />
    </aside>
    <main className="main-area" aria-label="Project content">
      {selected && <div className="page-heading"><h1>{selected.name}</h1><span className="page-rule" /></div>}
    </main>
  </>;
}
