import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { ClaudeSubscriptionProvider, ClaudeProviderMutation, ClaudeRuntimeStatus, ClaudeAuthOperation, ClaudeAuthAction } from '../../../../../shared/claude-subscription';
import type { ProviderApi } from '../useProviders';
import type { ClaudeSubscriptionLimits, ClaudeModelCatalog } from '../../../../../shared/claude-subscription';
import { ClaudeLimitsView } from './ClaudeLimitsView';
import { providerRequestId, ProviderRequestError } from '../api';

const base = '/claude-subscriptions';
const uuid = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;
function original(key: string) { try { const value = sessionStorage.getItem(key); return value && uuid.test(value) ? value : null; } catch { return null; } }
function useRuntime(api: ProviderApi) {
  const [runtime, setRuntime] = useState<ClaudeRuntimeStatus | null>(null), [error, setError] = useState('');
  const request = api.request;
  useEffect(() => {
    let active = true;
    void request<ClaudeRuntimeStatus>(base + '/runtime').then(value => { if (active) setRuntime(value); })
      .catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : 'The native Claude runtime is unavailable.'); });
    return () => { active = false; };
  }, [request]);
  return { runtime, error };
}
function Runtime({ runtime, error }: ReturnType<typeof useRuntime>) {
  return <p className={error ? 'provider-alert' : 'field-help'} role={error ? 'alert' : undefined}>
    {error || (runtime ? `Native Claude Code ${runtime.version} · Agent SDK ${runtime.sdkVersion}` : 'Checking native runtime…')}</p>;
}

export function NewClaudeProvider({ api, created }: { api: ProviderApi; created: (id: string) => void }) {
  const [name, setName] = useState('Claude'), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const key = 'studio.claude.new.request';
  const [pending, setPending] = useState(() => original(key));
  const runtime = useRuntime(api);
  async function save(event?: FormEvent) {
    event?.preventDefault(); if (busy) return;
    setBusy(true); setError('');
    try {
      let result: ClaudeProviderMutation;
      if (pending) result = await api.request<ClaudeProviderMutation>(base + '/creation-requests/' + pending);
      else {
        const requestId = providerRequestId(); sessionStorage.setItem(key, requestId); setPending(requestId);
        result = await api.request<ClaudeProviderMutation>(base, 'POST', { requestId, name: name.trim() });
      }
      sessionStorage.removeItem(key); setPending(null); await api.reload();
      if (result.state === 'deleted') { setName(''); setError('The original Claude provider was removed. Enter a name to add a separate provider.'); }
      else created(result.provider.id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Read the original provider request before trying again.'); }
    finally { setBusy(false); }
  }
  return <form className="provider-form" onSubmit={event => void save(event)}>
    <p className="field-help">Claude Pro / Max subscription. Native sign-in follows after adding your provider.</p>
    <Runtime {...runtime} />
    <label htmlFor="claude-name">Display name</label><input id="claude-name" maxLength={80} autoComplete="off" required value={name} disabled={busy || !!pending} onChange={event => setName(event.target.value)} />
    {error && <p className="provider-alert" role="alert">{error}</p>}
    <div className="provider-actions"><button className="button-primary" disabled={busy || api.loading || !!api.error || !name.trim() || !pending && !runtime.runtime}>
      {busy ? 'Reading original result…' : pending ? 'Read original provider request' : 'Add Claude provider'}</button>
      {pending && !busy && <button type="button" className="button-secondary" onClick={() => { sessionStorage.removeItem(key); setPending(null); setError(''); }}>Start a separate provider request</button>}
    </div>
  </form>;
}

const labels = { 'not-connected': 'Not connected', connected: 'Connected', 'reauthentication-required': 'Check sign-in', unsupported: 'Subscription unavailable' };
export function ClaudeProviderDetails({ initial, api, removed }: { initial: ClaudeSubscriptionProvider; api: ProviderApi; removed: () => void }) {
  const [observed, setObserved] = useState<ClaudeSubscriptionProvider | null>(null), [operation, setOperation] = useState<ClaudeAuthOperation | null>(null);
  const provider = observed && observed.revision >= initial.revision ? observed : initial;
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [code, setCode] = useState(''), [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false), [confirmName, setConfirmName] = useState('');
  const key = `studio.claude.${initial.id}.auth.request`;
  const [pending, setPending] = useState(() => original(key));
  const running = operation?.state === 'pending' || operation?.state === 'waiting';
  const inflight = useRef(false), mounted = useRef(true);
  const generation = useRef(0);
  const runtime = useRuntime(api), request = api.request, reload = api.reload;
  const [limits, setLimits] = useState<ClaudeSubscriptionLimits | null>(null);
  const [catalog, setCatalog] = useState<ClaudeModelCatalog | null>(null);
  useEffect(() => {
    let active = true;
    void request<{ limits: ClaudeSubscriptionLimits | null }>(`${base}/${provider.id}/limits`)
      .then(value => { if (active) setLimits(value.limits); }).catch(() => { if (active) setLimits(null); });
    return () => { active = false; };
  }, [provider.id, provider.revision, request]);
  useEffect(() => {
    let active = true;
    void request<{ catalog: ClaudeModelCatalog | null }>(`${base}/${provider.id}/catalog`)
      .then(value => { if (active) setCatalog(value.catalog); }).catch(() => { if (active) setCatalog(null); });
    return () => { active = false; };
  }, [provider.id, provider.revision, request]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const accept = useCallback((value: ClaudeAuthOperation) => {
    if (!mounted.current) return;
    setOperation(value); setObserved(value.provider); setError('');
    if (value.limits) setLimits(value.limits);
    if ('catalog' in value) setCatalog(value.catalog ?? null);
    if (value.state === 'removed') { sessionStorage.removeItem(key); setPending(null); removed(); }
    if (!['pending', 'waiting'].includes(value.state)) { setCode(''); void reload(); }
  }, [key, reload, removed]);
  const read = useCallback(async () => {
    if (!pending || inflight.current) return;
    const sequence = ++generation.current;
    try { const value = await request<ClaudeAuthOperation>(`${base}/${initial.id}/auth-requests/${pending}`); if (sequence === generation.current) accept(value); }
    catch (cause) {
      if (mounted.current && sequence === generation.current) {
        setError(cause instanceof Error ? cause.message : 'The original sign-in result is unavailable.');
        if (cause instanceof ProviderRequestError && cause.status === 410) { await reload(); removed(); }
      }
    }
  }, [accept, initial.id, pending, request, reload, removed]);
  useEffect(() => { const timer = setTimeout(() => void read(), 0); return () => clearTimeout(timer); }, [read]);
  useEffect(() => {
    if (!pending || !running) return;
    const timer = setInterval(() => { if (!document.hidden) void read(); }, 1500);
    return () => clearInterval(timer);
  }, [pending, running, read]);
  async function act(action: ClaudeAuthAction | 'remove') {
    if (inflight.current) return;
    inflight.current = true; generation.current++; setBusy(true); setError(''); setCode(''); setConfirmDisconnect(false); setConfirmRemove(false);
    try {
      const requestId = providerRequestId(); sessionStorage.setItem(key, requestId); setPending(requestId);
      accept(await request<ClaudeAuthOperation>(`${base}/${provider.id}${action === 'remove' ? '' : '/auth'}`, action === 'remove' ? 'DELETE' : 'POST',
        { requestId, revision: provider.revision, ...(action === 'remove' ? { confirmName } : { action }) }));
    }
    catch (cause) {
      if (mounted.current) {
        setError(cause instanceof Error ? cause.message : 'Read the original authentication result.');
        if (cause instanceof ProviderRequestError && cause.status === 410) { await reload(); removed(); }
      }
    }
    finally { inflight.current = false; if (mounted.current) setBusy(false); }
  }
  async function control(action: 'code' | 'cancel', event?: FormEvent) {
    event?.preventDefault(); if (inflight.current || !pending) return;
    inflight.current = true; generation.current++; setBusy(true); setError(''); const input = code; setCode('');
    setOperation(value => value ? { ...value, authorizationUrl: undefined } : null);
    try { accept(await request<ClaudeAuthOperation>(`${base}/${provider.id}/auth-requests/${pending}/${action}`, 'POST', action === 'code' ? { code: input } : {})); }
    catch (cause) { if (mounted.current) setError(cause instanceof Error ? cause.message : 'Read the original sign-in result before continuing.'); }
    finally { inflight.current = false; if (mounted.current) setBusy(false); }
  }
  return <div className="provider-card">
    <div className="provider-card-heading"><div><h2>{provider.name}</h2><p>Claude subscription</p></div><span className={`provider-status ${provider.status === 'connected' ? 'connected' : ''}`}>{labels[provider.status]}</span></div>
    <Runtime {...runtime} />
    <ClaudeLimitsView sample={limits} revision={provider.revision} />
    <section className="claude-models" aria-label="Native Claude model catalog"><h3>Native model catalog</h3>
      <p className="field-help">{catalog ? `Native client metadata received ${new Date(catalog.receivedAt).toLocaleString()}.` : 'Read the native model catalog to enable text sessions for this account.'} A listed model is not a subscription entitlement or billing guarantee. Each send checks the native account and included usage.</p>
      {catalog?.models.map(model => <article key={model.id} className="claude-model-row"><strong>{model.name}</strong><code>{model.id}</code><p>{model.description}</p>
        <p>Effort: {model.efforts.map(value => value || 'Native default').join(' · ')}. Context window: Unknown. Image input: {model.imageInputs === 'supported' ? 'Qualified PNG/JPEG/WebP (4 MiB each, 8 MiB per send)' : 'Unknown'}. Fast Mode: Unavailable.</p>
        <p>{model.unavailableReasons.join(' ')}</p></article>)}
    </section>
    {provider.account && <dl className="claude-account"><div><dt>Account</dt><dd>{provider.account.email}</dd></div><div><dt>Plan</dt><dd>{provider.account.plan.toUpperCase()}</dd></div><div><dt>Organization</dt><dd>{provider.account.orgName || provider.account.orgId}</dd></div><div><dt>Native status checked</dt><dd>{new Date(provider.account.checkedAt).toLocaleString()}</dd></div></dl>}
    <p className="field-help">Text, documents and qualified image inputs use this native Claude subscription with Studio tools. PDFs use extracted text; embedded images are not inspected. Hosted web search, image generation, native subagents and Fast Mode are unavailable. Paid extra usage must be disabled in your Claude account.</p>
    {error && <p role="alert" className="provider-alert">{error}</p>}
    {operation?.message && <p role="status" className="field-help">{operation.message}</p>}
    {operation?.authorizationUrl && <form className="provider-form" onSubmit={event => void control('code', event)}>
      <a className="button-primary claude-sign-in" href={operation.authorizationUrl} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">Open Claude sign-in</a>
      <p className="field-help">Sign in with your Pro / Max account, then paste the complete code shown by Claude. This link expires in {operation.expiresInSeconds ?? 0} seconds.</p>
      <label htmlFor="claude-code">Sign-in confirmation code</label><input id="claude-code" type="password" autoComplete="off" spellCheck={false} value={code} onChange={event => setCode(event.target.value)} maxLength={1800} disabled={busy} />
      <button className="button-primary" disabled={busy || !code}>Complete sign-in</button>
    </form>}
    <div className="provider-actions">
      <button type="button" className="button-primary" disabled={busy || running || !runtime.runtime} onClick={() => void act('connect')}>{provider.status === 'not-connected' ? 'Connect Claude' : 'Reconnect'}</button>
      <button type="button" className="button-secondary" disabled={busy || running || !runtime.runtime} onClick={() => void act('status')}>Check provider status</button>
      <button type="button" className="button-secondary" disabled={busy || running || provider.status !== 'connected' || !runtime.runtime} onClick={() => void act('limits')}>Check subscription limits</button>
      <button type="button" className="button-secondary" disabled={busy || running || provider.status !== 'connected' || !runtime.runtime} onClick={() => void act('catalog')}>Read native model catalog</button>
      {running && <button type="button" className="button-secondary" disabled={busy} onClick={() => void control('cancel')}>{operation?.action === 'remove' ? 'Cancel removal' : 'Cancel sign-in'}</button>}
      {pending && <button type="button" className="button-secondary" disabled={busy} onClick={() => void read()}>Read original request</button>}
      {provider.status !== 'not-connected' && <button type="button" className="button-secondary" disabled={busy || running} onClick={() => setConfirmDisconnect(true)}>Disconnect</button>}
      <button type="button" className="button-secondary" disabled={busy || running || provider.status !== 'not-connected'} title={provider.status !== 'not-connected' ? 'Disconnect this provider before removing it.' : undefined}
        onClick={() => { setConfirmName(''); setConfirmRemove(true); }}>Remove provider</button>
    </div>
    {confirmDisconnect && <div className="provider-alert" role="group" aria-label="Confirm disconnect"><p>Disconnect {provider.name}? Its native sign-in will be removed. Existing conversations stay on the host.</p><div className="provider-actions"><button type="button" className="button-secondary" disabled={busy} onClick={() => void act('disconnect')}>Disconnect {provider.name}</button><button type="button" className="button-secondary" onClick={() => setConfirmDisconnect(false)}>Keep connected</button></div></div>}
    {confirmRemove && <div className="provider-form" role="group" aria-label="Confirm provider removal" onKeyDown={event => { if (event.key === 'Escape') setConfirmRemove(false); }}>
      <p>Remove {provider.name}? Existing conversations stay on the host. This connection will no longer be available for new work.</p>
      <label htmlFor="claude-remove-name">Type the provider name to confirm</label><input id="claude-remove-name" autoFocus autoComplete="off" maxLength={80} value={confirmName} onChange={event => setConfirmName(event.target.value)} />
      <div className="provider-actions"><button type="button" className="button-secondary" disabled={busy || confirmName !== provider.name} onClick={() => void act('remove')}>Confirm removal</button>
        <button type="button" className="button-secondary" onClick={() => setConfirmRemove(false)}>Keep provider</button></div>
    </div>}
  </div>;
}
