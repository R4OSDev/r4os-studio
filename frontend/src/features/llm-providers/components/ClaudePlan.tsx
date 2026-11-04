import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { ApiProvider } from '../../../../../shared/api-providers';
import type { ProviderApi } from '../useProviders';
import { providerRequestId } from '../api';
import { useApiMutation } from '../useApiMutation';

interface Attempt { requestId: string; state: string; providerId: string | null; authorizationUrl?: string; message: string | null }
interface Status { attempts: Attempt[] }

export function ClaudePlan({ api, provider, saved }: { api: ProviderApi; provider?: ApiProvider; saved: (id: string) => void }) {
  const [name, setName] = useState(provider?.name ?? 'Claude');
  const [status, setStatus] = useState<Status | null>(null), [error, setError] = useState('');
  const [redirect, setRedirect] = useState(''), [busy, setBusy] = useState(false);
  const [pending, setPending] = useState(() => { try { return sessionStorage.getItem('studio.claude.plan.attempt'); } catch { return null; } });
  const active = useRef(true), working = useRef(false), activated = useRef<string | null>(null);
  const { request, reload } = api;
  const mutation = useApiMutation(api, provider?.id ?? null);
  const read = useCallback(async () => {
    const next = await request<Status>('/claude-plan');
    if (active.current) { setStatus(next); setError(''); }
  }, [request]);
  useEffect(() => {
    active.current = true;
    if (provider) return () => { active.current = false; };
    void read().catch(cause => { if (active.current) setError((cause as Error).message); });
    const timer = setInterval(() => { if (!document.hidden && !working.current) void read().catch(cause => { if (active.current) setError((cause as Error).message); }); }, 2000);
    return () => { active.current = false; clearInterval(timer); };
  }, [read, provider]);
  const attempt = status?.attempts.find(a => a.requestId === pending);
  useEffect(() => {
    if (attempt?.state !== 'complete' || !attempt.providerId || provider || activated.current === attempt.requestId) return;
    activated.current = attempt.requestId;
    sessionStorage.removeItem('studio.claude.plan.attempt');
    void reload().then(() => saved(attempt.providerId!)).catch(cause => { activated.current = null; if (active.current) setError((cause as Error).message); });
  }, [attempt, provider, reload, saved]);
  async function action(kind: 'start' | 'redirect' | 'cancel', event?: FormEvent) {
    event?.preventDefault(); if (working.current) return;
    working.current = true; setBusy(true); setError('');
    try {
      if (kind === 'start') {
        const requestId = providerRequestId();
        sessionStorage.setItem('studio.claude.plan.attempt', requestId); setPending(requestId);
        await request('/claude-plan/login', 'POST', { requestId, name: name.trim() });
      } else if (pending) {
        const url = redirect; setRedirect('');
        await request(`/claude-plan/attempts/${pending}/${kind}`, 'POST', kind === 'redirect' ? { redirectUrl: url } : {});
      }
      await read();
    } catch (cause) { if (active.current) setError((cause as Error).message); }
    finally { working.current = false; if (active.current) setBusy(false); }
  }
  if (provider) return <section aria-label="Claude browser connection">
    <p className="field-help">Claude subscription · Studio owns history, tools and context. Model access is qualified separately from sign-in. This connection uses one private browser grant, without a native agent or a second limits login.</p>
    <p>Status: {provider.enabled && provider.keyConfigured ? 'Connected' : 'Disconnected'}</p>
    <div className="provider-actions"><button type="button" className="button-secondary" disabled={mutation.busy} onClick={() => {
      if (window.confirm('Disconnect this Claude connection and stop its active runs? Local tokens will be cleared after their original transports end. Remote revocation is not confirmed.')) void mutation.send('disconnect', { revision: provider.revision }).then(() => reload());
    }}>Disconnect</button>
    <button type="button" className="button-secondary" disabled={mutation.busy} onClick={() => {
      if (window.confirm('Delete this connection and stop its active runs? Existing conversations are preserved.')) void mutation.send('delete', { revision: provider.revision }).then(() => reload());
    }}>Delete connection</button></div>
    {mutation.pending && <button type="button" className="button-secondary" disabled={mutation.busy} onClick={() => void mutation.send(mutation.pending!.operation, { revision: mutation.pending!.revision }, true).then(() => reload())}>Finish original request</button>}
    {mutation.error && <p role="alert" className="provider-alert">{mutation.error}</p>}
  </section>;
  return <section aria-label="Claude browser sign-in">
    <form className="provider-form" onSubmit={event => void action('start', event)}>
      <label htmlFor="claude-plan-name">Display name</label><input id="claude-plan-name" required maxLength={80} value={name} onChange={event => setName(event.target.value)} disabled={busy} />
      <p className="field-help">Sign in to your Claude subscription in your browser. Paste the complete final redirect address here. No helper or terminal is required.</p>
      <button className="button-primary" disabled={busy || !name.trim() || ['waiting', 'exchanging'].includes(attempt?.state ?? '')}>Continue with Claude</button>
    </form>
    {attempt && <p role="status">Sign-in: {attempt.state === 'complete' ? 'Connected' : attempt.state}{attempt.message ? ' · '+attempt.message : ''}</p>}
    {attempt?.authorizationUrl && <form className="provider-form" onSubmit={event => void action('redirect', event)}>
      <a className="button-primary" href={attempt.authorizationUrl} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">Open Claude sign-in</a>
      <label htmlFor="claude-plan-redirect">Complete redirect address</label><input id="claude-plan-redirect" type="password" autoComplete="off" spellCheck={false} maxLength={16384} value={redirect} onChange={event => setRedirect(event.target.value)} disabled={busy} />
      <button className="button-primary" disabled={busy || !redirect}>Complete sign-in</button>
      <button type="button" className="button-secondary" disabled={busy} onClick={() => void action('cancel')}>Cancel sign-in</button>
    </form>}
    {error && <p role="alert" className="provider-alert">{error}</p>}
  </section>;
}
