import { memo } from 'react';
import type { BoardCardSummary, BoardColumn, BoardLabel } from '../../../../shared/project-boards';
import { calendarToday } from './BoardFilters';
import type { BoardDragHint, useBoardDrag } from './useBoardDrag';
import type { MovingEntry } from './MoveEntryDialog';

type Drag = ReturnType<typeof useBoardDrag>['actions'];
const BoardCardView = memo(function BoardCardView({ card, labels, marker, drag, dragEnabled, locked, viewLocked, open, move }: {
  card: BoardCardSummary; labels: BoardLabel[]; marker?: BoardDragHint; drag: Drag; dragEnabled: boolean; locked: boolean; viewLocked: boolean;
  open: (id: string) => void; move: (entry: MovingEntry) => void;
}) {
  return <article className={'board-card' + (marker ? ' board-card-drop-' + marker.edge : '')}
    data-card-id={card.id} onDragOver={event => drag.cardOver(event, card.id)} onDrop={drag.drop}>
    <button type="button" className="board-card-open" aria-label={card.title} disabled={viewLocked} onClick={() => open(card.id)}>
      <strong>{card.title}</strong>{card.archived && <span className="board-archived-text">Archived</span>}{card.descriptionPreview && <span className="board-card-preview">{card.descriptionPreview}</span>}
      <span className="board-card-meta"><span data-priority={card.priority}>{card.priority[0].toUpperCase() + card.priority.slice(1)}</span>
        {card.dueDate && <span className={card.dueDate < calendarToday() ? 'board-overdue' : ''}>Due {card.dueDate}</span>}
        {!!card.checklistCount && <span aria-label={`${card.checked} of ${card.checklistCount} checklist items complete`}>☑ {card.checked}/{card.checklistCount}</span>}</span>
      {!!card.labelIds.length && <span className="board-card-labels">{labels.filter(label => card.labelIds.includes(label.id)).map(label => <span key={label.id} className="board-label" data-color={label.color}>{label.name}</span>)}</span>}
    </button><footer className="board-card-actions"><span className="board-drag-grip" aria-hidden="true" title="Drag card" data-drag-card={card.id} {...drag.grip({ kind: 'card', id: card.id }, dragEnabled)}>⠿</span>
      <button type="button" disabled={locked || card.archived} aria-label={'Move card ' + card.title} onClick={() => move({ kind: 'card', id: card.id })}>Move</button></footer>
  </article>;
});
const BoardCards = memo(function BoardCards({ cards, labels, marker, drag, dragEnabled, locked, viewLocked, open, move, filtered }: {
  cards: BoardCardSummary[]; labels: BoardLabel[]; marker?: BoardDragHint; drag: Drag; dragEnabled: boolean; locked: boolean; viewLocked: boolean;
  open: (id: string) => void; move: (entry: MovingEntry) => void; filtered: boolean;
}) {
  return <div className={'board-cards' + (marker?.edge === 'end' ? ' board-drop-end' : '')}>
    {cards.map(card => <BoardCardView key={card.id} card={card} labels={labels} marker={marker?.target === card.id ? marker : undefined}
      drag={drag} dragEnabled={dragEnabled} locked={locked} viewLocked={viewLocked} open={open} move={move} />)}
    {!cards.length && <p className="board-empty">{filtered ? 'No matching cards in this column.' : 'No cards yet.'}</p>}
  </div>;
});
export const BoardColumnView = memo(function BoardColumnView({ column, cards, labels, filtered, title, titleChanged, locked, viewLocked, minimum, edit, remove, open, add, drag, marker, dragEnabled, move }: {
  column: BoardColumn; cards: BoardCardSummary[]; title: string; titleChanged: (columnId: string, value: string) => void; locked: boolean; minimum: boolean;
  edit: (column: BoardColumn) => void; remove: (column: BoardColumn) => void; open: (id: string) => void; add: (columnId: string, title: string) => void;
  drag: Drag; marker?: BoardDragHint | null; dragEnabled: boolean; move: (entry: MovingEntry) => void;
  labels: BoardLabel[]; filtered: boolean; viewLocked: boolean;
}) {
  return <section className={'board-column' + (marker?.kind === 'column' ? ' board-drop-' + marker.edge : '')}
    aria-label={column.title} data-column-id={column.id} onDragOver={event => drag.columnOver(event, column.id)} onDrop={drag.drop}>
    <header><h3>{column.title}</h3><span className="board-count" aria-label={`${column.cardCount} active cards`}>{column.cardCount}</span></header>
    <div className="board-entry-actions"><span className="board-drag-grip" aria-hidden="true" title="Drag column" data-drag-column={column.id} {...drag.grip({ kind: 'column', id: column.id }, dragEnabled)}>⠿</span>
      <button type="button" disabled={locked} aria-label={'Move column ' + column.title} onClick={() => move({ kind: 'column', id: column.id })}>Move</button>
      <button type="button" disabled={locked} aria-label={'Edit column ' + column.title} onClick={() => edit(column)}>Edit</button>
      <button type="button" disabled={locked || minimum} aria-label={'Remove column ' + column.title} onClick={() => remove(column)}>Remove</button></div>
    <BoardCards cards={cards} labels={labels} marker={marker?.kind === 'card' ? marker : undefined} drag={drag} dragEnabled={dragEnabled}
      locked={locked} viewLocked={viewLocked} open={open} move={move} filtered={filtered} />
    <form className="board-quick-card" onSubmit={event => { event.preventDefault(); if (!locked && title.trim() && Array.from(title.trim()).length <= 240) add(column.id, title); }}>
      <input aria-label={'New card in ' + column.title} placeholder="Card title" autoComplete="off" value={title} maxLength={960} disabled={locked} onChange={event => titleChanged(column.id, event.target.value)} />
      <button disabled={locked || !title.trim() || Array.from(title.trim()).length > 240}>Add card</button>
      {!!title && <button type="button" disabled={locked} onClick={() => titleChanged(column.id, '')}>Cancel</button>}
    </form>
  </section>;
});
