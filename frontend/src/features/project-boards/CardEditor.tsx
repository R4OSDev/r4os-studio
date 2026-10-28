import { useEffect, useState } from 'react';
import type { BoardCard, BoardLabel } from '../../../../shared/project-boards';
import { projectRequestId } from '../projects/api';
import { loadCard } from './api';
import { BoardDialog } from './BoardDialog';
import { CardMetadataFields, cardDraft, type CardDraft } from './CardMetadataFields';
import type { useBoardChange } from './useBoardChange';
type Control = ReturnType<typeof useBoardChange>;
type Read = { card: BoardCard; boardRevision: number };

export function CardEditor({ projectId, boardId, cardId, boardRevision, labels, control, close, dirtyChanged }: {
  projectId: string; boardId: string; cardId: string; boardRevision: number; labels: BoardLabel[]; control: Control; close: () => void; dirtyChanged: (value: boolean) => void;
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
  return current ? <CardForm current={current} labels={labels} error={error} control={control} close={close} dirtyChanged={dirtyChanged} />
    : <BoardDialog title="Card details" close={close}><div className="board-dialog-body"><p role={error ? 'alert' : 'status'}>{error || 'Loading card…'}</p></div><footer className="project-actions"><button type="button" onClick={close}>Cancel</button></footer></BoardDialog>;
}
function CardForm({ current, labels, error, control, close, dirtyChanged }: { current: Read; labels: BoardLabel[]; error: string; control: Control; close: () => void; dirtyChanged: (value: boolean) => void }) {
  const [baseline, setBaseline] = useState(current), [draft, setDraft] = useState(() => cardDraft(current.card));
  const { title, description } = draft;
  const fields = Object.keys(draft) as (keyof CardDraft)[];
  const changed = (key: keyof CardDraft) => JSON.stringify(draft[key]) !== JSON.stringify(baseline.card[key]);
  const [deleting, setDeleting] = useState(false);
  const dirty = fields.some(changed), locked = control.busy || !!control.pending;
  const conflict = current.boardRevision !== baseline.boardRevision || current.card.revision !== baseline.card.revision;
  useEffect(() => { dirtyChanged(dirty); return () => dirtyChanged(false); }, [dirty, dirtyChanged]);
  const invalid = !title.trim() || Array.from(title.trim()).length > 240 || Array.from(description).length > 16000 || draft.checklist.some(item => !item.text.trim() || Array.from(item.text.trim()).length > 240) || draft.labelIds.some(id => !labels.some(label => label.id === id));
  function submit(remove = false) {
    if (locked || conflict || !!error || (!remove && invalid)) return;
    void control.perform({ kind: 'mutate', boardId: current.card.boardId, body: { requestId: projectRequestId(), expectedRevision: baseline.boardRevision,
      action: remove ? 'delete_card' : 'update_card', input: { cardId: current.card.id, expectedCardRevision: baseline.card.revision,
        ...(remove ? { confirm: true as const } : { ...Object.fromEntries(fields.filter(changed).map(key => [key, key === 'checklist' ? draft.checklist.map(({ id, text, checked, revision }) => ({ id, text, checked, revision })) : draft[key]])) }) } } });
  }
  return <BoardDialog title="Card details" close={() => { if (!control.busy) close(); }}><form onSubmit={event => { event.preventDefault(); submit(); }}>
    <fieldset className="project-fields" disabled={locked || deleting}><label className="project-field">Title<input value={title} maxLength={960} onChange={event => { const title = event.target.value; setDraft(old => ({ ...old, title })); }} /></label>
      <label className="project-field">Description<textarea rows={6} value={description} maxLength={64000} onChange={event => { const description = event.target.value; setDraft(old => ({ ...old, description })); }} /></label><CardMetadataFields draft={draft} setDraft={setDraft} labels={labels} /></fieldset>
    {conflict && <div className="board-conflict" role="status"><p>This card or Board changed. Your draft was preserved.</p><p className="board-current-text">Saved: {current.card.title}{'\n' + current.card.description}{'\nPriority: ' + current.card.priority + ' · Due: ' + (current.card.dueDate ?? 'none')}{'\nLabels: ' + labels.filter(label => current.card.labelIds.includes(label.id)).map(label => label.name).join(', ')}{'\nChecklist: ' + current.card.checklist.map(item => (item.checked ? '☑ ' : '☐ ') + item.text).join(' · ')}</p>
      <button type="button" disabled={locked} onClick={() => {
        const saved = cardDraft(current.card), next = { ...draft };
        for (const key of fields) if (!changed(key)) Object.assign(next, { [key]: saved[key] });
        if (changed('labelIds')) next.labelIds = next.labelIds.filter(id => labels.some(label => label.id === id));
        if (changed('checklist')) {
          next.checklist = draft.checklist.map(item => {
            const previous = baseline.card.checklist.find(row => row.id === item.id), live = current.card.checklist.find(row => row.id === item.id);
            return previous && live ? { ...item, revision: live.revision, text: item.text === previous.text ? live.text : item.text, checked: item.checked === previous.checked ? live.checked : item.checked } : item;
          });
          next.checklist.push(...current.card.checklist.filter(item => !baseline.card.checklist.some(row => row.id === item.id) && !next.checklist.some(row => row.id === item.id)));
        }
        setDraft(next); setBaseline(current);
      }}>Review saved changes</button></div>}
    {(error || control.error) && <p className="project-dialog-error" role="alert">{error || control.error}</p>}
    {control.pending && <div className="board-conflict"><button type="button" disabled={control.busy} onClick={() => void control.check()}>Check original change</button><button type="button" disabled={control.busy} onClick={() => void control.retry()}>Retry original change</button></div>}
    {deleting && <div className="board-conflict" role="group" aria-label="Confirm card deletion"><p>Permanently delete <strong>{current.card.title}</strong> and its details?</p>
      <button type="button" disabled={locked} onClick={() => setDeleting(false)}>Keep card</button><button type="button" className="board-danger" disabled={locked || conflict || !!error} onClick={() => submit(true)}>Delete permanently</button></div>}
    <footer className="project-actions"><button type="button" className="board-danger" disabled={locked || !!error} onClick={() => setDeleting(true)}>Delete card</button>
      <button type="button" disabled={control.busy} onClick={close}>Cancel</button><button className="project-primary" disabled={locked || deleting || conflict || invalid || !dirty || !!error}>Save</button></footer>
  </form></BoardDialog>;
}
