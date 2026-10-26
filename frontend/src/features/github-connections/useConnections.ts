import { useCallback, useEffect, useState } from 'react';
import type { GitHubConnection, GitHubConnectionChange, GitHubConnectionInput, GitHubTestResult } from '../../../../shared/github-connections';
import { loadConnections, request } from './api';
import type { GitHubProjectReference } from '../../../../shared/project-github';

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
  const references = (connection: GitHubConnection) => request<{ projects: GitHubProjectReference[] }>('GET', '/' + connection.id + '/projects');
  const remove = async (connection: GitHubConnection, confirmProjects: boolean) => {
    await request('DELETE', '/' + connection.id, { revision: connection.revision, ...(confirmProjects ? { confirmProjects: true } : {}) }, csrf);
    setConnections((previous) => previous.filter((v) => v.id !== connection.id));
  };
  const testDraft = (token: string) => request<GitHubTestResult>('POST', '/test', { token }, csrf);
  const testStored = async (connection: GitHubConnection) => {
    const result = await request<GitHubConnection>('POST', '/' + connection.id + '/test', { revision: connection.revision }, csrf);
    setConnections((previous) => previous.map((v) => v.id === result.id && v.tokenRevision === result.tokenRevision ? result : v));
    return result;
  };
  return { connections, error, loading: loading || (active && !csrf && !error), ready: !!csrf, refresh, save, remove, references, testDraft, testStored };
}
export type ConnectionsApi = ReturnType<typeof useConnections>;
