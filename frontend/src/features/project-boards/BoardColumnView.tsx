import type { BoardCardSummary, BoardColumn, BoardLabel } from '../../../../shared/project-boards';
import { calendarToday } from './BoardFilters';
import type { useBoardDrag } from './useBoardDrag';
import type { MovingEntry } from './MoveEntryDialog';

export function BoardColumnView({ column, cards, labels, filtered, title, titleChanged, locked, minimum, edit, remove, open, add, drag, move }: {
  column: BoardColumn; cards: BoardCardSummary[]; title: string; titleChanged: (value: string) => void; locked: boolean; minimum: boolean;
  edit: () => void; remove: () => void; open: (id: string) => void; add: () => void;
  drag: ReturnType<typeof useBoardDrag>; move: (entry: MovingEntry) => void;
  labels: BoardLabel[]; filtered: boolean;
}) {
  const marker = drag.hint;
  return <section className={'board-column' + (marker?.kind === 'column' && marker.target === column.id ? ' board-drop-' + marker.edge : '')}
    aria-label={column.title} data-column-id={column.id} onDragOver={event => drag.columnOver(event, column.id)} onDrop={drag.drop}>
    <header><h3>{column.title}</h3><span className="board-count" aria-label={`${column.cardCount} cards`}>{column.cardCount}</span></header>
    <div className="board-entry-actions"><span className="board-drag-grip" aria-hidden="true" title="Drag column" data-drag-column={column.id} {...drag.grip({ kind: 'column', id: column.id })}>⠿</span>
      <button type="button" disabled={locked} aria-label={'Move column ' + column.title} onClick={() => move({ kind: 'column', id: column.id })}>Move</button>
      <button type="button" disabled={locked} aria-label={'Edit column ' + column.title} onClick={edit}>Edit</button>
      <button type="button" disabled={locked || minimum} aria-label={'Remove column ' + column.title} onClick={remove}>Remove</button></div>
    <div className={'board-cards' + (marker?.kind === 'card' && marker.target === column.id && marker.edge === 'end' ? ' board-drop-end' : '')}>
      {cards.filter(card => !card.archived).sort((a, b) => a.position - b.position).map(card => <article className={'board-card' + (marker?.kind === 'card' && marker.target === card.id ? ' board-card-drop-' + marker.edge : '')}
        key={card.id} data-card-id={card.id} onDragOver={event => drag.cardOver(event, card.id)} onDrop={drag.drop}>
        <button type="button" className="board-card-open" aria-label={card.title} disabled={locked} onClick={() => open(card.id)}>
          <strong>{card.title}</strong>{card.descriptionPreview && <span className="board-card-preview">{card.descriptionPreview}</span>}
          <span className="board-card-meta"><span data-priority={card.priority}>{card.priority[0].toUpperCase() + card.priority.slice(1)}</span>
            {card.dueDate && <span className={card.dueDate < calendarToday() ? 'board-overdue' : ''}>Due {card.dueDate}</span>}
            {!!card.checklistCount && <span aria-label={`${card.checked} of ${card.checklistCount} checklist items complete`}>☑ {card.checked}/{card.checklistCount}</span>}</span>
          {!!card.labelIds.length && <span className="board-card-labels">{labels.filter(label => card.labelIds.includes(label.id)).map(label => <span key={label.id} className="board-label" data-color={label.color}>{label.name}</span>)}</span>}
        </button><footer className="board-card-actions"><span className="board-drag-grip" aria-hidden="true" title="Drag card" data-drag-card={card.id} {...drag.grip({ kind: 'card', id: card.id })}>⠿</span>
          <button type="button" disabled={locked} aria-label={'Move card ' + card.title} onClick={() => move({ kind: 'card', id: card.id })}>Move</button></footer>
      </article>)}{!cards.some(card => !card.archived) && <p className="board-empty">{filtered ? 'No matching cards in this column.' : 'No cards yet.'}</p>}</div>
    <form className="board-quick-card" onSubmit={event => { event.preventDefault(); if (!locked && title.trim() && Array.from(title.trim()).length <= 240) add(); }}>
      <input aria-label={'New card in ' + column.title} placeholder="Card title" autoComplete="off" value={title} maxLength={960} disabled={locked} onChange={event => titleChanged(event.target.value)} />
      <button disabled={locked || !title.trim() || Array.from(title.trim()).length > 240}>Add card</button>
      {!!title && <button type="button" disabled={locked} onClick={() => titleChanged('')}>Cancel</button>}
    </form>
  </section>;
}
