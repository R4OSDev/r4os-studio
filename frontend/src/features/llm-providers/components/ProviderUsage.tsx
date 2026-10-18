import { useCallback, useEffect, useRef, useState } from 'react';
import type { ProviderUsage as Usage, ResetOutcome, ResetResult } from '../../../../../shared/llm-providers.js';
import type { ProviderApi } from '../useProviders';
import { dateTime } from '../usage-format';
import { UsageWindow } from './UsageWindow';

type Attempt = { key: string; submitted: boolean };
const outcomes: Record<ResetOutcome, string> = {
  reset: 'One reset was used.',
  alreadyRedeemed: 'This reset attempt was already completed. No additional reset was used.',
  nothingToReset: 'OpenAI reports no eligible usage window to reset. No reset was used.',
  noCredit: 'OpenAI reports no available resets for this account.',
};

function restoreAttempt(storageKey: string): Attempt | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(storageKey) ?? 'null') as Attempt | null;
    return value && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(value.key) && typeof value.submitted === 'boolean' ? value : null;
  } catch { return null; }
}

function newKey(): string {
  // getRandomValues also works on the private HTTP LAN origin, unlike randomUUID.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function ProviderUsage({ id, accountEmail, request }: { id: string; accountEmail: string | null; request: ProviderApi['request'] }) {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now);
  const [confirming, setConfirming] = useState(false);
  const [resetting, setResetting] = useState(false);
  const storageKey = `r4os-studio:reset-attempt:${id}:${accountEmail ?? ''}`;
  const [attempt, setAttempt] = useState<Attempt | null>(() => restoreAttempt(storageKey));
  const alive = useRef(false);
  const reading = useRef(false);
  const consuming = useRef(false);
  const generation = useRef(0);
  const path = `/${id}/usage`;

  const refresh = useCallback((force = false) => {
    if (reading.current || consuming.current) return Promise.resolve();
    reading.current = true;
    const currentGeneration = generation.current;
    return request<{ usage: Usage }>(`${path}${force ? '?refresh=true' : ''}`).then((result) => {
      if (alive.current && currentGeneration === generation.current) { setUsage(result.usage); setError(null); setNow(Date.now()); }
    }).catch(() => {
      if (alive.current && currentGeneration === generation.current) setError('Usage could not be refreshed. Previously loaded values may be out of date.');
    }).finally(() => {
      reading.current = false;
      if (alive.current) setLoading(false);
    });
  }, [path, request]);

  useEffect(() => {
    alive.current = true;
    void refresh();
    const timer = setInterval(() => {
      setNow(Date.now());
      if (!document.hidden) void refresh();
    }, 60_000);
    const visible = () => { if (!document.hidden) void refresh(); };
    document.addEventListener('visibilitychange', visible);
    return () => { alive.current = false; clearInterval(timer); document.removeEventListener('visibilitychange', visible); };
  }, [refresh]);

  function saveAttempt(next: Attempt) {
    try { sessionStorage.setItem(storageKey, JSON.stringify(next)); }
    catch { throw new Error('Browser session storage is required to safely retry a reset. Enable it before continuing.'); }
    setAttempt(next);
  }

  function clearAttempt() {
    try { sessionStorage.removeItem(storageKey); } catch { /* Keeping an old key is safer than repeating with a new one. */ }
    setAttempt(null);
  }

  function begin() {
    try {
      saveAttempt(attempt ?? { key: newKey(), submitted: false });
      setConfirming(true); setMessage(null); setError(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'A reset attempt could not be prepared.'); }
  }

  function cancel() {
    if (!attempt?.submitted) clearAttempt();
    setConfirming(false);
  }

  async function consume() {
    if (!attempt || consuming.current) return;
    consuming.current = true;
    generation.current++;
    setResetting(true); setError(null); setMessage(null);
    try {
      // Persist before sending; retries and reloads reuse this exact logical attempt.
      saveAttempt({ ...attempt, submitted: true });
      const result = await request<ResetResult>(`${path}/resets`, 'POST', { confirm: true, idempotencyKey: attempt.key });
      if (!alive.current) return;
      clearAttempt(); setConfirming(false); setMessage(outcomes[result.outcome]);
      // The server refetches the authoritative limits instead of predicting new values.
      setUsage(result.usage);
      setNow(Date.now());
      if (!result.usage) setError('The reset result was confirmed, but usage could not be refreshed. Refresh usage separately.');
    } catch {
      if (alive.current) setError('The reset result could not be confirmed. Retry this same attempt; do not start another reset.');
    } finally {
      consuming.current = false;
      if (alive.current) setResetting(false);
    }
  }

  const resets = usage?.resetCredits;
  const count = resets?.availableCount;
  const canUse = (count !== undefined && count !== null && count > 0) || !!attempt?.submitted;
  return <section className="provider-usage" aria-labelledby={`usage-title-${id}`}>
    <div className="usage-heading"><div><h3 id={`usage-title-${id}`}>Usage limits</h3><p>Current Codex subscription usage</p></div><button className="button-secondary" type="button" disabled={loading || resetting} onClick={() => { setLoading(true); void refresh(true); }}>{loading ? 'Refreshing…' : 'Refresh usage'}</button></div>
    {message && <p className="provider-alert" role="status">{message}</p>}
    {error && <p className="provider-alert" role="alert">{error}</p>}
    {!usage && loading && <p className="field-help" role="status">Loading usage limits…</p>}
    {usage && <>
      {usage.ordinaryUsageAllowed === false && <p className="provider-alert" role="status">OpenAI currently reports that ordinary included usage is unavailable.</p>}
      <div className="usage-limits">{usage.limits.map((limit, index) => <article className="usage-bucket" key={`${limit.id}-${index}`}>
        <div className="usage-bucket-heading"><h4>{limit.name}</h4>{limit.limitReached && <span className="provider-status">Limit reached</span>}</div>
        <div className="usage-windows">
          {limit.primary && <UsageWindow window={limit.primary} label="Primary window" bucket={limit.name} now={now} />}
          {limit.secondary && <UsageWindow window={limit.secondary} label="Secondary window" bucket={limit.name} now={now} />}
        </div>
        {!limit.primary && !limit.secondary && <p className="field-help">OpenAI did not report a quota window for this limit.</p>}
      </article>)}</div>
      <p className="usage-updated">Last checked: <time dateTime={usage.fetchedAt}>{dateTime(usage.fetchedAt)}</time>. Updates every minute while this page is visible.</p>
    </>}
    {(usage || attempt?.submitted) && <div className="usage-resets">
        <div className="usage-heading"><div><h3>Available resets</h3><p>Earned resets, separate from scheduled quota resets</p></div><strong className="reset-count">{count ?? 'Not reported'}</strong></div>
        {!resets && <p className="field-help">OpenAI did not report reset availability for this account.</p>}
        {resets && count === 0 && <p className="field-help">No resets are currently available.</p>}
        {resets && resets.credits === null && <p className="field-help">Individual reset details were not reported.</p>}
        {resets?.credits && resets.credits.length > 0 && <ul className="reset-credit-list">{resets.credits.map((credit, index) => <li key={`${credit.id}-${index}`}>
          <div><strong>{credit.title ?? 'Rate-limit reset'}</strong><span className="provider-status">{credit.status}</span></div>
          {credit.description && <p>{credit.description}</p>}
          <dl><div><dt>Granted</dt><dd>{dateTime(credit.grantedAt)}</dd></div><div><dt>Expires</dt><dd>{credit.expiresAt ? dateTime(credit.expiresAt) : 'No expiry reported'}</dd></div></dl>
        </li>)}</ul>}
        {resets?.credits && count !== null && count !== undefined && count > resets.credits.length && <p className="field-help">OpenAI returned details for {resets.credits.length} of {count} available resets. The available count is authoritative.</p>}
        {attempt?.submitted && <p className="provider-alert" role="status">A previous reset attempt is unconfirmed. Retrying reuses its request ID.</p>}
        {confirming ? <div className="reset-confirmation" role="group" aria-label="Confirm reset usage">
          <h4>{attempt?.submitted ? 'Retry this reset attempt?' : 'Use one available reset?'}</h4>
          <p>OpenAI decides which usage windows are eligible. Applying a reset consumes one earned reset. This cannot be undone in Studio.</p>
          <div className="provider-actions"><button className="button-primary" type="button" disabled={resetting} onClick={() => void consume()}>{resetting ? 'Confirming reset…' : attempt?.submitted ? 'Retry same reset' : 'Confirm reset'}</button><button className="button-secondary" type="button" disabled={resetting} onClick={cancel}>Cancel</button></div>
        </div> : <div className="provider-actions"><button className="button-secondary" type="button" disabled={!canUse || resetting} onClick={begin}>{attempt?.submitted ? 'Retry previous reset' : 'Use a reset'}</button></div>}
        <p className="field-help">Viewing and refreshing usage never uses a reset.</p>
      </div>}
  </section>;
}
