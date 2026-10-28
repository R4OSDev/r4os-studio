import { useCallback, useEffect, useRef, useState } from 'react';
import type { BoardCreate, BoardOrder, BoardReceipt, BoardUpdate } from '../../../../shared/project-boards';
import { ProjectRequestError } from '../projects/api';
import { createBoard, orderBoards, readBoardReceipt, updateBoard } from './api';

export type BoardChange = { kind: 'create'; body: BoardCreate } | { kind: 'update'; boardId: string; body: BoardUpdate } | { kind: 'order'; body: BoardOrder };
function read(key: string): BoardChange | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) ?? 'null');
    return value && ['create', 'update', 'order'].includes(value.kind) && typeof value.body?.requestId === 'string'
      && /^[a-f0-9-]{36}$/.test(value.body.requestId) && Number.isSafeInteger(value.body.expectedRevision)
      && (value.kind !== 'update' || /^[a-f0-9-]{36}$/.test(value.boardId)) ? value : null;
  } catch { return null; }
}
export function useBoardChange(projectId: string, token: string, accepted: (receipt: BoardReceipt, change: BoardChange) => void, busyChanged: (value: boolean) => void, reload: () => void) {
  const key = 'studio.boards.request.' + projectId;
  const [pending, setPending] = useState(() => read(key)), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const current = useRef(pending), mounted = useRef(true), active = useRef(false), acceptedRef = useRef(accepted);
  useEffect(() => { acceptedRef.current = accepted; }, [accepted]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { busyChanged(busy); return () => busyChanged(false); }, [busy, busyChanged]);
  const finish = useCallback((receipt: BoardReceipt, change: BoardChange) => {
    if (!mounted.current || current.current?.body.requestId !== change.body.requestId) return;
    if (receipt.requestId !== change.body.requestId || (change.kind === 'update' && receipt.boardId !== change.boardId)) throw new Error('The original Board receipt does not match this change.');
    sessionStorage.removeItem(key); current.current = null; setPending(null); setError(''); acceptedRef.current(receipt, change);
  }, [key]);
  const check = useCallback(async (change: BoardChange) => {
    try { finish(await readBoardReceipt(projectId, change.body.requestId), change); return true; }
    catch (failure) {
      if (!mounted.current) return false;
      setError((failure as ProjectRequestError).status === 404 ? 'The original change has no confirmed receipt yet. Check again or retry the same change.' : 'The original Board change is unconfirmed. Check its receipt before continuing.');
      return false;
    }
  }, [finish, projectId]);
  useEffect(() => {
    const original = current.current;
    if (!original) return;
    active.current = true; setBusy(true);
    void check(original).finally(() => { active.current = false; if (mounted.current) setBusy(false); });
  }, [check]);
  async function perform(change: BoardChange) {
    if (active.current || (current.current && current.current.body.requestId !== change.body.requestId)) return;
    try { sessionStorage.setItem(key, JSON.stringify(change)); }
    catch { setError('Enable session storage before saving a Board change.'); return; }
    current.current = change; setPending(change); active.current = true; setBusy(true); setError('');
    try {
      const receipt = change.kind === 'create' ? await createBoard(projectId, token, change.body)
        : change.kind === 'update' ? await updateBoard(projectId, change.boardId, token, change.body) : await orderBoards(projectId, token, change.body);
      finish(receipt, change);
    } catch (failure) {
      if (!mounted.current) return;
      const issue = failure as ProjectRequestError;
      if (issue.status >= 400 && issue.status < 500) {
        sessionStorage.removeItem(key); current.current = null; setPending(null); setError(issue.message);
        if (issue.status === 409) reload();
      } else await check(change); // Read-only recovery; never automatically POST again.
    } finally { active.current = false; if (mounted.current) setBusy(false); }
  }
  async function inspect(retry = false) {
    const original = current.current;
    if (!original || active.current) return;
    active.current = true; setBusy(true);
    try {
      try { finish(await readBoardReceipt(projectId, original.body.requestId), original); }
      catch (failure) {
        if (retry && (failure as ProjectRequestError).status === 404) { active.current = false; await perform(original); }
        else await check(original);
      }
    } finally { active.current = false; if (mounted.current) setBusy(false); }
  }
  return { pending, busy, error, perform, check: () => inspect(), retry: () => inspect(true) };
}
