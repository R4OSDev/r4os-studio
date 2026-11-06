import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { DragEvent, PointerEvent } from 'react';
import type { BoardCardSummary, BoardMutation, BoardSnapshot } from '../../../../shared/project-boards';
import { projectRequestId } from '../projects/api';
import type { MovingEntry } from './MoveEntryDialog';

const mime = 'application/x-r4os-board';
export type BoardDragHint = { kind: 'card' | 'column'; target: string; position: number; edge: 'before' | 'after' | 'end' };
type Source = MovingEntry & { data: BoardSnapshot; nonce: string; cards: Map<string, BoardCardSummary>; counts: Map<string, number>; positions: Map<string, number>; columns: Map<string, number> };
type Target = { kind: 'card' | 'column'; id: string; element: HTMLElement; canvas: HTMLElement | null; x: number; y: number; nonce: string };
const sameHint = (a: BoardDragHint | null, b: BoardDragHint | null) => a === b || !!a && !!b && a.kind === b.kind && a.target === b.target && a.position === b.position && a.edge === b.edge;
export function useBoardDrag(data: BoardSnapshot | null, enabled: boolean, send: (body: BoardMutation) => void) {
  const source = useRef<Source | null>(null), lastScroll = useRef(0), marker = useRef<BoardDragHint | null>(null);
  const pending = useRef<Target | null>(null), frame = useRef<number | undefined>(undefined), latest = useRef({ data, enabled, send });
  useLayoutEffect(() => { latest.current = { data, enabled, send }; });
  const [hint, setHint] = useState<BoardDragHint | null>(null), [dragging, setDragging] = useState<MovingEntry | null>(null);
  const actions = useMemo(() => {
    function publish(next: BoardDragHint | null) {
      if (sameHint(marker.current, next)) return;
      marker.current = next; setHint(next);
    }
    function dispose() { if (frame.current !== undefined) cancelAnimationFrame(frame.current); frame.current = undefined; pending.current = null; source.current = null; marker.current = null; }
    function clear() { dispose(); setHint(null); setDragging(null); }
    function available(event: DragEvent) {
      const current = latest.current;
      return current.enabled && current.data && source.current?.data.projectId === current.data.projectId && source.current.data.board.id === current.data.board.id && event.dataTransfer.types.includes(mime);
    }
    function grip(entry: MovingEntry, allowed: boolean) {
      return { draggable: allowed, onPointerDown: (event: PointerEvent<HTMLElement>) => { event.currentTarget.draggable = latest.current.enabled && event.pointerType !== 'touch'; },
        onDragStart: (event: DragEvent<HTMLElement>) => {
          const current = latest.current;
          if (!current.enabled || !current.data || !event.currentTarget.draggable) { event.preventDefault(); return; }
          clear();
          const data = current.data, cards = new Map(data.cards.map(card => [card.id, card])), counts = new Map<string, number>(), positions = new Map<string, number>();
          const groups = new Map<string, BoardCardSummary[]>();
          for (const card of data.cards) if (entry.kind !== 'card' || card.id !== entry.id) { const list = groups.get(card.columnId) ?? []; list.push(card); groups.set(card.columnId, list); }
          for (const [id, list] of groups) { list.sort((a, b) => a.position - b.position); counts.set(id, list.length); list.forEach((card, index) => positions.set(card.id, index)); }
          const columns = new Map(data.columns.filter(column => entry.kind !== 'column' || column.id !== entry.id).map((column, index) => [column.id, index]));
          const nonce = projectRequestId(); source.current = { ...entry, data, nonce, cards, counts, positions, columns }; setDragging(entry);
          event.dataTransfer.setData(mime, nonce); event.dataTransfer.effectAllowed = 'move';
        }, onDragEnd: clear };
    }
    function calculate(target: Target) {
      const original = source.current;
      if (!original || original.nonce !== target.nonce || !latest.current.enabled || !target.element.isConnected) return;
      if (target.canvas && Date.now() - lastScroll.current >= 32) {
        const bounds = target.canvas.getBoundingClientRect(), delta = target.x < bounds.left + 32 ? -10 : target.x > bounds.right - 32 ? 10 : 0;
        if (delta) target.canvas.scrollLeft += delta;
        lastScroll.current = Date.now();
      }
      if (target.kind === 'column') {
        if (original.kind === 'card') {
          if (!original.data.columns.some(column => column.id === target.id)) { publish(null); return; }
          publish({ kind: 'card', target: target.id, position: original.counts.get(target.id) ?? 0, edge: 'end' });
        } else {
          const index = original.columns.get(target.id); if (index === undefined) { publish(null); return; }
          const bounds = target.element.getBoundingClientRect(), after = target.x > bounds.left + bounds.width / 2;
          publish({ kind: 'column', target: target.id, position: index + Number(after), edge: after ? 'after' : 'before' });
        }
      } else {
        if (original.kind !== 'card') return;
        const index = original.positions.get(target.id); if (index === undefined) { publish(null); return; }
        const bounds = target.element.getBoundingClientRect(), after = target.y > bounds.top + bounds.height / 2;
        publish({ kind: 'card', target: target.id, position: index + Number(after), edge: after ? 'after' : 'before' });
      }
    }
    function flush() {
      if (frame.current !== undefined) cancelAnimationFrame(frame.current); frame.current = undefined;
      const target = pending.current; pending.current = null; if (target) calculate(target);
    }
    function over(event: DragEvent<HTMLElement>, kind: Target['kind'], id: string) {
      if (!available(event) || kind === 'card' && source.current?.kind !== 'card') return;
      event.preventDefault(); event.stopPropagation(); event.dataTransfer.dropEffect = 'move';
      pending.current = { kind, id, element: event.currentTarget, canvas: event.currentTarget.closest<HTMLElement>('.board-canvas'), x: event.clientX, y: event.clientY, nonce: source.current!.nonce };
      frame.current ??= requestAnimationFrame(flush);
    }
    function drop(event: DragEvent) {
      if (!available(event)) return;
      event.preventDefault(); event.stopPropagation(); flush();
      const original = source.current!, target = marker.current;
      if (!target || event.dataTransfer.getData(mime) !== original.nonce) { clear(); return; }
      const snapshot = original.data, common = { requestId: projectRequestId(), expectedRevision: snapshot.board.revision, expectedOrderRevision: snapshot.board.orderRevision };
      if (original.kind === 'card') {
        const card = original.cards.get(original.id), columnId = target.edge === 'end' ? target.target : original.cards.get(target.target)?.columnId;
        if (card && columnId && (card.columnId !== columnId || card.position !== target.position)) latest.current.send({ ...common, action: 'move_card', input: { cardId: card.id, expectedCardRevision: card.revision, sourceColumnId: card.columnId, targetColumnId: columnId, position: target.position } });
      } else {
        const column = snapshot.columns.find(row => row.id === original.id);
        if (column && column.position !== target.position) latest.current.send({ ...common, action: 'move_column', input: { columnId: column.id, expectedColumnRevision: column.revision, position: target.position } });
      }
      clear();
    }
    return { grip, drop, clear, dispose, columnOver: (event: DragEvent<HTMLElement>, id: string) => over(event, 'column', id), cardOver: (event: DragEvent<HTMLElement>, id: string) => over(event, 'card', id),
      canvasOver: (event: DragEvent) => { if (event.target === event.currentTarget || event.dataTransfer.types.includes('Files')) { event.preventDefault(); if (frame.current !== undefined) cancelAnimationFrame(frame.current); frame.current = undefined; pending.current = null; publish(null); } },
      canvasDrop: (event: DragEvent) => { event.preventDefault(); clear(); } };
  }, []);
  useEffect(() => { const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') actions.clear(); }; window.addEventListener('keydown', escape);
    return () => { window.removeEventListener('keydown', escape); actions.dispose(); };
  }, [actions]);
  return { hint, dragging, enabled, actions, ...actions };
}
