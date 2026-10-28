import { useEffect, useState } from 'react';
import type { BoardColumn, BoardSnapshot } from '../../../../shared/project-boards';
import { projectRequestId } from '../projects/api';
import { BoardDialog } from './BoardDialog';
import type { useBoardChange } from './useBoardChange';
type Control = ReturnType<typeof useBoardChange>;

export function ColumnForm({ initial, data, control, close, dirtyChanged }: { initial?: BoardColumn; data: BoardSnapshot; control: Control; close: () => void; dirtyChanged: (value: boolean) => void }) {
  const [baseline, setBaseline] = useState({ title: initial?.title ?? '', revision: initial?.revision ?? 0, boardRevision: data.board.revision });
  const [title, setTitle] = useState(baseline.title), current = initial ? data.columns.find(column => column.id === initial.id) : null;
  const locked = control.busy || !!control.pending, conflict = data.board.revision !== baseline.boardRevision || (!!initial && !current);
  useEffect(() => { dirtyChanged(title !== baseline.title); return () => dirtyChanged(false); }, [title, baseline.title, dirtyChanged]);
  return <BoardDialog title={initial ? 'Edit column' : 'New column'} close={() => { if (!control.busy) close(); }}><form onSubmit={event => {
    event.preventDefault(); if (locked || conflict || !title.trim() || Array.from(title.trim()).length > 120) return;
    void control.perform({ kind: 'mutate', boardId: data.board.id, body: { requestId: projectRequestId(), expectedRevision: baseline.boardRevision,
      action: initial ? 'update_column' : 'create_column', input: { title, ...(initial ? { columnId: initial.id, expectedColumnRevision: baseline.revision } : {}) } } });
  }}><fieldset className="project-fields" disabled={locked}><label className="project-field">Title<input value={title} maxLength={480} autoComplete="off" onChange={event => setTitle(event.target.value)} /></label></fieldset>
    {conflict && <div className="board-conflict" role="status"><p>This Board changed. Your column draft was preserved.</p>
      {current && <p className="board-current-text">Saved: {current.title}</p>}
      {(!initial || current) && <button type="button" disabled={locked} onClick={() => {
        if (current && title === baseline.title) setTitle(current.title);
        setBaseline({ title: current?.title ?? '', revision: current?.revision ?? 0, boardRevision: data.board.revision });
      }}>Review saved changes</button>}</div>}
    {control.error && <p className="project-dialog-error" role="alert">{control.error}</p>}
    {control.pending && <div className="board-conflict"><button type="button" disabled={control.busy} onClick={() => void control.check()}>Check original change</button><button type="button" disabled={control.busy} onClick={() => void control.retry()}>Retry original change</button></div>}
    <footer className="project-actions"><button type="button" disabled={control.busy} onClick={close}>Cancel</button><button className="project-primary" disabled={locked || conflict || !title.trim() || Array.from(title.trim()).length > 120 || (!!initial && title === baseline.title)}>Save</button></footer>
  </form></BoardDialog>;
}

export function RemoveColumn({ column, data, draftTitle, control, close }: { column: BoardColumn; data: BoardSnapshot; draftTitle?: string; control: Control; close: () => void }) {
  const [original] = useState({ revision: data.board.revision, columnRevision: column.revision }), [target, setTarget] = useState('');
  const count = data.cards.filter(card => card.columnId === column.id).length, locked = control.busy || !!control.pending;
  const conflict = original.revision !== data.board.revision;
  return <BoardDialog title="Remove column" close={() => { if (!control.busy) close(); }}><form onSubmit={event => {
    event.preventDefault(); if (locked || conflict || (count > 0 && !target)) return;
    void control.perform({ kind: 'mutate', boardId: data.board.id, body: { requestId: projectRequestId(), expectedRevision: original.revision,
      action: 'delete_column', input: { columnId: column.id, expectedColumnRevision: original.columnRevision, confirm: true, ...(target ? { targetColumnId: target } : {}) } } });
  }}><div className="board-dialog-body"><p>Remove <strong>{column.title}</strong>?</p>
    {draftTitle && <p>The unsaved card title “{draftTitle}” will be discarded.</p>}
    {count > 0 ? <><p>Move all {count} cards, including archived cards, to another column.</p><label className="project-field">Move cards to<select value={target} disabled={locked} onChange={event => setTarget(event.target.value)}><option value="">Choose a column</option>
      {data.columns.filter(value => value.id !== column.id).map(value => <option key={value.id} value={value.id}>{value.title}</option>)}</select></label></> : <p>This column is empty.</p>}</div>
    {conflict && <p className="project-dialog-status">This Board changed. Cancel and review the current column before removing it.</p>}
    {control.error && <p className="project-dialog-error" role="alert">{control.error}</p>}
    <footer className="project-actions"><button type="button" disabled={control.busy} onClick={close}>Cancel</button><button className="board-danger" disabled={locked || conflict || data.columns.length < 2 || (count > 0 && !target)}>Remove column</button></footer>
  </form></BoardDialog>;
}
