import { useCallback, useEffect, useState } from 'react';
import type { VmList } from '../../../../shared/virtual-machines.js';
import { loadVms, vmRequest } from './api';
export function useVms(enabled: boolean) {
  const [data, setData] = useState<VmList>({ vms: [], images: [], csrfToken: '', available: false });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    try { const result = await loadVms(); setData(result); setError(''); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'VMs could not be loaded.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    if (!enabled) return;
    const initial = window.setTimeout(() => void reload(), 0); const timer = window.setInterval(() => { if (!document.hidden) void reload(); }, 4000);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, [enabled, reload]);
  return { ...data, error, loading, reload,
    request: <T,>(path: string, method = 'GET', body?: unknown) => vmRequest<T>(path, data.csrfToken, method, body) };
}
export type VmApi = ReturnType<typeof useVms>;
