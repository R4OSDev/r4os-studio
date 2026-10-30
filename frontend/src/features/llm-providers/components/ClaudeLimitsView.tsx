import { useEffect, useState } from 'react';
import type { ClaudeSubscriptionLimits, ClaudeRateObservation } from '../../../../../shared/claude-subscription';

function percent(value: number | null) { return value === null ? 'Unknown' : `${Math.round(value * 10) / 10}%`; }
function countdown(reset: string, clock: number) {
  const seconds = Math.max(0, Math.ceil((Date.parse(reset) - clock) / 1000));
  if (!Number.isFinite(seconds)) return 'Unknown';
  const days = Math.floor(seconds / 86400), hours = Math.floor(seconds % 86400 / 3600), minutes = Math.floor(seconds % 3600 / 60);
  return `${days ? days + 'd ' : ''}${hours}h ${minutes}m ${seconds % 60}s`;
}

/** Native quota percentages and their receipt time; no token-based estimates. */
export function ClaudeLimitsView({ sample, compact = false, revision, observation }: { sample: ClaudeSubscriptionLimits | null; compact?: boolean; revision?: number; observation?: ClaudeRateObservation | null }) {
  const [clock, setClock] = useState(Date.now);
  useEffect(() => {
    const tick = () => setClock(Date.now());
    const immediate = setTimeout(tick, 0), timer = setInterval(tick, 1000);
    return () => { clearTimeout(immediate); clearInterval(timer); };
  }, [sample?.receivedAt, observation?.receivedAt]);
  const currentClock = clock;
  const age = sample ? currentClock - Date.parse(sample.receivedAt) : NaN;
  const fresh = Number.isFinite(age) && age >= 0 && age <= 60000 && (revision === undefined || revision === sample?.providerRevision);
  const state = !sample || sample.coverage === 'unavailable' ? 'Unavailable' : !fresh ? 'Stale' : sample.coverage === 'partial' ? 'Partial' : 'Reported';
  const formatter = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'long' });
  const nativeMeters = sample?.windows.filter(row => row.id.startsWith('native-meter-')) ?? [];
  const renderWindow = (row: ClaudeSubscriptionLimits['windows'][number]) => <div className="claude-limit-row" key={row.id}>
    <div><span>{row.label}</span><span>{percent(row.usedPercent)} used · {percent(row.remainingPercent)} remaining</span></div>
    {row.usedPercent !== null && <progress max={100} value={row.usedPercent} aria-label={`${row.label} used`} />}
    <p>{row.resetsAt ? <>Reset {formatter.format(new Date(row.resetsAt))} · {formatter.resolvedOptions().timeZone} · {countdown(row.resetsAt, currentClock)}</> : 'Reset time unknown'}</p>
  </div>;
  const content = <>
    <p className="claude-limits-heading">{sample?.plan?.toUpperCase() || 'Claude subscription'} · {state}</p>
    {observation && <p>Native quota event: {observation.status.replaceAll('_', ' ')} · {observation.scope || 'Scope unknown'} · {percent(observation.usedPercent)} used.
      {' '}Received {formatter.format(new Date(observation.receivedAt))}.{observation.resetsAt && <> Reset {formatter.format(new Date(observation.resetsAt))} · {formatter.resolvedOptions().timeZone} · {countdown(observation.resetsAt, currentClock)}.</>}</p>}
    {!sample && <p>Subscription limits have not been checked.</p>}
    {sample?.windows.filter(row => !row.id.startsWith('native-meter-')).map(renderWindow)}
    {nativeMeters.length > 0 && <details><summary>Additional reported limits</summary>{nativeMeters.map(renderWindow)}</details>}
    {sample && <p>{sample.message} Received {formatter.format(new Date(sample.receivedAt))}. Source: native Claude usage control.</p>}
    <p>Paid extra usage: {sample?.extraUsageEnabled === false ? 'Disabled in the reported account state' : sample?.extraUsageEnabled === true ? 'Enabled — model use blocked' : 'Unconfirmed — model use blocked'}.</p>
    <p>Limits are shared with other Claude surfaces for this account. A reset countdown does not resume work.</p>
  </>;
  if (compact) return <details className="claude-limits compact"><summary>Claude subscription · {state}{observation ? ' · Native quota ' + observation.status.replaceAll('_', ' ') : ''}{sample?.windows.find(w => w.id === 'five_hour') ? ' · 5h ' + percent(sample.windows.find(w => w.id === 'five_hour')!.usedPercent) + ' used' : ''}</summary>{content}</details>;
  return <section className="claude-limits" aria-label="Claude subscription limits">{content}</section>;
}
