import type { ConnectionLimits } from '../../../../../shared/connection-limits';
import { ClaudeLimitsView } from './ClaudeLimitsView';

export function ConnectionLimitsView({ sample, loading, busy, error, pending, notFound, refresh, recover, compact = false, enabled = true }: {
  sample: ConnectionLimits | null; loading: boolean; busy: boolean; error: string; pending: boolean; notFound: boolean;
  refresh: () => void; recover: () => void; compact?: boolean; enabled?: boolean;
}) {
  return <section aria-label="Account subscription limits">
    {(error || sample?.error) && <p className="provider-alert" role="status">{error || sample?.error}</p>}
    {loading && <p>Loading subscription limits…</p>}
    <ClaudeLimitsView sample={sample?.claude ?? null} revision={sample?.configRevision} reportedState={sample?.state} compact={compact} />
    <div className="provider-actions"><button type="button" className="button-secondary" disabled={busy || !enabled} onClick={refresh}>{busy ? 'Checking…' : pending ? notFound ? 'Retry original check' : 'Read original check' : 'Refresh subscription limits'}</button>
      {pending && !notFound && <button type="button" className="button-secondary" disabled={busy} onClick={recover}>Read original result</button>}</div>
  </section>;
}
