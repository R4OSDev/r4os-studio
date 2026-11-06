import { useCallback, useEffect, useRef, useState } from 'react';
import type { VmList } from '../../../../shared/virtual-machines.js';
import { loadVms, vmRequest, VmRequestError } from './api';
const empty: VmList = { vms: [], images: [], defaultImageId: null, csrfToken: '', available: false, networkAvailable: false };
type Reader = { live: boolean; authEpoch: number; controller?: AbortController; load: (force: boolean) => Promise<void> };
export function useVms(enabled: boolean) {
  const [data, setData] = useState<VmList>(empty), [error, setError] = useState(''), [loading, setLoading] = useState(true);
  const active = useRef<Reader | null>(null);
  const reload = useCallback(async () => { await active.current?.load(true); }, []);
  useEffect(() => {
    if (!enabled) return;
    let pending: Promise<void> | null = null, queued = false, forcing = false;
    const reader: Reader = { live: true, authEpoch: 0, load(force) {
      if (pending) { if (force) queued = true; return pending; }
      queued = force;
      pending = (async () => {
        do {
          forcing = queued; queued = false;
          const epoch = reader.authEpoch, controller = new AbortController(); reader.controller = controller;
          try {
            const result = await loadVms(forcing, controller.signal);
            if (reader.live && epoch === reader.authEpoch) { setData(result); setError(''); }
          } catch (cause) {
            if (reader.live && !controller.signal.aborted && epoch === reader.authEpoch)
              setError(cause instanceof Error ? cause.message : 'VMs could not be loaded.');
          }
        } while (reader.live && queued);
      })().finally(() => { pending = null; if (reader.live) setLoading(false); });
      return pending;
    } };
    active.current = reader;
    const initial = window.setTimeout(() => { setData(empty); setError(''); setLoading(true); void reader.load(true); }, 0);
    const timer = window.setInterval(() => { if (!document.hidden) void reader.load(false); }, 4000);
    return () => {
      reader.live = false; reader.controller?.abort();
      if (active.current === reader) active.current = null;
      window.clearTimeout(initial); window.clearInterval(timer);
    };
  }, [enabled]);
  return { ...data, error, loading, reload,
    request: async <T,>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal) => {
      const reader = active.current;
      try { return await vmRequest<T>(path, data.csrfToken, method, body, signal); }
      catch (cause) {
        if (cause instanceof VmRequestError && cause.status === 403 && reader?.live && active.current === reader) {
          reader.authEpoch++; reader.controller?.abort(); setData(old => ({ ...old, csrfToken: '' }));
          void reader.load(true);
        }
        throw cause;
      }
    } };
}
export type VmApi = ReturnType<typeof useVms>;
