import { useEffect, useState } from 'react';
import type { BoardSnapshot } from '../../../../shared/project-boards';
import { projectRequestId } from '../projects/api';
import { BoardDialog } from './BoardDialog';
import type { useBoardChange } from './useBoardChange';

export type MovingEntry = { kind: 'card' | 'column'; id: string };
export function MoveEntryDialog({ entry, data, control, close, dirtyChanged }: {
  entry: MovingEntry; data: BoardSnapshot; control: ReturnType<typeof useBoardChange>; close: () => void; dirtyChanged: (value: boolean) => void;
}) {
  const [baseline, setBaseline] = useState(data);
  const original = entry.kind === 'card' ? baseline.cards.find(row => row.id === entry.id) : baseline.columns.find(row => row.id === entry.id);
  const [target, setTarget] = useState(original && 'columnId' in original ? original.columnId : '');
  const [position, setPosition] = useState(original?.position ?? 0);
  const locked = control.busy || !!control.pending, conflict = data.board.revision !== baseline.board.revision;
  const rows = entry.kind === 'card' ? baseline.cards.filter(row => row.columnId === target && row.id !== entry.id) : baseline.columns.filter(row => row.id !== entry.id);
  const changed = !!original && (position !== original.position || ('columnId' in original && target !== original.columnId));
  useEffect(() => { dirtyChanged(changed); return () => dirtyChanged(false); }, [changed, dirtyChanged]);
  function submit() {
    if (!original || locked || conflict || !changed || position > rows.length) return;
    void control.perform({ kind: 'mutate', boardId: baseline.board.id, body: { requestId: projectRequestId(), expectedRevision: baseline.board.revision,
      expectedOrderRevision: baseline.board.orderRevision, action: entry.kind === 'card' ? 'move_card' : 'move_column',
      input: 'columnId' in original ? { cardId: original.id, expectedCardRevision: original.revision, sourceColumnId: original.columnId, targetColumnId: target, position }
        : { columnId: original.id, expectedColumnRevision: original.revision, position } } });
  }
  return <BoardDialog title={entry.kind === 'card' ? 'Move card' : 'Move column'} close={() => { if (!control.busy) close(); }}>
    <form onSubmit={event => { event.preventDefault(); submit(); }}><fieldset className="project-fields" disabled={locked || !original}>
      <p className="board-current-text">{original?.title ?? 'This item is no longer available.'}</p>
      {entry.kind === 'card' && <label className="project-field">Target column<select value={target} onChange={event => { setTarget(event.target.value); setPosition(0); }}>
        {baseline.columns.map((column, index) => <option key={column.id} value={column.id}>{index + 1}. {column.title}</option>)}
      </select></label>}
      <label className="project-field">Position<select value={Math.min(position, rows.length)} onChange={event => setPosition(Number(event.target.value))}>
        {Array.from({ length: rows.length + 1 }, (_, index) => <option key={index} value={index}>{index + 1}{index === 0 ? ' — first' : index === rows.length ? ' — last' : ''}</option>)}
      </select></label><p className="project-help">{entry.kind === 'card' ? 'Positions include every card, including hidden and archived cards.' : 'Choose the column’s final position.'}</p>
    </fieldset>
      {conflict && <div className="board-conflict" role="status"><p>The Board changed. Review the current order before moving.</p>
        <button type="button" disabled={locked} onClick={() => {
          const current = entry.kind === 'card' ? data.cards.find(row => row.id === entry.id) : data.columns.find(row => row.id === entry.id);
          const nextTarget = data.columns.some(column => column.id === target) ? target : current && 'columnId' in current ? current.columnId : '';
          setTarget(nextTarget); setPosition(Math.min(position, entry.kind === 'card' ? data.cards.filter(row => row.columnId === nextTarget && row.id !== entry.id).length : data.columns.length - 1)); setBaseline(data);
        }}>Review current order</button></div>}
      {control.error && <p className="project-dialog-error" role="alert">{control.error}</p>}
      {control.pending && <div className="board-conflict"><button type="button" disabled={control.busy} onClick={() => void control.check()}>Check original change</button>
        <button type="button" disabled={control.busy} onClick={() => void control.retry()}>Retry original change</button></div>}
      <footer className="project-actions"><button type="button" disabled={control.busy} onClick={close}>Cancel</button><button className="project-primary" disabled={locked || conflict || !original || !changed}>Move</button></footer>
    </form></BoardDialog>;
}
