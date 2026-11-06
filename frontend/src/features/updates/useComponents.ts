import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { ComponentsProgress, ComponentsStatus } from '../../../../shared/components';

type Driver = { load: (force: boolean) => Promise<void>; receive: (value: ComponentsStatus) => void };
export function useComponents(onReceive?: (value: ComponentsStatus) => void) {
  const [status, setStatus] = useState<ComponentsStatus | null>(null), [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const active = useRef<Driver | null>(null), callback = useRef(onReceive);
  useLayoutEffect(() => { callback.current = onReceive; });
  const refresh = useCallback(async () => { await active.current?.load(true); }, []);
  const receive = useCallback((value: ComponentsStatus) => active.current?.receive(value), []);
  useEffect(() => {
    let live = true, value: ComponentsStatus | null = null, epoch = 0, lastFull = 0;
    let pending: Promise<void> | null = null, queued = false, controller: AbortController | null = null, timer = 0;
    function accept(next: ComponentsStatus, notify = true) {
      if (!next.enabled && value?.enabled) throw new Error(next.message);
      value = next; setStatus(next); setError(''); if (notify) callback.current?.(next);
    }
    function schedule() {
      window.clearTimeout(timer);
      if (!live) return;
      timer = window.setTimeout(() => { if (document.hidden) schedule(); else void load(false); }, value?.job?.phase === 'working' ? 2000 : value?.features?.componentProgress === 1 ? 15000 : 30000);
    }
    async function load(force: boolean): Promise<void> {
      if (pending) { if (force) queued = true; return pending; }
      queued = force; window.clearTimeout(timer);
      pending = (async () => {
        do {
          const forced = queued; queued = false;
          const current = epoch, full = forced || !value || value.features?.componentProgress !== 1 || Date.now() - lastFull >= 30000;
          controller = new AbortController(); const signal = controller.signal;
          if (full) setRefreshing(true);
          try {
            const response = await fetch('/api/updates/components' + (full ? forced ? '?refresh=true' : '' : '/progress'), { cache: 'no-store', signal });
            if (!response.ok) {
              if (!full && [403, 404, 409].includes(response.status)) queued = true;
              throw new Error('Component versions could not be verified. Your selection was retained.');
            }
            if (full) {
              const next = await response.json() as ComponentsStatus;
              if (live && current === epoch && !signal.aborted) { accept(next); lastFull = Date.now(); }
            } else {
              const progress = await response.json() as ComponentsProgress;
              if (!live || current !== epoch || signal.aborted || !value) continue;
              const changed = progress.generation !== value.generation || progress.profileRevision !== value.profileRevision
                || progress.inventoryRevision !== (value.inventory?.revision ?? null)
                || (value.job?.phase === 'working' && progress.job?.phase !== 'working');
              if (changed) {
                queued = true; setRefreshing(true);
              }
              // A new profile binding must never be combined with old inventory.
              accept({ ...value, job: progress.job }, !changed);
            }
          } catch (cause) {
            if (live && current === epoch && !signal.aborted) setError((cause as Error).message);
          }
        } while (live && queued);
      })().finally(() => { pending = null; if (live) { setRefreshing(false); schedule(); } });
      return pending;
    }
    const driver: Driver = { load, receive(next) {
      epoch++; controller?.abort();
      accept({ ...next, csrfToken: value?.csrfToken || next.csrfToken }); lastFull = Date.now();
      schedule();
    } };
    active.current = driver;
    const initial = window.setTimeout(() => void load(false), 0);
    const wake = () => { if (!document.hidden) void load(false); };
    window.addEventListener('focus', wake); document.addEventListener('visibilitychange', wake);
    return () => {
      live = false; epoch++; controller?.abort();
      if (active.current === driver) active.current = null;
      window.clearTimeout(initial); window.clearTimeout(timer);
      window.removeEventListener('focus', wake); document.removeEventListener('visibilitychange', wake);
    };
  }, []);
  return { status, error, setError, refreshing, refresh, receive };
}
