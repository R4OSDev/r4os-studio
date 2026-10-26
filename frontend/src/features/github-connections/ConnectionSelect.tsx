import { useCallback, useEffect, useRef, useState } from 'react';
import type { GitHubConnection } from '../../../../shared/github-connections';
import type { GitHubAccount } from '../../../../shared/project-github';
import { loadConnections, request } from './api';

export function ConnectionSelect({ value, changed, disabled = false }: {
  value: GitHubAccount | null; changed: (value: GitHubAccount | null) => void; disabled?: boolean;
}) {
  const [connections, setConnections] = useState<GitHubConnection[]>([]), [csrf, setCsrf] = useState('');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const invalidate = useCallback(() => { generation.current++; }, []);
  useEffect(() => {
    let active = true;
    void loadConnections().then((v) => { if (active) { setConnections(v.connections); setCsrf(v.csrfToken); } }).catch((e: Error) => { if (active) setError(e.message); });
    return () => { active = false; invalidate(); };
  }, [invalidate]);
  async function choose(id: string) {
    const current = ++generation.current; changed(null); setError('');
    if (!id) return;
    const connection = connections.find((v) => v.id === id); if (!connection) return;
    setBusy(true);
    try { const account = await request<GitHubAccount>('POST', '/' + id + '/account', { tokenRevision: connection.tokenRevision }, csrf);
      if (generation.current === current) changed(account);
    } catch (e) { if (generation.current === current) setError((e as Error).message); }
    finally { if (generation.current === current) setBusy(false); }
  }
  return <div><label htmlFor="github-connection">GitHub connection</label>
    <select id="github-connection" value={value?.connectionId ?? ''} disabled={disabled || busy || !csrf} onChange={(e) => void choose(e.target.value)}>
      <option value="">None / Local only</option>{connections.map((v) => <option key={v.id} value={v.id}>{v.name}{v.lastTest?.status === 'success' ? ' · @' + v.lastTest.login : ' · Account not verified'}</option>)}
    </select>{busy && <p role="status">Verifying account…</p>}{error && <p role="alert">{error}</p>}
    {value && <p role="status">{value.connectionName} · @{value.login}. Repository creation permission will be checked when creating the repository.</p>}
  </div>;
}
