import { useEffect, useRef, useState } from 'react';
import type { Provider, ProviderLogin } from '../../../../../shared/llm-providers.js';
import type { ProviderApi } from '../useProviders';
import { Icon } from '../../../app/Icon';

const labels: Record<Provider['status'], string> = {
  connected: 'Connected', disconnected: 'Not connected', signing_in: 'Waiting for sign-in', unavailable: 'Unavailable',
};

export function ProviderDetails({ initial, api, removed }: { initial: Provider; api: ProviderApi; removed: () => void }) {
  const [provider, setProvider] = useState(initial);
  const [login, setLogin] = useState<ProviderLogin | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copyMessage, setCopyMessage] = useState('');
  const [confirmRemove, setConfirmRemove] = useState(false);
  const codeInput = useRef<HTMLInputElement>(null);
  const { request, reload } = api;
  const path = `/${initial.id}`;

  useEffect(() => {
    let active = true;
    void Promise.all([
      request<{ provider: Provider }>(path),
      request<{ login: ProviderLogin | null }>(`${path}/login`).catch(() => ({ login: null })),
    ]).then(([result, session]) => {
      if (active) { setProvider(result.provider); setLogin(session.login); }
    }).catch(() => { if (active) setError('The provider could not be loaded. Please reload this page.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [path, request]);

  useEffect(() => {
    if (login?.status !== 'pending') return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await request<{ login: ProviderLogin | null }>(`${path}/login`);
        if (!active) return;
        setError(null);
        if (result.login?.status !== 'pending') {
          const current = await request<{ provider: Provider }>(path);
          if (active) { setProvider(current.provider); setLogin(result.login); await reload(); }
          return;
        }
        setLogin(result.login);
      } catch { if (active) setError('Connection interrupted. Retrying…'); }
      if (active) timer = setTimeout(() => void poll(), 1500);
    };
    timer = setTimeout(() => void poll(), 1500);
    return () => { active = false; clearTimeout(timer); };
  }, [login?.status, path, request, reload]);

  async function action(operation: 'login' | 'cancel' | 'disconnect' | 'remove') {
    if (busy) return;
    setBusy(true); setError(null); setCopyMessage('');
    try {
      if (operation === 'login') {
        const result = await request<{ login: ProviderLogin }>(`${path}/login`, 'POST');
        setLogin(result.login);
        setProvider((previous) => ({ ...previous, status: result.login.status === 'pending' ? 'signing_in' : 'disconnected' }));
      } else if (operation === 'remove') {
        await request(path, 'DELETE');
        await reload(); removed(); return;
      } else {
        if (operation === 'cancel') await request(`${path}/login`, 'DELETE');
        else await request(`${path}/disconnect`, 'POST');
        setLogin(null);
        setProvider((await request<{ provider: Provider }>(path)).provider);
      }
      await reload();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The provider request failed.'); }
    finally { setBusy(false); }
  }

  async function copyCode() {
    if (!login?.userCode) return;
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(login.userCode);
      else { codeInput.current?.select(); if (!document.execCommand('copy')) throw new Error(); }
      setCopyMessage('Code copied.');
    } catch { codeInput.current?.select(); setCopyMessage('Code selected. Press Ctrl+C to copy.'); }
  }

  const pending = login?.status === 'pending';
  const status = pending ? 'signing_in' : provider.status;
  return <div className="provider-card">
    <div className="provider-card-heading"><span className="provider-brand"><Icon name="box" /></span><div><h2>{provider.name}</h2><p>OpenAI · ChatGPT subscription</p></div><span className={`provider-status ${status}`}><span />{loading ? 'Checking connection…' : labels[status]}</span></div>
    {error && <p className="provider-alert" role="alert">{error}</p>}
    {login?.message && <p className="provider-alert" role="status">{login.message}</p>}
    {pending && <div className="device-login" aria-label="OpenAI sign-in">
      <h3>Finish signing in</h3>
      <p>Enter this one-time code on OpenAI. Keep this page open; your connection will update automatically.</p>
      <label htmlFor="openai-code">One-time code</label>
      <div className="device-code-row"><input ref={codeInput} id="openai-code" value={login.userCode ?? ''} readOnly onFocus={(event) => event.currentTarget.select()} autoComplete="off" /><button className="button-secondary" type="button" onClick={() => void copyCode()}>Copy code</button></div>
      <div className="copy-message" role="status">{copyMessage}</div>
      <div className="provider-actions"><a className="button-primary" href={login.verificationUrl} target="_blank" rel="noopener noreferrer">Open OpenAI sign-in ↗</a><button className="button-secondary" type="button" disabled={busy} onClick={() => void action('cancel')}>Cancel sign-in</button></div>
      <p className="field-help">The code expires at {new Date(login.expiresAt).toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit' })}. Only continue if you started this sign-in.</p>
    </div>}
    {!pending && <>
      <dl className="provider-properties">
        <div><dt>Provider</dt><dd>OpenAI</dd></div>
        <div><dt>Account</dt><dd>{provider.account?.email ?? 'Not signed in'}</dd></div>
        <div><dt>Plan</dt><dd className="plan-name">{provider.account?.plan ?? '—'}</dd></div>
        <div><dt>Authentication</dt><dd>ChatGPT subscription</dd></div>
      </dl>
      {provider.status !== 'connected' && <div className="provider-actions"><button className="button-primary" type="button" disabled={busy || loading || !api.signInAvailable || !!api.error || provider.status === 'signing_in'} onClick={() => void action('login')}>{busy ? 'Starting sign-in…' : 'Continue with ChatGPT'}</button></div>}
      {!api.signInAvailable && <p className="provider-alert" role="status">OpenAI sign-in is currently unavailable. Please try again later.</p>}
      {provider.status === 'signing_in' && <p className="field-help">A sign-in is in progress in another browser session.</p>}
      <div className="provider-hint"><Icon name="system" /><p>{provider.status === 'connected' ? 'Connected to your ChatGPT account. Your subscription determines available Codex access.' : 'Sign in at OpenAI to connect your ChatGPT subscription. You will not need a terminal or an API key.'}</p></div>
    </>}
    <div className="provider-footer-actions">
      {provider.status === 'connected' && !pending && <button className="button-secondary" type="button" disabled={busy} onClick={() => void action('disconnect')}>Disconnect</button>}
      {confirmRemove ? <div className="remove-confirmation"><span>Remove this provider?</span><button className="button-danger" type="button" disabled={busy} onClick={() => void action('remove')}>Remove</button><button className="button-secondary" type="button" disabled={busy} onClick={() => setConfirmRemove(false)}>Keep provider</button></div>
        : <button className="button-text" type="button" disabled={busy} onClick={() => setConfirmRemove(true)}>Remove provider</button>}
    </div>
  </div>;
}
