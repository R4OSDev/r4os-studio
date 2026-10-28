import { useEffect, useState } from 'react';
import type { BoardCard } from '../../../../shared/project-boards';
import { projectRequestId } from '../projects/api';
import { loadCard } from './api';
import { BoardDialog } from './BoardDialog';
import type { useBoardChange } from './useBoardChange';
type Control = ReturnType<typeof useBoardChange>;
type Read = { card: BoardCard; boardRevision: number };

export function CardEditor({ projectId, boardId, cardId, boardRevision, control, close, dirtyChanged }: {
  projectId: string; boardId: string; cardId: string; boardRevision: number; control: Control; close: () => void; dirtyChanged: (value: boolean) => void;
}) {
  const [current, setCurrent] = useState<Read | null>(null), [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    void loadCard(projectId, boardId, cardId, controller.signal).then(value => {
      if (controller.signal.aborted) return;
      if (value.card.id !== cardId || value.card.boardId !== boardId) throw new Error('The card reply belongs to another Board.');
      setCurrent(value); setError('');
    }).catch((failure: Error) => { if (!controller.signal.aborted) setError(failure.message); });
    return () => controller.abort();
  }, [projectId, boardId, cardId, boardRevision]);
  return current ? <CardForm current={current} error={error} control={control} close={close} dirtyChanged={dirtyChanged} />
    : <BoardDialog title="Card details" close={close}><div className="board-dialog-body"><p role={error ? 'alert' : 'status'}>{error || 'Loading card…'}</p></div><footer className="project-actions"><button type="button" onClick={close}>Cancel</button></footer></BoardDialog>;
}
function CardForm({ current, error, control, close, dirtyChanged }: { current: Read; error: string; control: Control; close: () => void; dirtyChanged: (value: boolean) => void }) {
  const [baseline, setBaseline] = useState(current), [title, setTitle] = useState(current.card.title), [description, setDescription] = useState(current.card.description);
  const [deleting, setDeleting] = useState(false);
  const dirty = title !== baseline.card.title || description !== baseline.card.description, locked = control.busy || !!control.pending;
  const conflict = current.boardRevision !== baseline.boardRevision || current.card.revision !== baseline.card.revision;
  useEffect(() => { dirtyChanged(dirty); return () => dirtyChanged(false); }, [dirty, dirtyChanged]);
  const invalid = !title.trim() || Array.from(title.trim()).length > 240 || Array.from(description).length > 16000;
  function submit(remove = false) {
    if (locked || conflict || !!error || (!remove && invalid)) return;
    void control.perform({ kind: 'mutate', boardId: current.card.boardId, body: { requestId: projectRequestId(), expectedRevision: baseline.boardRevision,
      action: remove ? 'delete_card' : 'update_card', input: { cardId: current.card.id, expectedCardRevision: baseline.card.revision,
        ...(remove ? { confirm: true as const } : { ...(title !== baseline.card.title ? { title } : {}), ...(description !== baseline.card.description ? { description } : {}) }) } } });
  }
  return <BoardDialog title="Card details" close={() => { if (!control.busy) close(); }}><form onSubmit={event => { event.preventDefault(); submit(); }}>
    <fieldset className="project-fields" disabled={locked || deleting}><label className="project-field">Title<input value={title} maxLength={960} onChange={event => setTitle(event.target.value)} /></label>
      <label className="project-field">Description<textarea rows={6} value={description} maxLength={64000} onChange={event => setDescription(event.target.value)} /></label></fieldset>
    {conflict && <div className="board-conflict" role="status"><p>This card or Board changed. Your draft was preserved.</p><p className="board-current-text">Saved: {current.card.title}{current.card.description ? '\n' + current.card.description : ''}</p>
      <button type="button" disabled={locked} onClick={() => {
        if (title === baseline.card.title) setTitle(current.card.title);
        if (description === baseline.card.description) setDescription(current.card.description);
        setBaseline(current);
      }}>Review saved changes</button></div>}
    {(error || control.error) && <p className="project-dialog-error" role="alert">{error || control.error}</p>}
    {control.pending && <div className="board-conflict"><button type="button" disabled={control.busy} onClick={() => void control.check()}>Check original change</button><button type="button" disabled={control.busy} onClick={() => void control.retry()}>Retry original change</button></div>}
    {deleting && <div className="board-conflict" role="group" aria-label="Confirm card deletion"><p>Permanently delete <strong>{current.card.title}</strong> and its details?</p>
      <button type="button" disabled={locked} onClick={() => setDeleting(false)}>Keep card</button><button type="button" className="board-danger" disabled={locked || conflict || !!error} onClick={() => submit(true)}>Delete permanently</button></div>}
    <footer className="project-actions"><button type="button" className="board-danger" disabled={locked || !!error} onClick={() => setDeleting(true)}>Delete card</button>
      <button type="button" disabled={control.busy} onClick={close}>Cancel</button><button className="project-primary" disabled={locked || deleting || conflict || invalid || !dirty || !!error}>Save</button></footer>
  </form></BoardDialog>;
}
