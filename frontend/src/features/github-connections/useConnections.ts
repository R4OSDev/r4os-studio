import { useCallback, useEffect, useState } from 'react';
import type { GitHubConnection, GitHubConnectionChange, GitHubConnectionInput } from '../../../../shared/github-connections';
import { loadConnections, request } from './api';

export function useConnections(active: boolean) {
  const [connections, setConnections] = useState<GitHubConnection[]>([]);
  const [csrf, setCsrf] = useState(''), [error, setError] = useState(''), [loading, setLoading] = useState(false);
  const refresh = useCallback(async () => {
    setLoading(true);
    try { const result = await loadConnections(); setConnections(result.connections); setCsrf(result.csrfToken); setError(''); return result; }
    catch (cause) { setError((cause as Error).message); throw cause; }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    let cancelled = false;
    if (active) void loadConnections().then((result) => {
      if (!cancelled) { setConnections(result.connections); setCsrf(result.csrfToken); setError(''); }
    }).catch((cause: Error) => { if (!cancelled) setError(cause.message); });
    return () => { cancelled = true; };
  }, [active]);
  const save = async (input: GitHubConnectionInput | GitHubConnectionChange, id?: string) => {
    const saved = await request<GitHubConnection>(id ? 'PATCH' : 'POST', id ? '/' + id : '', input, csrf);
    setConnections((previous) => [...previous.filter((v) => v.id !== saved.id), saved].sort((a, b) => a.createdAt.localeCompare(b.createdAt)));
    return saved;
  };
  const remove = async (connection: GitHubConnection) => {
    await request('DELETE', '/' + connection.id, { revision: connection.revision }, csrf);
    setConnections((previous) => previous.filter((v) => v.id !== connection.id));
  };
  return { connections, error, loading: loading || (active && !csrf && !error), ready: !!csrf, refresh, save, remove };
}
export type ConnectionsApi = ReturnType<typeof useConnections>;
