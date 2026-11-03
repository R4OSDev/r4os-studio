import type { ZaiSubscriptionLimits } from '../../../../../shared/zai-subscription';

const amount = (value: number | null) => value === null ? 'Unknown' : new Intl.NumberFormat('en-GB', { maximumFractionDigits: 4 }).format(value);
const date = (value: string) => new Date(value).toLocaleString('en-GB', { timeZoneName: 'short' });
export function ZaiLimitsView({ sample, loading = false, busy = false, error = '', pending = false, notFound = false, enabled = true, compact = false, refresh, recover }: {
  sample: ZaiSubscriptionLimits | null; loading?: boolean; busy?: boolean; error?: string; pending?: boolean; notFound?: boolean;
  enabled?: boolean; compact?: boolean; refresh: () => void; recover: () => void;
}) {
  const state = sample?.holds?.length ? 'Held' : loading ? 'Loading' : sample?.state === 'current' ? 'Reported' : sample?.state === 'stale' ? 'Stale' : 'Unknown';
  const content = <>
    <p className="zai-limits-heading">Z.AI · GLM Coding Plan{sample?.level ? ' · ' + sample.level : ''} · {state}</p>
    {sample?.holds?.map((hold, index) => <p className="provider-alert" role="status" key={index}>{hold.model ? hold.model + ': ' : ''}{hold.reason}{hold.resetAt ? ' Reset ' + date(hold.resetAt) + '.' : ' Reset time unknown.'} Continue explicitly after access is restored.</p>)}
    {(error || sample?.error) && <p className="provider-alert" role="status">{error || sample?.error}</p>}
    {!sample?.limits.length && <p>{loading ? 'Loading subscription limits…' : 'No subscription allowance has been reported. Missing data does not mean zero remaining.'}</p>}
    {sample?.limits.map(window => <div className="zai-limit-row" key={window.id}>
      <strong>{window.window} · {window.unit === 'unknown' ? 'Reported allowance' : window.unit}</strong>
      <p>Used {amount(window.used)} of {amount(window.maximum)} · Remaining {amount(window.remaining)}</p>
      {window.percentage !== null && <><progress max={100} value={Math.min(100, window.percentage)} aria-label={`${window.window} ${window.unit} used`} /><span> {amount(window.percentage)}% used</span></>}
      <p>{window.resetAt ? 'Reset ' + date(window.resetAt) : 'Reset time unknown'}</p>
    </div>)}
    {sample?.checkedAt && <p>Observed {date(sample.checkedAt)} · Source: Z.AI subscription monitoring.</p>}
    <p>Account-wide allowance includes usage outside Studio. Session statistics show this session’s reported token usage separately.</p>
    <p>Refreshing limits or reaching a reset does not resume a session or Goal. Studio does not enable paid extra usage.</p>
    <div className="zai-limit-actions">
      <button type="button" className="button-secondary" disabled={busy || !enabled || !sample} onClick={refresh}>{busy ? 'Checking…' : pending ? notFound ? 'Retry original check' : 'Read original check' : 'Refresh subscription limits'}</button>
      {pending && !notFound && !busy && <button type="button" className="button-secondary" onClick={recover}>Check original result</button>}
    </div>
    {pending && <p role="status">The original limit check is pending. Its request is preserved on reload.</p>}
  </>;
  if (compact) return <details className="zai-limits compact"><summary>Z.AI subscription · {state}</summary>{content}</details>;
  return <section className="zai-limits" aria-label="Z.AI subscription limits">{content}</section>;
}
