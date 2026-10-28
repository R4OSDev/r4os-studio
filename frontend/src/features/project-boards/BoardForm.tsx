import { useEffect, useState } from 'react';
import type { BoardSummary, BoardsListing } from '../../../../shared/project-boards';
import { projectRequestId } from '../projects/api';
import type { useBoardChange } from './useBoardChange';
import { BoardDialog } from './BoardDialog';

type Control = ReturnType<typeof useBoardChange>;
export function BoardForm({ initial, listing, current, control, close, dirtyChanged }: {
  initial?: BoardSummary; listing: BoardsListing; current?: BoardSummary; control: Control; close: () => void; dirtyChanged: (value: boolean) => void;
}) {
  const [baseline, setBaseline] = useState({ name: initial?.name ?? '', description: initial?.description ?? '', revision: initial?.revision ?? listing.revision });
  const [name, setName] = useState(baseline.name), [description, setDescription] = useState(baseline.description);
  const dirty = name !== baseline.name || description !== baseline.description, liveRevision = initial ? current?.revision : listing.revision;
  const conflict = liveRevision !== undefined && liveRevision !== baseline.revision;
  useEffect(() => { dirtyChanged(dirty); return () => dirtyChanged(false); }, [dirty, dirtyChanged]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);
  function review() {
    if (initial && current) {
      if (name === baseline.name) setName(current.name);
      if (description === baseline.description) setDescription(current.description);
      setBaseline({ name: current.name, description: current.description, revision: current.revision });
    } else setBaseline(value => ({ ...value, revision: listing.revision }));
  }
  const locked = control.busy || !!control.pending;
  return <BoardDialog title={initial ? 'Edit Board' : 'New Board'} close={() => { if (!control.busy) close(); }}>
    <form onSubmit={event => {
      event.preventDefault(); if (locked || conflict || !name.trim() || Array.from(name.trim()).length > 120 || Array.from(description).length > 8000) return;
      const body = { requestId: projectRequestId(), expectedRevision: baseline.revision, name, description };
      void control.perform(initial ? { kind: 'update', boardId: initial.id, body: { requestId: body.requestId, expectedRevision: body.expectedRevision,
        ...(name !== baseline.name ? { name } : {}), ...(description !== baseline.description ? { description } : {}) } } : { kind: 'create', body });
    }}>
      <fieldset className="project-fields" disabled={locked}><label className="project-field">Name<input autoComplete="off" value={name} maxLength={480} onChange={event => setName(event.target.value)} /></label>
        <label className="project-field">Description<textarea rows={4} value={description} maxLength={32000} onChange={event => setDescription(event.target.value)} /></label></fieldset>
      {conflict && <div className="board-conflict" role="status"><p>{initial ? 'This Board changed.' : 'The Board list changed.'} Your draft was preserved.</p>
        {current && <p className="board-current-text">Saved: {current.name}{current.description ? '\n' + current.description : ''}</p>}
        <button type="button" disabled={locked} onClick={review}>Review saved changes</button></div>}
      {control.error && <p className="project-dialog-error" role="alert">{control.error}</p>}
      {control.pending && <div className="board-conflict"><p>The original change is unconfirmed.</p><button type="button" disabled={control.busy} onClick={() => void control.check()}>Check original change</button>
        <button type="button" disabled={control.busy} onClick={() => void control.retry()}>Retry original change</button></div>}
      <footer className="project-actions"><button type="button" disabled={control.busy} onClick={close}>Cancel</button><button className="project-primary" disabled={locked || conflict || !name.trim() || Array.from(name.trim()).length > 120 || Array.from(description).length > 8000 || (!!initial && !dirty)}>{control.busy ? 'Saving…' : 'Save'}</button></footer>
    </form>
  </BoardDialog>;
}

export function BoardOrderDialog({ board, listing, control, close }: { board: BoardSummary; listing: BoardsListing; control: Control; close: () => void }) {
  const [original] = useState(listing), [position, setPosition] = useState(listing.boards.findIndex(value => value.id === board.id));
  const conflict = listing.revision !== original.revision, locked = control.busy || !!control.pending;
  return <BoardDialog title="Move Board" close={() => { if (!control.busy) close(); }}><form onSubmit={event => {
    event.preventDefault(); if (locked || conflict) return;
    const ids = original.boards.map(value => value.id).filter(id => id !== board.id); ids.splice(position, 0, board.id);
    void control.perform({ kind: 'order', body: { requestId: projectRequestId(), expectedRevision: original.revision, ids } });
  }}><fieldset className="project-fields" disabled={locked}><label className="project-field">Position<select value={position} onChange={event => setPosition(Number(event.target.value))}>
    {original.boards.map((value, index) => <option key={value.id} value={index}>{index + 1}</option>)}</select></label></fieldset>
    {conflict && <p className="project-dialog-status">The Board list changed. Cancel and reopen Move Board.</p>}
    {control.error && <p className="project-dialog-error" role="alert">{control.error}</p>}
    <footer className="project-actions"><button type="button" disabled={control.busy} onClick={close}>Cancel</button><button className="project-primary" disabled={locked || conflict}>Move</button></footer>
  </form></BoardDialog>;
}
