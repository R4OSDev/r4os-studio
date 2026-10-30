import type { RoadmapModel } from './useRoadmap';
import { versionStatusLabels } from './model';

export function RoadmapNavigation({ model, selected, choose, create, disabled }: {
  model: RoadmapModel; selected?: string; choose: (id?: string) => void; create: () => void; disabled: boolean;
}) {
  const state = model.overview;
  return <nav className="nav-column" aria-label="Project roadmap versions">
    <div className="column-heading" aria-hidden="true" />
    <div className="nav-items">
      <button className={`nav-item ${!selected ? 'selected' : ''}`} type="button" disabled={disabled}
        aria-current={!selected ? 'page' : undefined} onClick={() => choose()}>Overview</button>
      <button className="nav-item project-new" type="button" disabled={disabled || !state?.exists}
        onClick={create}><span className="project-plus" aria-hidden="true">+</span><span>New Version</span></button>
      {model.loading && <p className="project-nav-message" role="status">Loading roadmap…</p>}
      {state?.exists && state.versions.items.map((version) => <button key={version.id} type="button"
        className={`nav-item roadmap-version-link ${selected === version.id ? 'selected' : ''}`} disabled={disabled}
        aria-current={selected === version.id ? 'page' : undefined} title={`${version.number} ${version.title}`} aria-label={`${version.number} ${version.title}, ${versionStatusLabels[version.status]}${state.roadmap.currentVersionId===version.id?', Current':''}`} onClick={() => choose(version.id)}>
        <span><span className="roadmap-version-line"><strong>{version.number}</strong><span className="roadmap-version-name">{version.title}</span></span>
          <small>{versionStatusLabels[version.status]}{state.roadmap.currentVersionId === version.id ? ' · Current' : ''}</small></span>
      </button>)}
      {state?.exists && state.versions.nextCursor && <button type="button" className="nav-item" disabled={disabled || model.paging}
        onClick={() => void model.more()}>{model.paging ? 'Loading…' : 'More versions'}</button>}
    </div>
  </nav>;
}
