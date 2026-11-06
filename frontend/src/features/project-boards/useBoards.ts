import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { BoardReadVersion, BoardSnapshot, BoardsListing } from '../../../../shared/project-boards';
import { listBoards, loadBoard, readBoardMetadata } from './api';

type Known = { revision: number; readVersion: BoardReadVersion };
type State = { readEpoch: number; scope: string; listing: BoardsListing | null; snapshot: BoardSnapshot | null; selectedId?: string; loading: boolean; error: string; known?: Known };
const sameVersion = (a?: BoardReadVersion, b?: BoardReadVersion) => !!a && !!b && a.source === b.source && a.stamp === b.stamp;
function retainRows<T extends { id: string }>(before: T[] | undefined, next: T[]) {
  if (!before) return next;
  const old = new Map(before.map(row => [row.id, row]));
  const retained = next.map(row => { const previous = old.get(row.id); return previous && JSON.stringify(previous) === JSON.stringify(row) ? previous : row; });
  return retained.length === before.length && retained.every((row, index) => row === before[index]) ? before : retained;
}
function retainSnapshot(before: BoardSnapshot | null | undefined, next: BoardSnapshot): BoardSnapshot {
  if (!before || before.projectId !== next.projectId || before.board.id !== next.board.id) return next;
  const board = JSON.stringify(before.board) === JSON.stringify(next.board) ? before.board : next.board;
  const columns = retainRows(before.columns, next.columns), cards = retainRows(before.cards, next.cards), labels = retainRows(before.labels, next.labels);
  if (before.revision === next.revision && board === before.board && columns === before.columns && cards === before.cards && labels === before.labels && sameVersion(before.readVersion, next.readVersion)) return before;
  return { ...next, board, columns, cards, labels };
}
export function useBoards(projectId: string | null, requestedId?: string) {
  const scope = `${projectId ?? ''}:${requestedId ?? ''}`;
  const [epoch, setEpoch] = useState(0), [pulse, setPulse] = useState(0);
  const [state, setState] = useState<State>({ readEpoch: -1, scope: '', listing: null, snapshot: null, loading: false, error: '' });
  const latest = useRef(state), selection = useRef<{ scope: string; id: string } | null>(null);
  useLayoutEffect(() => { latest.current = state; });
  const [archiveView, setArchiveView] = useState<{ projectId: string | null; shown: boolean }>({ projectId, shown: false });
  const reload = useCallback(() => setEpoch(value => value + 1), []);
  useEffect(() => {
    if (!projectId) return;
    const refresh = () => { if (document.visibilityState === 'visible') setPulse(value => value + 1); };
    const timer = setInterval(refresh, 15000);
    window.addEventListener('focus', refresh); document.addEventListener('visibilitychange', refresh);
    return () => { clearInterval(timer); window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh); };
  }, [projectId]);
  useEffect(() => {
    if (!projectId) return;
    const controller = new AbortController(), signal = controller.signal;
    const previous = latest.current.scope === scope ? latest.current : null;
    const force = !previous?.listing || previous.readEpoch !== epoch || !previous.known;
    // An existing view remains usable during read-only reconciliation. Server
    // revisions still decide each mutation; local forms and quick drafts stay put.
    setState(old => old.scope === scope ? old.error ? { ...old, error: '' } : old : { readEpoch: -1, scope, listing: null, snapshot: null, loading: true, error: '' });
    void (async () => {
      try {
        if (!force) {
          const metadata = await readBoardMetadata(projectId, signal);
          if (signal.aborted) return;
          if (metadata.projectId !== projectId || !Number.isSafeInteger(metadata.revision) || !metadata.readVersion?.source || !metadata.readVersion.stamp) throw new Error('The Board metadata belongs to another view.');
          if (metadata.revision === previous!.known!.revision && sameVersion(metadata.readVersion, previous!.known!.readVersion)) return;
        }
        const listing = await listBoards(projectId, signal);
        if (signal.aborted) return;
        if (listing.projectId !== projectId) throw new Error('The Board list belongs to another project.');
        let saved: string | null = null;
        try { saved = sessionStorage.getItem('studio.boards.selection.' + projectId); } catch { /* Deep links still work. */ }
        // A removed current Board must not silently replace a local form with another Board.
        const selectedId = requestedId ?? (selection.current?.scope === scope ? selection.current.id : undefined) ?? listing.boards.find(board => board.id === saved && !board.archived)?.id ?? listing.boards.find(board => !board.archived)?.id;
        if (selectedId) selection.current = { scope, id: selectedId };
        setState(old => ({ ...old, scope, listing, selectedId, snapshot: old.snapshot?.board.id === selectedId ? old.snapshot : null }));
        if (!selectedId) { setState(old => ({ ...old, readEpoch: epoch, loading: false, known: listing.readVersion ? { revision: listing.revision, readVersion: listing.readVersion } : undefined })); return; }
        const incoming = await loadBoard(projectId, selectedId, signal);
        if (signal.aborted) return;
        if (incoming.projectId !== projectId || incoming.board.id !== selectedId) throw new Error('The Board reply belongs to another view.');
        const snapshot = retainSnapshot(previous?.snapshot, incoming);
        // Separate HTTP reads must describe the same committed catalog before
        // its next unchanged metadata read can retain the entire view.
        const known = listing.revision === snapshot.revision && sameVersion(listing.readVersion, snapshot.readVersion)
          ? { revision: snapshot.revision, readVersion: snapshot.readVersion! } : undefined;
        try { sessionStorage.setItem('studio.boards.selection.' + projectId, selectedId); } catch { /* Navigation does not mutate server data. */ }
        setState({ readEpoch: epoch, scope, listing, snapshot, selectedId, known, loading: false, error: '' });
      } catch (failure) {
        if (!signal.aborted) setState(old => ({ ...old, readEpoch: epoch, loading: false, error: (failure as Error).message }));
      }
    })();
    return () => controller.abort();
  }, [projectId, requestedId, scope, epoch, pulse]);
  const visible: State = projectId && state.scope === scope ? { ...state, loading: state.loading || !state.listing && state.readEpoch !== epoch } : { readEpoch: -1, scope, listing: null, snapshot: null, loading: !!projectId, error: '' };
  return { ...visible, reload, showArchived: archiveView.projectId === projectId && archiveView.shown,
    setShowArchived: (shown: boolean) => setArchiveView({ projectId, shown }),
    forgetSelection: () => { selection.current = null; try { sessionStorage.removeItem('studio.boards.selection.' + projectId); } catch { /* View preference only. */ } } };
}
export type BoardsModel = ReturnType<typeof useBoards>;
