import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { ApiProvider } from '../../../../shared/api-providers';
import type { Provider } from '../../../../shared/llm-providers';
import type { ProviderApi } from '../llm-providers/useProviders';
import { useConnectionLimits } from '../llm-providers/useConnectionLimits';
import { connectionWindows, usageWindows } from '../llm-providers/limit-windows';
import type { LimitWindow } from '../llm-providers/limit-windows';
import { dateTime, percent } from '../llm-providers/usage-format';

type State = 'current' | 'stale' | 'unknown' | 'loading' | 'disconnected' | 'disabled' | 'unavailable';
const states: Record<State, string> = { current: 'Reported', stale: 'Stale', unknown: 'Unknown', loading: 'Loading', disconnected: 'Not connected', disabled: 'Disabled', unavailable: 'Unavailable' };
const timestamp = (value: string | null | undefined) => value && Number.isFinite(Date.parse(value)) ? value : null;

function LimitRing({ window, now }: { window: LimitWindow; now: number }) {
  const value = window.unlimited ? '∞' : window.remainingPercent === null ? '—' : percent(window.remainingPercent);
  const caption = window.unlimited ? 'unlimited' : window.remainingPercent === null ? 'not reported' : 'remaining';
  return <figure className="ai-limit-window" data-window-id={window.id}>
    <figcaption><strong>{window.label}</strong><span>{window.scope}</span></figcaption>
    <div className="ai-limit-ring" role="img" aria-label={`${window.label}: ${value} ${caption}`}>
      <svg viewBox="0 0 120 120" aria-hidden="true" focusable="false">
        <circle className={window.remainingPercent === null ? 'ai-limit-track' : 'ai-limit-used'} cx="60" cy="60" r="51" pathLength="100" />
        {window.remainingPercent !== null && <circle className="ai-limit-remaining" cx="60" cy="60" r="51" pathLength="100" strokeDasharray={`${window.remainingPercent} 100`} transform="rotate(-90 60 60)" />}
      </svg>
      <div className="ai-limit-value"><strong>{value}</strong><span>{caption}</span></div>
    </div>
    <p className="ai-limit-reset">{window.resetsAt ? <>Reset <time dateTime={window.resetsAt}>{dateTime(window.resetsAt)}</time></> : 'Reset time unknown'}</p>
    {window.resetsAt && Date.parse(window.resetsAt) <= now && <p className="ai-limit-notice">Reported reset has passed. Refresh limits for a new observation.</p>}
  </figure>;
}

function QuotaCard({ id, name, state, windows = [], observed, notice, children, now }: {
  id: string; name: string; state: State; windows?: LimitWindow[]; observed?: string | null; notice?: string | null; children?: ReactNode; now: number;
}) {
  const checked = timestamp(observed);
  return <article className="ai-limit-card" data-provider-id={id} data-state={state}>
    <header><h2>{name}</h2><span className="ai-limit-state">{states[state]}</span></header>
    {windows.length ? <div className="ai-limit-windows">{windows.map(window => <LimitRing key={window.id} window={window} now={now} />)}</div>
      : <p className="status-empty">{state === 'loading' ? 'Loading account limits…' : 'No account limits reported for this connection.'}</p>}
    {notice && <p className="ai-limit-notice" role="status">{notice}</p>}
    {checked && <p className="ai-limit-observed">Observed <time dateTime={checked}>{dateTime(checked)}</time></p>}
    {children && <div className="provider-actions">{children}</div>}
  </article>;
}

function NativeCard({ name, provider, api, enabled, now }: { name: string; provider: Provider; api: ProviderApi; enabled: boolean; now: number }) {
  const observation = api.usageByProvider[provider.id] ?? null;
  const connected = enabled && provider.status === 'connected' && !!provider.account;
  const [busy, setBusy] = useState(false);
  const inflight = useRef(false);
  async function refresh() {
    if (inflight.current || !connected) return;
    inflight.current = true; setBusy(true);
    try { await api.request(`/${provider.id}/usage?refresh=true`); }
    catch { /* The shared observation records the error and preserves its scope. */ }
    finally { inflight.current = false; setBusy(false); }
  }
  return <QuotaCard id={provider.id} name={name} now={now} state={!enabled ? 'disabled' : !connected ? 'disconnected' : observation?.state ?? 'loading'}
    windows={connected ? usageWindows(observation) : []} observed={connected ? observation?.usage?.fetchedAt : null} notice={observation?.error}>
    <button className="button-secondary" type="button" disabled={!connected || busy} onClick={() => void refresh()}>{busy ? 'Refreshing…' : 'Refresh limits'}</button>
  </QuotaCard>;
}

function ConnectionCard({ provider, api, now }: { provider: ApiProvider; api: ProviderApi; now: number }) {
  const limits = useConnectionLimits(provider, api);
  const enabled = provider.enabled && provider.keyConfigured;
  const sample = enabled ? limits.sample : null;
  const held = !!sample?.zai?.holds?.length;
  const notice = limits.error || sample?.error || (held ? 'Provider access is held. Refreshing limits does not resume a run.' : null);
  return <QuotaCard id={provider.id} name={provider.name} now={now} state={!provider.enabled ? 'disabled' : !provider.keyConfigured ? 'disconnected' : sample?.state ?? (api.connectionLimits[provider.id] === undefined ? 'loading' : 'unknown')}
    windows={connectionWindows(sample)} observed={sample?.checkedAt} notice={notice}>
    <button className="button-secondary" type="button" disabled={!enabled || limits.busy} onClick={() => void limits.refresh()}>
      {limits.busy ? 'Checking…' : limits.pending ? limits.notFound ? 'Retry original check' : 'Read original check' : 'Refresh limits'}
    </button>
  </QuotaCard>;
}

export function AiLimitsPanel({ api }: { api: ProviderApi }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    // Follow the existing shared observations; no timer per tile or new poller.
    const update = setTimeout(() => setNow(Date.now()), 0);
    return () => clearTimeout(update);
  }, [api.connectionLimits, api.usageByProvider]);
  return <section aria-label="AI provider limits">
    {(api.error || api.apiError || api.claudeError) && <p className="provider-alert" role="alert">{api.error || api.apiError || api.claudeError}<button type="button" onClick={() => void api.reload()}>Reload connections</button></p>}
    {api.loading && <p className="status-empty" role="status">Loading AI providers…</p>}
    {!api.loading && !api.providers.length && <p className="status-empty">No AI providers configured. Add a connection under System → Settings → AI Provider.</p>}
    <div className="ai-limits-grid">{api.providers.map(provider => {
      const native = api.nativeProviders.find(p => p.id === provider.id);
      if (native) return <NativeCard key={provider.id + ':' + (native.account?.scope ?? '')} name={provider.name} provider={native} api={api} now={now} enabled={provider.type !== 'api' || provider.enabled} />;
      if (provider.type === 'api' && ['claude-plan', 'openrouter', 'zai-coding-plan'].includes(provider.kind)) return <ConnectionCard key={provider.id} provider={provider} api={api} now={now} />;
      return <QuotaCard key={provider.id} id={provider.id} name={provider.name} now={now} state="unavailable" notice="Account limits are not available for this connection." />;
    })}</div>
  </section>;
}
