import type { Dispatch, SetStateAction } from 'react';
import type { BoardCard, BoardLabel } from '../../../../shared/project-boards';
import { projectRequestId } from '../projects/api';

export type CardDraft = Pick<BoardCard, 'title' | 'description' | 'priority' | 'dueDate' | 'labelIds' | 'checklist'>;
export const cardDraft = (card: BoardCard): CardDraft => ({ title: card.title, description: card.description, priority: card.priority, dueDate: card.dueDate, labelIds: card.labelIds, checklist: card.checklist });
export function CardMetadataFields({ draft, setDraft, labels }: { draft: CardDraft; setDraft: Dispatch<SetStateAction<CardDraft>>; labels: BoardLabel[] }) {
  function reorder(index: number, direction: number) {
    setDraft(old => { const next = [...old.checklist]; [next[index], next[index + direction]] = [next[index + direction], next[index]]; return { ...old, checklist: next }; });
  }
  return <>
    <div className="board-field-pair"><label className="project-field">Priority<select value={draft.priority} onChange={event => setDraft(old => ({ ...old, priority: event.target.value as BoardCard['priority'] }))}>
      <option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option></select></label>
      <label className="project-field">Due date<input type="date" min="0001-01-01" max="9999-12-31" value={draft.dueDate ?? ''} onChange={event => setDraft(old => ({ ...old, dueDate: event.target.value || null }))} /></label></div>
    <fieldset className="board-label-choices"><legend>Labels</legend>{labels.map(label => <label key={label.id}><input type="checkbox" checked={draft.labelIds.includes(label.id)} onChange={event => {
      const checked = event.target.checked; setDraft(old => ({ ...old, labelIds: checked ? [...old.labelIds, label.id] : old.labelIds.filter(id => id !== label.id) }));
    }} /><span className="board-label" data-color={label.color}>{label.name}</span></label>)}{!labels.length && <p className="project-help">Create labels with Manage labels in the Board.</p>}</fieldset>
    <fieldset className="board-checklist"><legend>Checklist · {draft.checklist.filter(item => item.checked).length}/{draft.checklist.length}</legend>
      {draft.checklist.map((item, index) => <div className="board-check-item" key={item.id}>
        <input type="checkbox" aria-label={'Complete checklist item ' + (index + 1)} checked={item.checked} onChange={event => { const checked = event.target.checked; setDraft(old => ({ ...old, checklist: old.checklist.map(row => row.id === item.id ? { ...row, checked } : row) })); }} />
        <input type="text" aria-label={'Checklist item ' + (index + 1)} maxLength={960} value={item.text} onChange={event => { const text = event.target.value; setDraft(old => ({ ...old, checklist: old.checklist.map(row => row.id === item.id ? { ...row, text } : row) })); }} />
        <div><button type="button" aria-label={'Move checklist item ' + (index + 1) + ' up'} disabled={index === 0} onClick={() => reorder(index, -1)}>↑</button>
          <button type="button" aria-label={'Move checklist item ' + (index + 1) + ' down'} disabled={index === draft.checklist.length - 1} onClick={() => reorder(index, 1)}>↓</button>
          <button type="button" aria-label={'Remove checklist item ' + (index + 1)} onClick={() => setDraft(old => ({ ...old, checklist: old.checklist.filter(row => row.id !== item.id) }))}>Remove</button></div>
      </div>)}<button type="button" disabled={draft.checklist.length >= 100} onClick={() => setDraft(old => ({ ...old, checklist: [...old.checklist, { id: projectRequestId(), text: '', checked: false, revision: 0, position: old.checklist.length }] }))}>Add checklist item</button>
    </fieldset>
  </>;
}
