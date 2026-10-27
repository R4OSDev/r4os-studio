import { useCallback, useEffect, useRef, useState } from 'react';
import type { RemoteHost, RemoteHostInput, RemoteHostChange, RemoteHostRemoval } from '../../../../shared/remote-hosts';
import { listHosts, createHost, updateHost, removeHost, checkHost, resetHostTrust } from './api';

export function useRemoteHosts(active: boolean) {
  const [hosts, setHosts] = useState<RemoteHost[]>([]), [token, setToken] = useState('');
  const [loading, setLoading] = useState(false), [error, setError] = useState('');
  const generation = useRef(0);
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const attempt = ++generation.current; setLoading(true);
    try {
      const result = await listHosts(signal);
      if (attempt === generation.current) { setHosts(result.hosts); setToken(result.csrfToken); setError(''); }
      return result;
    } catch (cause) { if (attempt === generation.current && !signal?.aborted) setError((cause as Error).message); throw cause; }
    finally { if (attempt === generation.current) setLoading(false); }
  }, []);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController(), attempt = ++generation.current;
    void listHosts(controller.signal).then((result) => {
      if (!controller.signal.aborted && attempt === generation.current) { setHosts(result.hosts); setToken(result.csrfToken); setError(''); }
    }).catch((cause: Error) => { if (!controller.signal.aborted && attempt === generation.current) setError(cause.message); })
      .finally(() => { if (!controller.signal.aborted && attempt === generation.current) setLoading(false); });
    return () => controller.abort();
  }, [active]);
  const accept = useCallback((saved: RemoteHost) => {
    generation.current++; setLoading(false);
    setHosts((previous) => [...previous.filter((h) => h.id !== saved.id), saved].sort((a, b) => a.name.localeCompare(b.name)));
  }, []);
  const save = async (input: RemoteHostInput | RemoteHostChange, id?: string) => {
    const saved = id ? await updateHost(id, input as RemoteHostChange, token) : await createHost(input as RemoteHostInput, token);
    accept(saved); return saved;
  };
  const remove = async (id: string, input: RemoteHostRemoval) => {
    await removeHost(id, input, token); generation.current++; setLoading(false); setHosts((previous) => previous.filter((h) => h.id !== id));
  };
  const check = (host: RemoteHost, requestId: string, revision = host.revision) => checkHost(host.id, { requestId, revision }, token);
  const resetTrust = async (host: RemoteHost, requestId: string, revision = host.revision) => { const saved = await resetHostTrust(host.id, { requestId, revision, confirm: true }, token); accept(saved); return saved; };
  return { hosts, loading: loading || (active && !token && !error), error, ready: !!token, refresh, save, remove, accept, check, resetTrust };
}
export type RemoteHostsApi = ReturnType<typeof useRemoteHosts>;
