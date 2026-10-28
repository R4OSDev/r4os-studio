import { useEffect, useState } from 'react';
import type { BoardCardSummary, BoardSnapshot, BoardSearch } from '../../../../shared/project-boards';
import { searchBoard } from './api';
export function calendarToday() { const date = new Date(); return `${date.getFullYear().toString().padStart(4, '0')}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getDate().toString().padStart(2, '0')}`; }
export function useBoardFilters(projectId: string, data: BoardSnapshot | null) {
  const [query, setQuery] = useState(''), [label, setLabel] = useState(''), [priority, setPriority] = useState(''), [due, setDue] = useState('');
  const [match, setMatch] = useState<{ query: string; value: BoardSearch } | null>(null), [error, setError] = useState('');
  const boardId = data?.board.id, revision = data?.board.revision, needle = query.trim(), active = !!(needle || label || priority || due);
  useEffect(() => {
    if (!boardId || !needle || Array.from(needle).length > 256) return;
    const controller = new AbortController();
    const timer = setTimeout(() => { void searchBoard(projectId, boardId, needle, controller.signal).then(value => {
      if (controller.signal.aborted) return;
      if (value.projectId !== projectId || value.boardId !== boardId) throw new Error('The search reply belongs to another Board.');
      setMatch({ query: needle, value }); setError('');
    }).catch((failure: Error) => { if (!controller.signal.aborted) setError(failure.message); }); }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [projectId, boardId, revision, needle]);
  const searching = !!needle && (match?.query !== needle || match.value.boardId !== boardId || match.value.boardRevision !== revision);
  function includes(card: BoardCardSummary) {
    if (needle && (searching || !match?.value.cardIds.includes(card.id))) return false;
    if (label && !card.labelIds.includes(label) || priority && card.priority !== priority) return false;
    const today = calendarToday();
    return !due || (due === 'none' ? !card.dueDate : !!card.dueDate && (due === 'overdue' ? card.dueDate < today : due === 'today' ? card.dueDate === today : card.dueDate > today));
  }
  return { query, setQuery, label, setLabel, priority, setPriority, due, setDue, active, searching, error: needle ? Array.from(needle).length > 256 ? 'Use at most256 search characters.' : error : '', includes,
    clear: () => { setQuery(''); setLabel(''); setPriority(''); setDue(''); setError(''); } };
}
export function BoardFilters({ data, filters }: { data: BoardSnapshot; filters: ReturnType<typeof useBoardFilters> }) {
  const visible = data.cards.filter(card => !card.archived && filters.includes(card)).length, total = data.cards.filter(card => !card.archived).length;
  return <div className="board-filters" role="search" aria-label="Filter cards"><label>Search cards<input type="search" placeholder="Title or description" value={filters.query} maxLength={1024} onChange={event => filters.setQuery(event.target.value)} /></label>
    <label>Label<select value={filters.label} onChange={event => filters.setLabel(event.target.value)}><option value="">All labels</option>{data.labels.map(label => <option key={label.id} value={label.id}>{label.name}</option>)}{filters.label && !data.labels.some(label => label.id === filters.label) && <option value={filters.label}>Removed label</option>}</select></label>
    <label>Priority<select value={filters.priority} onChange={event => filters.setPriority(event.target.value)}><option value="">All priorities</option><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option></select></label>
    <label>Due<select value={filters.due} onChange={event => filters.setDue(event.target.value)}><option value="">Any date</option><option value="overdue">Overdue</option><option value="today">Today</option><option value="upcoming">Upcoming</option><option value="none">No date</option></select></label>
    {filters.active && <><button type="button" onClick={filters.clear}>Clear filters</button><span className="project-help">{visible} of {total} cards · Use Move while filtering.</span></>}
    {filters.searching && <span role="status">Searching…</span>}{filters.error && <span className="project-error" role="alert">{filters.error}</span>}
    {filters.active && !filters.searching && !filters.error && !visible && <p className="board-empty">No cards match these filters.</p>}
  </div>;
}
