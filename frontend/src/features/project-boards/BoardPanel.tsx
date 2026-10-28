import { useEffect, useState } from 'react';
import type { BoardColumn, BoardSummary } from '../../../../shared/project-boards';
import { BoardForm, BoardOrderDialog } from './BoardForm';
import type { BoardsModel } from './useBoards';
import { useBoardChange } from './useBoardChange';
import { BoardColumnView } from './BoardColumnView';
import { ColumnForm, RemoveColumn } from './ColumnForm';
import { CardEditor } from './CardEditor';
import { projectRequestId } from '../projects/api';
import './styles.css';

export function BoardPanel({ id, token, model, creating, closeCreate, created, dirtyChanged, busyChanged }: {
  id: string; token: string; model: BoardsModel; creating: boolean; closeCreate: () => void; created: (id: string) => void;
  dirtyChanged: (value: boolean) => void; busyChanged: (value: boolean) => void;
}) {
  const [editing, setEditing] = useState<BoardSummary | null>(null), [moving, setMoving] = useState<BoardSummary | null>(null);
  const [columnEditor, setColumnEditor] = useState<BoardColumn | 'new' | null>(null), [removingColumn, setRemovingColumn] = useState<BoardColumn | null>(null);
  const [cardEditor, setCardEditor] = useState<string | null>(null), [formDirty, setFormDirty] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({}), [notice, setNotice] = useState('');
  const [focusColumn, setFocusColumn] = useState<{ id: string; revision: number } | null>(null);
  const dirty = formDirty || Object.values(drafts).some(value => !!value);
  useEffect(() => { dirtyChanged(dirty); return () => dirtyChanged(false); }, [dirty, dirtyChanged]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  useEffect(() => {
    if (!focusColumn || model.loading || !model.snapshot || model.snapshot.board.revision < focusColumn.revision) return;
    const frame = requestAnimationFrame(() => {
      if (document.activeElement === document.body) document.querySelector<HTMLElement>(`[data-column-id="${focusColumn.id}"] input`)?.focus();
      setFocusColumn(null);
    });
    return () => cancelAnimationFrame(frame);
  }, [focusColumn, model.loading, model.snapshot]);
  const control = useBoardChange(id, token, (receipt, change) => {
    setEditing(null); setMoving(null); setColumnEditor(null); setRemovingColumn(null); setCardEditor(null); setFormDirty(false); model.reload();
    if (change.kind === 'mutate' && change.body.action === 'create_card' && change.body.input.columnId) {
      const columnId = change.body.input.columnId;
      setDrafts(old => ({ ...old, [columnId]: '' }));
      if (change.boardId === model.snapshot?.board.id) setFocusColumn({ id: columnId, revision: receipt.revision ?? 0 });
    }
    if (receipt.deleted && receipt.cardId) {
      const columnId = model.snapshot?.cards.find(card => card.id === receipt.cardId)?.columnId;
      if (columnId) setFocusColumn({ id: columnId, revision: receipt.revision ?? 0 });
    }
    if (receipt.deleted && receipt.columnId) {
      const columnId = receipt.columnId;
      setDrafts(old => { const next = { ...old }; delete next[columnId]; return next; });
    }
    setNotice(receipt.deleted ? receipt.cardId ? 'Card deleted.' : `Column removed. ${receipt.movedCards ?? 0} cards preserved.` : 'Board change saved.');
    if (change.kind === 'create' && receipt.boardId) created(receipt.boardId);
  }, busyChanged, model.reload);
  const data = model.snapshot, locked = control.busy || !!control.pending;
  return <section className="project-boards" aria-label="Project boards">
    <header className="board-toolbar"><div><h2>{data?.board.name ?? 'Boards'}</h2>{data?.board.description && <p className="board-description">{data.board.description}</p>}</div>
      <div className="board-actions">{data && <><button type="button" disabled={locked || !!model.error} onClick={() => setEditing(data.board)}>Edit Board</button>
        <button type="button" disabled={locked || !!model.error || (model.listing?.boards.length ?? 0) < 2} onClick={() => setMoving(data.board)}>Move Board</button>
        <button type="button" disabled={locked || !!model.error || data.columns.length >= 32} onClick={() => setColumnEditor('new')}>Add column</button></>}
        <button type="button" disabled={control.busy} onClick={model.reload}>Refresh</button></div></header>
    {model.loading && <p className="project-message" role="status">Loading boards…</p>}
    {(model.error || control.error) && <p className="project-error" role="alert">{model.error || control.error}</p>}
    {notice && <p className="project-message" role="status">{notice}</p>}
    {control.pending && !creating && !editing && !columnEditor && !cardEditor && <div className="board-recovery"><p>The original Board change is unconfirmed.</p><button type="button" disabled={control.busy} onClick={() => void control.check()}>Check original change</button>
      <button type="button" disabled={control.busy} onClick={() => void control.retry()}>Retry original change</button></div>}
    {!model.loading && !data && !model.error && <p className="board-empty">No boards yet. Use New Board to organize this project’s work.</p>}
    {data && <div className="board-canvas" aria-label="Board columns" tabIndex={0}>{data.columns.map(column => <BoardColumnView column={column} key={column.id}
      cards={data.cards.filter(card => card.columnId === column.id)} title={drafts[column.id] ?? ''} titleChanged={value => setDrafts(old => ({ ...old, [column.id]: value }))}
      locked={locked || !!model.error || model.loading} minimum={data.columns.length < 2} edit={() => setColumnEditor(column)} remove={() => setRemovingColumn(column)} open={setCardEditor}
      add={() => void control.perform({ kind: 'mutate', boardId: data.board.id, body: { requestId: projectRequestId(), expectedRevision: data.board.revision, action: 'create_card', input: { columnId: column.id, title: drafts[column.id] } } })} />)}</div>}
    {creating && model.listing && <BoardForm listing={model.listing} control={control} close={closeCreate} dirtyChanged={setFormDirty} />}
    {editing && model.listing && <BoardForm initial={editing} current={data?.board} listing={model.listing} control={control} close={() => setEditing(null)} dirtyChanged={setFormDirty} />}
    {moving && model.listing && <BoardOrderDialog board={moving} listing={model.listing} control={control} close={() => setMoving(null)} />}
    {columnEditor && data && <ColumnForm initial={columnEditor === 'new' ? undefined : columnEditor} data={data} control={control} close={() => setColumnEditor(null)} dirtyChanged={setFormDirty} />}
    {removingColumn && data && <RemoveColumn column={removingColumn} data={data} draftTitle={drafts[removingColumn.id]} control={control} close={() => setRemovingColumn(null)} />}
    {cardEditor && data && <CardEditor key={cardEditor} projectId={id} boardId={data.board.id} cardId={cardEditor} boardRevision={data.board.revision} control={control} close={() => setCardEditor(null)} dirtyChanged={setFormDirty} />}
  </section>;
}
