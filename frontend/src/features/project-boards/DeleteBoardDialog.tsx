import { useState } from 'react';
import type { BoardSnapshot } from '../../../../shared/project-boards';
import { BoardDialog } from './BoardDialog';
import { projectRequestId } from '../projects/api';
import type { useBoardChange } from './useBoardChange';
export function DeleteBoardDialog({ data, control, close }: { data: BoardSnapshot; control: ReturnType<typeof useBoardChange>; close: () => void }) {
  const [baseline] = useState(data), conflict = baseline.board.revision !== data.board.revision, locked = control.busy || !!control.pending;
  return <BoardDialog title="Delete Board" close={() => { if (!control.busy) close(); }}><div className="board-dialog-body">
    <p>Permanently delete <strong>{baseline.board.name}</strong>?</p><p>This removes its {baseline.columns.length} columns, {baseline.cards.length} cards (including archived cards), {baseline.labels.length} labels and {baseline.cards.reduce((sum, card) => sum + card.checklistCount, 0)} checklist items.</p>
    <p>This cannot be undone. Other Boards and project files are kept.</p>
    {conflict && <p role="alert">The Board changed. Cancel and reopen Delete Board to review its current contents.</p>}
    {control.error && <p className="project-error" role="alert">{control.error}</p>}
    {control.pending && <div className="board-conflict"><button type="button" disabled={control.busy} onClick={() => void control.check()}>Check original change</button><button type="button" disabled={control.busy} onClick={() => void control.retry()}>Retry original change</button></div>}
  </div><footer className="project-actions"><button type="button" disabled={control.busy} onClick={close}>Keep Board</button>
    <button type="button" className="board-danger" disabled={locked || conflict} onClick={() => void control.perform({ kind: 'mutate', boardId: baseline.board.id, body: { requestId: projectRequestId(), expectedRevision: baseline.board.revision, action: 'delete_board', input: { confirm: true } } })}>Delete permanently</button>
  </footer></BoardDialog>;
}
