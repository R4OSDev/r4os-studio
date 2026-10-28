import { useCallback, useEffect, useRef, useState } from 'react';
import type { EnvironmentNotePage } from '../../../../shared/environment-notes';
import { sessionPath, useSessionApi } from './api';
export type NoteQuery = Record<string, string | number>;
type Summary = { key: string; revision: number; count: number };
export function useEnvironmentNotes(ownerId: string, sessionId: string, reauth: () => Promise<void>) {
  const { request, base } = useSessionApi(), path = sessionPath(ownerId, sessionId) + '/environment-notes', key = base + path;
  const [selection, setSelection] = useState<{ key: string; query: NoteQuery }>({ key, query: {} });
  const query = selection.key === key ? selection.query : {};
  const queryString = new URLSearchParams(Object.entries(query).map(([name, value]) => [name, String(value)])).toString();
  const [state, setState] = useState<{ key: string; query: string; page: EnvironmentNotePage | null; error: string }>({ key, query: '', page: null, error: '' });
  const [summary, setSummary] = useState<Summary>({ key, revision: -1, count: 0 });
  const minimum = useRef<Summary>({ key, revision: -1, count: 0 });
  const [nonce, setNonce] = useState(0), refresh = useCallback(() => setNonce(value => value + 1), []);
  const accept = useCallback((value: { revision: number; count: number }) => {
    if (!Number.isSafeInteger(value.revision) || value.revision < 0 || !Number.isInteger(value.count) || value.count < 0 || value.count > 200) return false;
    if (minimum.current.key === key && value.revision < minimum.current.revision) return false;
    const next = { key, revision: value.revision, count: value.count };
    minimum.current = next; setSummary(next); return true;
  }, [key]);
  const observe = useCallback((value: { revision: number; count: number }) => { if (accept(value)) refresh(); }, [accept, refresh]);
  useEffect(() => {
    const controller = new AbortController(); let loading = false;
    async function load() {
      if (loading || document.hidden) return; loading = true;
      try {
        let value: EnvironmentNotePage;
        try { value = await request<EnvironmentNotePage>(path + '?' + queryString, '', 'GET', undefined, controller.signal); }
        catch (error) {
          if ((error as { status?: number }).status !== 403) throw error;
          await reauth(); value = await request<EnvironmentNotePage>(path + '?' + queryString, '', 'GET', undefined, controller.signal);
        }
        if (!controller.signal.aborted && accept(value)) setState({ key, query: queryString, page: value, error: '' });
      } catch (error) {
        if (!controller.signal.aborted) setState(previous => ({ key, query: queryString, page: previous.key === key && previous.query === queryString ? previous.page : null, error: (error as Error).message }));
      } finally { loading = false; }
    }
    void load(); const timer = window.setInterval(() => void load(), 4000);
    const visible = () => { if (!document.hidden) void load(); };
    window.addEventListener('focus', visible); window.addEventListener('online', visible); document.addEventListener('visibilitychange', visible);
    return () => { controller.abort(); window.clearInterval(timer); window.removeEventListener('focus', visible); window.removeEventListener('online', visible); document.removeEventListener('visibilitychange', visible); };
  }, [key, path, queryString, request, reauth, accept, nonce]);
  const page = state.key === key && state.query === queryString ? state.page : null;
  return { page, query, setQuery: (next: NoteQuery) => setSelection({ key, query: next }), path, key, refresh, observe,
    count: summary.key === key ? summary.count : 0,
    current: !!page && summary.key === key && page.revision >= summary.revision && !state.error,
    error: state.key === key ? state.error : '' };
}
