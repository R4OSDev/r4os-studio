import type { BoardCardSummary, BoardColumn } from '../../../../shared/project-boards';

export function BoardColumnView({ column, cards, title, titleChanged, locked, minimum, edit, remove, open, add }: {
  column: BoardColumn; cards: BoardCardSummary[]; title: string; titleChanged: (value: string) => void; locked: boolean; minimum: boolean;
  edit: () => void; remove: () => void; open: (id: string) => void; add: () => void;
}) {
  return <section className="board-column" aria-label={column.title} data-column-id={column.id}>
    <header><h3>{column.title}</h3><span className="board-count" aria-label={`${column.cardCount} cards`}>{column.cardCount}</span></header>
    <div className="board-entry-actions"><button type="button" disabled={locked} aria-label={'Edit column ' + column.title} onClick={edit}>Edit</button>
      <button type="button" disabled={locked || minimum} aria-label={'Remove column ' + column.title} onClick={remove}>Remove</button></div>
    <div className="board-cards">{cards.filter(card => !card.archived).sort((a, b) => a.position - b.position).map(card => <button type="button" className="board-card" key={card.id} data-card-id={card.id} aria-label={card.title} disabled={locked} onClick={() => open(card.id)}>
      <strong>{card.title}</strong>{card.descriptionPreview && <span className="board-card-preview">{card.descriptionPreview}</span>}
    </button>)}{!cards.some(card => !card.archived) && <p className="board-empty">No cards yet.</p>}</div>
    <form className="board-quick-card" onSubmit={event => { event.preventDefault(); if (!locked && title.trim() && Array.from(title.trim()).length <= 240) add(); }}>
      <input aria-label={'New card in ' + column.title} placeholder="Card title" autoComplete="off" value={title} maxLength={960} disabled={locked} onChange={event => titleChanged(event.target.value)} />
      <button disabled={locked || !title.trim() || Array.from(title.trim()).length > 240}>Add card</button>
      {!!title && <button type="button" disabled={locked} onClick={() => titleChanged('')}>Cancel</button>}
    </form>
  </section>;
}
