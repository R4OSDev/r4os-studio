import { useEffect, useRef, useState } from 'react';
import type { DragEvent, PointerEvent } from 'react';
import type { BoardMutation, BoardSnapshot } from '../../../../shared/project-boards';
import { projectRequestId } from '../projects/api';
import type { MovingEntry } from './MoveEntryDialog';

const mime = 'application/x-r4os-board';
type Source = MovingEntry & { data: BoardSnapshot; nonce: string };
type Hint = { kind: 'card' | 'column'; target: string; position: number; edge: 'before' | 'after' | 'end' };
export function useBoardDrag(data: BoardSnapshot | null, enabled: boolean, send: (body: BoardMutation) => void) {
  const source = useRef<Source | null>(null), lastScroll = useRef(0);
  const [hint, setHint] = useState<Hint | null>(null), [dragging, setDragging] = useState<MovingEntry | null>(null);
  const clear = () => { source.current = null; setHint(null); setDragging(null); };
  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') clear(); };
    window.addEventListener('keydown', escape); return () => window.removeEventListener('keydown', escape);
  }, []);
  function grip(entry: MovingEntry) {
    return { draggable: enabled, onPointerDown: (event: PointerEvent<HTMLElement>) => { event.currentTarget.draggable = enabled && event.pointerType !== 'touch'; },
      onDragStart: (event: DragEvent<HTMLElement>) => {
        if (!enabled || !data || !event.currentTarget.draggable) { event.preventDefault(); return; }
        const nonce = projectRequestId(); source.current = { ...entry, data, nonce }; setDragging(entry);
        event.dataTransfer.setData(mime, nonce); event.dataTransfer.effectAllowed = 'move';
      }, onDragEnd: clear };
  }
  function available(event: DragEvent) { return enabled && data && source.current?.data.board.id === data.board.id && event.dataTransfer.types.includes(mime); }
  function scroll(event: DragEvent) {
    const canvas = event.currentTarget.closest<HTMLElement>('.board-canvas'); if (!canvas || Date.now() - lastScroll.current < 32) return;
    const bounds = canvas.getBoundingClientRect(); const delta = event.clientX < bounds.left + 32 ? -10 : event.clientX > bounds.right - 32 ? 10 : 0;
    if (delta) { canvas.scrollLeft += delta; lastScroll.current = Date.now(); }
  }
  function columnOver(event: DragEvent<HTMLElement>, columnId: string) {
    if (!available(event)) return;
    event.preventDefault(); event.stopPropagation(); event.dataTransfer.dropEffect = 'move'; scroll(event);
    const original = source.current!, snapshot = original.data;
    if (original.kind === 'card') setHint({ kind: 'card', target: columnId, position: snapshot.cards.filter(row => row.columnId === columnId && row.id !== original.id).length, edge: 'end' });
    else {
      const others = snapshot.columns.filter(row => row.id !== original.id), index = others.findIndex(row => row.id === columnId);
      if (index < 0) { setHint(null); return; }
      const bounds = event.currentTarget.getBoundingClientRect(), after = event.clientX > bounds.left + bounds.width / 2;
      setHint({ kind: 'column', target: columnId, position: index + Number(after), edge: after ? 'after' : 'before' });
    }
  }
  function cardOver(event: DragEvent<HTMLElement>, cardId: string) {
    if (!available(event) || source.current?.kind !== 'card') return;
    event.preventDefault(); event.stopPropagation(); event.dataTransfer.dropEffect = 'move'; scroll(event);
    const original = source.current!, target = original.data.cards.find(row => row.id === cardId);
    if (!target || target.id === original.id) { setHint(null); return; }
    const others = original.data.cards.filter(row => row.columnId === target.columnId && row.id !== original.id).sort((a, b) => a.position - b.position);
    const bounds = event.currentTarget.getBoundingClientRect(), after = event.clientY > bounds.top + bounds.height / 2;
    setHint({ kind: 'card', target: cardId, position: others.findIndex(row => row.id === cardId) + Number(after), edge: after ? 'after' : 'before' });
  }
  function drop(event: DragEvent) {
    if (!available(event)) return;
    event.preventDefault(); event.stopPropagation();
    const original = source.current!, marker = hint;
    if (!marker || event.dataTransfer.getData(mime) !== original.nonce) { clear(); return; }
    const snapshot = original.data, common = { requestId: projectRequestId(), expectedRevision: snapshot.board.revision, expectedOrderRevision: snapshot.board.orderRevision };
    if (original.kind === 'card') {
      const card = snapshot.cards.find(row => row.id === original.id), columnId = marker.edge === 'end' ? marker.target : snapshot.cards.find(row => row.id === marker.target)?.columnId;
      if (card && columnId && (card.columnId !== columnId || card.position !== marker.position)) send({ ...common, action: 'move_card', input: { cardId: card.id, expectedCardRevision: card.revision, sourceColumnId: card.columnId, targetColumnId: columnId, position: marker.position } });
    } else {
      const column = snapshot.columns.find(row => row.id === original.id);
      if (column && column.position !== marker.position) send({ ...common, action: 'move_column', input: { columnId: column.id, expectedColumnRevision: column.revision, position: marker.position } });
    }
    clear();
  }
  return { hint, dragging, grip, columnOver, cardOver, drop, clear,
    canvasOver: (event: DragEvent) => { if (event.target === event.currentTarget || event.dataTransfer.types.includes('Files')) { event.preventDefault(); setHint(null); } },
    canvasDrop: (event: DragEvent) => { event.preventDefault(); clear(); } };
}
