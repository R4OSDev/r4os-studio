import { useCallback, useEffect, useRef, useState } from 'react';
import type { BoardSnapshot, BoardsListing } from '../../../../shared/project-boards';
import { listBoards, loadBoard } from './api';

type State = { readEpoch: number; scope: string; listing: BoardsListing | null; snapshot: BoardSnapshot | null; selectedId?: string; loading: boolean; error: string };
export function useBoards(projectId: string | null, requestedId?: string) {
  const scope = `${projectId ?? ''}:${requestedId ?? ''}`;
  const [epoch, setEpoch] = useState(0), [state, setState] = useState<State>({ readEpoch: -1, scope: '', listing: null, snapshot: null, loading: false, error: '' });
  const selection = useRef<{ scope: string; id: string } | null>(null);
  const [archiveView, setArchiveView] = useState<{ projectId: string | null; shown: boolean }>({ projectId, shown: false });
  const reload = useCallback(() => setEpoch(value => value + 1), []);
  useEffect(() => {
    if (!projectId) return;
    const refresh = () => { if (document.visibilityState === 'visible') reload(); };
    const timer = setInterval(refresh, 15000);
    window.addEventListener('focus', refresh); document.addEventListener('visibilitychange', refresh);
    return () => { clearInterval(timer); window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh); };
  }, [projectId, reload]);
  useEffect(() => {
    if (!projectId) return;
    const controller = new AbortController(), signal = controller.signal;
    setState(old => old.scope === scope ? { ...old, loading: true, error: '' } : { readEpoch: -1, scope, listing: null, snapshot: null, loading: true, error: '' });
    void (async () => {
      try {
        const listing = await listBoards(projectId, signal);
        if (signal.aborted) return;
        if (listing.projectId !== projectId) throw new Error('The Board list belongs to another project.');
        let saved: string | null = null;
        try { saved = sessionStorage.getItem('studio.boards.selection.' + projectId); } catch { /* Deep links still work. */ }
        // A removed current Board must not silently replace a local form with another Board.
        const selectedId = requestedId ?? (selection.current?.scope === scope ? selection.current.id : undefined) ?? listing.boards.find(board => board.id === saved && !board.archived)?.id ?? listing.boards.find(board => !board.archived)?.id;
        if (selectedId) selection.current = { scope, id: selectedId };
        setState(old => ({ ...old, scope, listing, selectedId, snapshot: old.snapshot?.board.id === selectedId ? old.snapshot : null }));
        if (!selectedId) { setState(old => ({ ...old, readEpoch: epoch, loading: false })); return; }
        const snapshot = await loadBoard(projectId, selectedId, signal);
        if (signal.aborted) return;
        if (snapshot.projectId !== projectId || snapshot.board.id !== selectedId) throw new Error('The Board reply belongs to another view.');
        try { sessionStorage.setItem('studio.boards.selection.' + projectId, selectedId); } catch { /* Navigation does not mutate server data. */ }
        setState({ readEpoch: epoch, scope, listing, snapshot, selectedId, loading: false, error: '' });
      } catch (failure) {
        if (!signal.aborted) setState(old => ({ ...old, readEpoch: epoch, loading: false, error: (failure as Error).message }));
      }
    })();
    return () => controller.abort();
  }, [projectId, requestedId, scope, epoch]);
  const visible: State = projectId && state.scope === scope ? { ...state, loading: state.loading || state.readEpoch !== epoch } : { readEpoch: -1, scope, listing: null, snapshot: null, loading: !!projectId, error: '' };
  return { ...visible, reload, showArchived: archiveView.projectId === projectId && archiveView.shown,
    setShowArchived: (shown: boolean) => setArchiveView({ projectId, shown }),
    forgetSelection: () => { selection.current = null; try { sessionStorage.removeItem('studio.boards.selection.' + projectId); } catch { /* View preference only. */ } } };
}
export type BoardsModel = ReturnType<typeof useBoards>;
