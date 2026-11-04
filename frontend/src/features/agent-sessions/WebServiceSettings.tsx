import { useEffect, useState } from 'react';
import { useSessionApi } from './api';
import { ProjectField } from '../projects/ProjectField';

type Settings = { revision: number; searchEndpoint: string | null };
export function WebServiceSettings({ token }: { token: string }) {
  const { request } = useSessionApi();
  const [current, setCurrent] = useState<Settings | null>(null), [endpoint, setEndpoint] = useState('');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<(Settings & { requestId: string }) | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void request<Settings>('/web-service', '', 'GET', undefined, controller.signal).then(value => {
      if (!controller.signal.aborted) { setCurrent(value); setEndpoint(value.searchEndpoint ?? ''); }
    }).catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [request]);
  async function save() {
    if (!current || busy) return;
    setBusy(true); setError('');
    try {
      const original = pending ?? { requestId: crypto.randomUUID(), revision: current.revision, searchEndpoint: endpoint.trim() || null };
      setPending(original);
      const value = await request<Settings>('/web-service', token, 'PUT', original);
      setPending(null); setCurrent(value); setEndpoint(value.searchEndpoint ?? '');
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="agent-web-service">
    <ProjectField id="studio-web-endpoint" label="SearXNG search endpoint"><input id="studio-web-endpoint" type="url" aria-label="SearXNG search endpoint" value={endpoint} disabled={!current || busy || !!pending} onChange={event => setEndpoint(event.target.value)} placeholder="https://search.example/search" /></ProjectField>
    <button className="project-reload" type="button" disabled={!current || busy || endpoint.trim() === (current.searchEndpoint ?? '')} onClick={() => { void save(); }}>{busy ? 'Saving…' : pending ? 'Check original save' : 'Save search service'}</button>
    <p className="agent-terminal-hint">Host-wide setting for future runs. Search requires your configured SearXNG JSON service; an empty endpoint leaves search unavailable. Public page fetch works independently. Saving starts no search or installation.</p>
    {error && <p role="alert">{error}</p>}
  </div>;
}
