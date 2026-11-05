import type { ConnectionLimits } from '../../../../../shared/connection-limits';
import { ClaudeLimitsView } from './ClaudeLimitsView';
import { OpenRouterLimitsView } from './OpenRouterLimitsView';

export function ConnectionLimitsView({ sample, loading, busy, error, pending, notFound, refresh, recover, compact = false, enabled = true, kind }: {
  sample: ConnectionLimits | null; loading: boolean; busy: boolean; error: string; pending: boolean; notFound: boolean;
  refresh: () => void; recover: () => void; compact?: boolean; enabled?: boolean;
  kind?: string;
}) {
  const router = kind === 'openrouter' || !!sample?.openrouter;
  return <section aria-label={router ? 'Account key limits' : 'Account subscription limits'}>
    {(error || sample?.error) && <p className="provider-alert" role="status">{error || sample?.error}</p>}
    {loading && <p>Loading account limits…</p>}
    {router ? <OpenRouterLimitsView sample={sample} /> : <ClaudeLimitsView sample={sample?.claude ?? null} revision={sample?.configRevision} reportedState={sample?.state} compact={compact} />}
    <div className="provider-actions"><button type="button" className="button-secondary" disabled={busy || !enabled} onClick={refresh}>{busy ? 'Checking…' : pending ? notFound ? 'Retry original check' : 'Read original check' : router ? 'Refresh key limits' : 'Refresh subscription limits'}</button>
      {pending && !notFound && <button type="button" className="button-secondary" disabled={busy} onClick={recover}>Read original result</button>}</div>
  </section>;
}
