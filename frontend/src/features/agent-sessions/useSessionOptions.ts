import { useEffect, useState } from 'react';
import type { SessionOptions } from '../../../../shared/agent-sessions';
import { sessionPath, useSessionApi } from './api';
import { watchSessionReads } from './sessionReads';
import { watchVisible } from './sessionActivity';

export function useSessionOptions(ownerId: string) {
  const { request, base } = useSessionApi(), path = sessionPath(ownerId) + '/options', key = base + path;
  const [state, setState] = useState<{ key: string; value: SessionOptions | null; error: string }>({ key, value: null, error: '' });
  useEffect(() => {
    const controller = new AbortController(); let loading = false, dirty = false, timer: number | undefined;
    async function load() {
      if (controller.signal.aborted || document.hidden) return;
      if (loading) { dirty = true; return; }
      loading = true; dirty = false; window.clearTimeout(timer);
      try {
        const value = await request<SessionOptions>(path, '', 'GET', undefined, controller.signal);
        if (!controller.signal.aborted) setState({ key, value, error: '' });
      } catch (error) {
        if (!controller.signal.aborted && (error as Error).name !== 'AbortError') setState({ key, value: null, error: (error as Error).message });
      } finally {
        loading = false;
        if (!controller.signal.aborted && !document.hidden) {
          if (dirty) void load(); else timer = window.setTimeout(() => void load(), 30000);
        }
      }
    }
    const invalidate = () => { setState({ key, value: null, error: '' }); void load(); };
    const stopInvalidation = watchSessionReads(invalidate, 'options'), stopVisible = watchVisible(() => void load());
    void load();
    return () => { controller.abort(); window.clearTimeout(timer); stopInvalidation(); stopVisible(); };
  }, [key, path, request]);
  return state.key === key ? { options: state.value, error: state.error } : { options: null, error: '' };
}
