import { useState } from 'react';
import type { BoardSummary } from '../../../../shared/project-boards';
import { BoardForm, BoardOrderDialog } from './BoardForm';
import type { BoardsModel } from './useBoards';
import { useBoardChange } from './useBoardChange';
import './styles.css';

export function BoardPanel({ id, token, model, creating, closeCreate, created, dirtyChanged, busyChanged }: {
  id: string; token: string; model: BoardsModel; creating: boolean; closeCreate: () => void; created: (id: string) => void;
  dirtyChanged: (value: boolean) => void; busyChanged: (value: boolean) => void;
}) {
  const [editing, setEditing] = useState<BoardSummary | null>(null), [moving, setMoving] = useState<BoardSummary | null>(null);
  const control = useBoardChange(id, token, (receipt, change) => {
    setEditing(null); setMoving(null); dirtyChanged(false); model.reload();
    if (change.kind === 'create' && receipt.boardId) created(receipt.boardId);
  }, busyChanged, model.reload);
  const data = model.snapshot, locked = control.busy || !!control.pending;
  return <section className="project-boards" aria-label="Project boards">
    <header className="board-toolbar"><div><h2>{data?.board.name ?? 'Boards'}</h2>{data?.board.description && <p className="board-description">{data.board.description}</p>}</div>
      <div className="board-actions">{data && <><button type="button" disabled={locked || !!model.error} onClick={() => setEditing(data.board)}>Edit Board</button>
        <button type="button" disabled={locked || !!model.error || (model.listing?.boards.length ?? 0) < 2} onClick={() => setMoving(data.board)}>Move Board</button></>}
        <button type="button" disabled={control.busy} onClick={model.reload}>Refresh</button></div></header>
    {model.loading && <p className="project-message" role="status">Loading boards…</p>}
    {(model.error || control.error) && <p className="project-error" role="alert">{model.error || control.error}</p>}
    {control.pending && !creating && !editing && <div className="board-recovery"><p>The original Board change is unconfirmed.</p><button type="button" disabled={control.busy} onClick={() => void control.check()}>Check original change</button>
      <button type="button" disabled={control.busy} onClick={() => void control.retry()}>Retry original change</button></div>}
    {!model.loading && !data && !model.error && <p className="board-empty">No boards yet. Use New Board to organize this project’s work.</p>}
    {data && <div className="board-canvas" aria-label="Board columns" tabIndex={0}>{data.columns.map(column => <section className="board-column" key={column.id} aria-label={column.title}>
      <header><h3>{column.title}</h3><span className="board-count" aria-label={`${column.cardCount} cards`}>{column.cardCount}</span></header><p className="board-empty">No cards yet.</p>
    </section>)}</div>}
    {creating && model.listing && <BoardForm listing={model.listing} control={control} close={closeCreate} dirtyChanged={dirtyChanged} />}
    {editing && model.listing && <BoardForm initial={editing} current={data?.board} listing={model.listing} control={control} close={() => setEditing(null)} dirtyChanged={dirtyChanged} />}
    {moving && model.listing && <BoardOrderDialog board={moving} listing={model.listing} control={control} close={() => setMoving(null)} />}
  </section>;
}
