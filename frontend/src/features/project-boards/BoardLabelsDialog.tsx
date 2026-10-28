import { useEffect, useState } from 'react';
import type { BoardColor, BoardLabel, BoardSnapshot } from '../../../../shared/project-boards';
import { BoardDialog } from './BoardDialog';
import { projectRequestId } from '../projects/api';
import type { useBoardChange } from './useBoardChange';
const colors: BoardColor[] = ['purple', 'blue', 'green', 'yellow', 'orange', 'pink', 'gray'];
export function BoardLabelsDialog({ data, control, close, dirtyChanged }: { data: BoardSnapshot; control: ReturnType<typeof useBoardChange>; close: () => void; dirtyChanged: (value: boolean) => void }) {
  const [selected, setSelected] = useState<BoardLabel | 'new' | null>(null);
  if (selected) return <LabelForm key={selected === 'new' ? 'new' : selected.id} data={data} initial={selected} control={control} close={close} dirtyChanged={dirtyChanged} />;
  return <BoardDialog title="Manage labels" close={close}><div className="board-dialog-body board-label-list">
    {data.labels.map(label => <button type="button" key={label.id} onClick={() => setSelected(label)}><span className="board-label" data-color={label.color}>{label.name}</span><span>Edit</span></button>)}
    {!data.labels.length && <p>No labels yet.</p>}<button type="button" disabled={control.busy || !!control.pending || data.labels.length >= 64} onClick={() => setSelected('new')}>New label</button>
  </div><footer className="project-actions"><button type="button" onClick={close}>Close</button></footer></BoardDialog>;
}
function LabelForm({ data, initial, control, close, dirtyChanged }: { data: BoardSnapshot; initial: BoardLabel | 'new'; control: ReturnType<typeof useBoardChange>; close: () => void; dirtyChanged: (value: boolean) => void }) {
  const [baseline, setBaseline] = useState({ boardRevision: data.board.revision, label: initial === 'new' ? null : initial });
  const [name, setName] = useState(baseline.label?.name ?? ''), [color, setColor] = useState<BoardColor>(baseline.label?.color ?? 'purple'), [removing, setRemoving] = useState(false);
  const dirty = name !== (baseline.label?.name ?? '') || color !== (baseline.label?.color ?? 'purple');
  useEffect(() => { dirtyChanged(dirty); return () => dirtyChanged(false); }, [dirty, dirtyChanged]);
  const locked = control.busy || !!control.pending, conflict = baseline.boardRevision !== data.board.revision;
  const current = baseline.label ? data.labels.find(row => row.id === baseline.label!.id) : null, valid = !!name.trim() && Array.from(name.trim()).length <= 64;
  function submit(remove = false) {
    if (locked || conflict || (!remove && !valid)) return;
    void control.perform({ kind: 'mutate', boardId: data.board.id, body: { requestId: projectRequestId(), expectedRevision: baseline.boardRevision,
      action: remove ? 'delete_label' : baseline.label ? 'update_label' : 'create_label', input: { ...(baseline.label ? { labelId: baseline.label.id, expectedLabelRevision: baseline.label.revision } : {}),
        ...(remove ? { confirm: true as const } : { name, color }) } } });
  }
  return <BoardDialog title={baseline.label ? 'Edit label' : 'New label'} close={() => { if (!control.busy) close(); }}><form onSubmit={event => { event.preventDefault(); submit(); }}>
    <fieldset className="project-fields" disabled={locked || removing}><label className="project-field">Name<input maxLength={256} value={name} onChange={event => setName(event.target.value)} /></label>
      <label className="project-field">Color<select value={color} onChange={event => setColor(event.target.value as BoardColor)}>{colors.map(value => <option key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</option>)}</select></label>
      <span className="board-label" data-color={color}>{name || 'Label'}</span></fieldset>
    {conflict && <div className="board-conflict"><p>This Board changed. Your label draft was preserved.</p><button type="button" disabled={locked || (!!baseline.label && !current)} onClick={() => {
      if (current) { if (name === baseline.label?.name) setName(current.name); if (color === baseline.label?.color) setColor(current.color); }
      setBaseline({ boardRevision: data.board.revision, label: current ?? null });
    }}>Review saved changes</button>{baseline.label && !current && <p>This label has been removed.</p>}</div>}
    {removing && <div className="board-conflict"><p>Remove <strong>{baseline.label?.name}</strong> from {data.cards.filter(row => row.labelIds.includes(baseline.label!.id)).length} cards? The cards and their details are kept.</p>
      <button type="button" disabled={locked} onClick={() => setRemoving(false)}>Keep label</button><button type="button" className="board-danger" disabled={locked || conflict} onClick={() => submit(true)}>Remove label</button></div>}
    {control.error && <p className="project-dialog-error" role="alert">{control.error}</p>}
    {control.pending && <div className="board-conflict"><button type="button" disabled={control.busy} onClick={() => void control.check()}>Check original change</button><button type="button" disabled={control.busy} onClick={() => void control.retry()}>Retry original change</button></div>}
    <footer className="project-actions">{baseline.label && <button type="button" className="board-danger" disabled={locked} onClick={() => setRemoving(true)}>Delete label</button>}
      <button type="button" disabled={control.busy} onClick={close}>Cancel</button><button className="project-primary" disabled={locked || conflict || !valid || removing || (!!baseline.label && !dirty)}>Save</button></footer>
  </form></BoardDialog>;
}
