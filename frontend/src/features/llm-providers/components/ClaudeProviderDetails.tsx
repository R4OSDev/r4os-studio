import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { ClaudeSubscriptionProvider, ClaudeProviderMutation, ClaudeRuntimeStatus, ClaudeAuthOperation, ClaudeAuthAction } from '../../../../../shared/claude-subscription';
import type { ProviderApi } from '../useProviders';
import type { ClaudeSubscriptionLimits } from '../../../../../shared/claude-subscription';
import { ClaudeLimitsView } from './ClaudeLimitsView';

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
        const requestId = crypto.randomUUID(); sessionStorage.setItem(key, requestId); setPending(requestId);
        result = await api.request<ClaudeProviderMutation>(base, 'POST', { requestId, name: name.trim() });
      }
      sessionStorage.removeItem(key); setPending(null); await api.reload(); created(result.provider.id);
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
export function ClaudeProviderDetails({ initial, api }: { initial: ClaudeSubscriptionProvider; api: ProviderApi }) {
  const [observed, setObserved] = useState<ClaudeSubscriptionProvider | null>(null), [operation, setOperation] = useState<ClaudeAuthOperation | null>(null);
  const provider = observed && observed.revision >= initial.revision ? observed : initial;
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [code, setCode] = useState(''), [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const key = `studio.claude.${initial.id}.auth.request`;
  const [pending, setPending] = useState(() => original(key));
  const running = operation?.state === 'pending' || operation?.state === 'waiting';
  const inflight = useRef(false), mounted = useRef(true);
  const generation = useRef(0);
  const runtime = useRuntime(api), request = api.request, reload = api.reload;
  const [limits, setLimits] = useState<ClaudeSubscriptionLimits | null>(null);
  useEffect(() => {
    let active = true;
    void request<{ limits: ClaudeSubscriptionLimits | null }>(`${base}/${provider.id}/limits`)
      .then(value => { if (active) setLimits(value.limits); }).catch(() => { if (active) setLimits(null); });
    return () => { active = false; };
  }, [provider.id, provider.revision, request]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const accept = useCallback((value: ClaudeAuthOperation) => {
    if (!mounted.current) return;
    setOperation(value); setObserved(value.provider); setError('');
    if (value.limits) setLimits(value.limits);
    if (!['pending', 'waiting'].includes(value.state)) { setCode(''); void reload(); }
  }, [reload]);
  const read = useCallback(async () => {
    if (!pending || inflight.current) return;
    const sequence = ++generation.current;
    try { const value = await request<ClaudeAuthOperation>(`${base}/${initial.id}/auth-requests/${pending}`); if (sequence === generation.current) accept(value); }
    catch (cause) { if (mounted.current && sequence === generation.current) setError(cause instanceof Error ? cause.message : 'The original sign-in result is unavailable.'); }
  }, [accept, initial.id, pending, request]);
  useEffect(() => { const timer = setTimeout(() => void read(), 0); return () => clearTimeout(timer); }, [read]);
  useEffect(() => {
    if (!pending || !running) return;
    const timer = setInterval(() => { if (!document.hidden) void read(); }, 1500);
    return () => clearInterval(timer);
  }, [pending, running, read]);
  async function act(action: ClaudeAuthAction) {
    if (inflight.current) return;
    inflight.current = true; generation.current++; setBusy(true); setError(''); setCode(''); setConfirmDisconnect(false);
    const requestId = crypto.randomUUID(); sessionStorage.setItem(key, requestId); setPending(requestId);
    try { accept(await request<ClaudeAuthOperation>(`${base}/${provider.id}/auth`, 'POST', { requestId, revision: provider.revision, action })); }
    catch (cause) { if (mounted.current) setError(cause instanceof Error ? cause.message : 'Read the original authentication result.'); }
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
    {provider.account && <dl className="claude-account"><div><dt>Account</dt><dd>{provider.account.email}</dd></div><div><dt>Plan</dt><dd>{provider.account.plan.toUpperCase()}</dd></div><div><dt>Organization</dt><dd>{provider.account.orgName || provider.account.orgId}</dd></div><div><dt>Native status checked</dt><dd>{new Date(provider.account.checkedAt).toLocaleString()}</dd></div></dl>}
    <p className="field-help">Model access will be available after the native session, tool and subscription limit checks are complete.</p>
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
      {running && <button type="button" className="button-secondary" disabled={busy} onClick={() => void control('cancel')}>Cancel sign-in</button>}
      {pending && <button type="button" className="button-secondary" disabled={busy} onClick={() => void read()}>Read original request</button>}
      {provider.status !== 'not-connected' && <button type="button" className="button-secondary" disabled={busy || running} onClick={() => setConfirmDisconnect(true)}>Disconnect</button>}
    </div>
    {confirmDisconnect && <div className="provider-alert" role="group" aria-label="Confirm disconnect"><p>Disconnect {provider.name}? Its native sign-in will be removed. Existing conversations stay on the host.</p><div className="provider-actions"><button type="button" className="button-secondary" disabled={busy} onClick={() => void act('disconnect')}>Disconnect {provider.name}</button><button type="button" className="button-secondary" onClick={() => setConfirmDisconnect(false)}>Keep connected</button></div></div>}
  </div>;
}
