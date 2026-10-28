import type { BoardsModel } from './useBoards';

export function BoardNavigation({ model, disabled, choose, create }: { model: BoardsModel; disabled: boolean; choose: (id: string) => void; create: () => void }) {
  return <nav className="nav-column" aria-label="Project boards"><div className="column-heading" aria-hidden="true" />
    <div className="nav-items"><button type="button" className="nav-item project-new" disabled={disabled || !model.listing} onClick={create}>
      <span className="project-plus" aria-hidden="true">+</span><span>New Board</span></button>
      <label className="board-archive-toggle"><input type="checkbox" checked={model.showArchived} onChange={event => model.setShowArchived(event.target.checked)} />Show archived</label>
      {model.loading && !model.listing ? <p className="project-nav-message" role="status">Loading boards…</p> : model.error && !model.listing ? <p className="project-nav-message" role="alert">{model.error}</p>
        : model.listing?.boards.filter(board => model.showArchived || !board.archived).map(board => <button key={board.id} type="button" className={'nav-item ' + (model.selectedId === board.id ? 'selected' : '')}
          disabled={disabled} aria-current={model.selectedId === board.id ? 'page' : undefined} title={board.name} onClick={() => choose(board.id)}><span>{board.name}{board.archived && <small className="board-archived-text">Archived</small>}</span></button>)}
    </div>
  </nav>;
}
