import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { ApiAuth, ApiProtocol, ApiProvider, ApiProviderKind, ApiProviderMutation, ApiServer } from '../../../../../shared/api-providers';
import type { ProviderApi } from '../useProviders';
import { useApiMutation } from '../useApiMutation';
import { OpenRouterFields, routerDraft, routerSettings } from './OpenRouterFields';

export const apiKinds = { openrouter: 'OpenRouter', 'openai-compatible': 'Custom API', local: 'Local API' };
export type LeaveGuard = (guard: () => boolean) => void;
export function ApiConnectionForm({ api, initial, kind, saved, setLeaveGuard }: {
  api: ProviderApi; initial?: ApiProvider; kind: ApiProviderKind; saved: (id: string) => void; setLeaveGuard?: LeaveGuard;
}) {
  const [name, setName] = useState(initial?.name ?? apiKinds[kind]);
  const [baseUrl, setUrl] = useState(initial?.baseUrl ?? (kind === 'openrouter' ? 'https://openrouter.ai/api/v1' : ''));
  const [protocol, setProtocol] = useState<ApiProtocol>(initial?.protocol ?? 'chat-completions');
  const [auth, setAuth] = useState<ApiAuth>(initial?.auth ?? (kind === 'local' ? 'none' : 'bearer'));
  const [enabled, setEnabled] = useState(initial?.enabled ?? true), [secret, setSecret] = useState('');
  const [keyAction, setKeyAction] = useState<'keep' | 'replace' | 'clear'>(initial ? 'keep' : 'replace');
  const [routing, setRouting] = useState(() => routerDraft(initial?.openrouter));
  const [server, setServer] = useState<ApiServer>(initial?.server ?? 'custom');
  const mutation = useApiMutation(api, initial?.id ?? null), field = useRef<HTMLInputElement>(null);
  const retryConfig = mutation.notFound && !!mutation.pending && ['create', 'update'].includes(mutation.pending.operation);
  const dirty = name !== (initial?.name ?? apiKinds[kind]) || baseUrl !== (initial?.baseUrl ?? (kind === 'openrouter' ? 'https://openrouter.ai/api/v1' : ''))
    || protocol !== (initial?.protocol ?? 'chat-completions') || auth !== (initial?.auth ?? (kind === 'local' ? 'none' : 'bearer'))
    || enabled !== (initial?.enabled ?? true) || !!secret || !!initial && keyAction !== 'keep'
    || kind === 'openrouter' && JSON.stringify(routing) !== JSON.stringify(routerDraft(initial?.openrouter));
  const changed = dirty || kind !== 'openrouter' && server !== (initial?.server ?? 'custom');
  useEffect(() => {
    setLeaveGuard?.(() => !mutation.busy && (!changed && !mutation.pending || window.confirm('Leave these API settings? Unsaved keys will be discarded. An original pending request remains available on return.')));
    const warn = (event: BeforeUnloadEvent) => { if (changed || mutation.pending) event.preventDefault(); };
    window.addEventListener('beforeunload', warn);
    return () => { setLeaveGuard?.(() => true); window.removeEventListener('beforeunload', warn); };
  }, [changed, mutation.busy, mutation.pending, setLeaveGuard]);
  async function accept(result: ApiProviderMutation | undefined) {
    if (result?.state !== 'complete') return;
    setSecret(''); await api.reload(); saved(result.provider.id);
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    const data = { name: name.trim(), baseUrl: baseUrl.trim(), protocol, auth,
      ...(kind === 'openrouter' ? { openrouter: routerSettings(routing) } : { server }),
      ...(initial ? { revision: initial.revision, enabled: auth === 'bearer' && (keyAction === 'clear' || !initial.keyConfigured && !secret) ? false : enabled } : { kind }),
      ...(auth === 'bearer' && keyAction === 'replace' && secret ? { key: secret } : initial && (keyAction === 'clear' || auth === 'none') ? { key: null } : {}) };
    await accept(await mutation.send(initial ? 'update' : 'create', data, !!mutation.pending) as ApiProviderMutation | undefined);
  }
  function cancel() {
    setSecret(''); setName(initial?.name ?? apiKinds[kind]); setUrl(initial?.baseUrl ?? (kind === 'openrouter' ? 'https://openrouter.ai/api/v1' : ''));
    setProtocol(initial?.protocol ?? 'chat-completions'); setAuth(initial?.auth ?? (kind === 'local' ? 'none' : 'bearer'));
    setEnabled(initial?.enabled ?? true); setKeyAction(initial ? 'keep' : 'replace'); setRouting(routerDraft(initial?.openrouter));
    setServer(initial?.server ?? 'custom');
  }
  return <form className="provider-form api-connection-form" onSubmit={event => void submit(event)} aria-label="API connection">
    <fieldset disabled={mutation.busy || !!mutation.pending && !retryConfig}>
      <label htmlFor="api-name">Display name</label><input id="api-name" value={name} required maxLength={80} autoComplete="off" onChange={event => setName(event.target.value)} />
      {kind !== 'openrouter' && <><label htmlFor="api-server">Server software</label><select id="api-server" value={server} onChange={event => setServer(event.target.value as ApiServer)}><option value="custom">Custom OpenAI-compatible server</option><option value="ollama">Ollama</option><option value="lm-studio">LM Studio</option></select>
        {server !== 'custom' && <><p className="field-help">{server === 'ollama' ? 'Responses requires Ollama 0.13.3 or later and is stateless.' : 'Responses requires LM Studio 0.3.29 or later; API tokens require 0.4.0 or later.'} Confirm your server version and exact nonreasoning model facts. A preset does not verify compatibility.</p>
          {kind === 'local' && <button type="button" className="button-secondary" onClick={() => { setUrl(server === 'ollama' ? 'http://127.0.0.1:11434/v1' : 'http://127.0.0.1:1234/v1'); setProtocol('chat-completions'); setAuth('none'); setSecret(''); if (initial) setKeyAction('clear'); }}>Use {server === 'ollama' ? 'Ollama' : 'LM Studio'} local defaults</button>}</>}</>}
      <label htmlFor="api-url">Base URL</label><input id="api-url" value={baseUrl} required maxLength={2048} autoComplete="off" placeholder={kind === 'local' ? 'http://127.0.0.1:11434/v1' : 'https://api.example.com/v1'} onChange={event => setUrl(event.target.value)} />
      <p className="field-help">Localhost / 127.0.0.1 means the Studio host, not your browser device. Use Local API for an explicit LAN IP and port. Include the full API prefix, without a model route or query. No network discovery is performed.</p>
      <label htmlFor="api-protocol">Protocol</label><select id="api-protocol" value={protocol} onChange={event => setProtocol(event.target.value as ApiProtocol)}><option value="chat-completions">Chat Completions</option><option value="responses" disabled={kind === 'openrouter'}>Responses{kind === 'openrouter' ? ' · unavailable for OpenRouter' : ''}</option></select>
      {kind === 'openrouter' && <p className="field-help">Streamed text and function tools use Chat Completions. Reasoning tool-history, Responses and hosted web/images are currently unavailable for this provider.</p>}
      <label htmlFor="api-auth">Authentication</label><select id="api-auth" value={auth} onChange={event => { setAuth(event.target.value as ApiAuth); setSecret(''); }}><option value="bearer">Bearer API key</option><option value="none" disabled={kind === 'openrouter'}>No authentication</option></select>
      {auth === 'bearer' && <div className="api-key-editor">
        <p className="field-help">{initial?.keyConfigured ? 'A key is configured. Its value cannot be read back.' : 'No key is configured. You can save now and add it later.'}</p>
        {initial && <div className="provider-actions"><button type="button" className="button-secondary" onClick={() => { setKeyAction('replace'); requestAnimationFrame(() => field.current?.focus()); }}>Replace key</button><button type="button" className="button-secondary" onClick={() => { setSecret(''); setKeyAction('clear'); }}>Clear key</button></div>}
        {keyAction === 'replace' && <><label htmlFor="api-key">{initial ? 'Replacement API key' : 'API key (optional)'}</label><input ref={field} id="api-key" type="password" value={secret} maxLength={8192} autoComplete="new-password" spellCheck={false} onChange={event => setSecret(event.target.value)} /></>}
        {keyAction === 'clear' && <p className="field-help">The key will be removed when you save. This connection will be disabled.</p>}
      </div>}
      {initial && <label className="api-enabled"><input type="checkbox" checked={enabled} disabled={auth === 'bearer' && (keyAction === 'clear' || !initial.keyConfigured && !secret)} onChange={event => setEnabled(event.target.checked)} />Enabled for new runs</label>}
      {kind === 'openrouter' && <OpenRouterFields draft={routing} change={setRouting} />}
    </fieldset>
    <p className="field-help">Saving stores configuration only. It does not check metadata or send a model request.</p>
    {mutation.error && <p className="provider-alert" role="alert">{mutation.error}</p>}
    {mutation.pending ? <div className="provider-alert" role="status"><span>Original request: {mutation.pending.requestId}. Read its result before changing this configuration.</span><button type="button" disabled={mutation.busy} onClick={() => void mutation.read().then(result => accept(result as ApiProviderMutation | undefined))}>{mutation.busy ? 'Reading…' : 'Read original result'}</button></div>
      : <div className="provider-actions"><button type="submit" className="button-primary" disabled={mutation.busy || api.loading || !!api.error || !!initial && !changed || auth === 'bearer' && keyAction === 'replace' && !!initial && !secret}>{mutation.busy ? 'Saving…' : 'Save connection'}</button><button type="button" className="button-secondary" disabled={mutation.busy} onClick={cancel}>Cancel changes</button></div>}
    {retryConfig && <button type="submit" className="button-primary" disabled={mutation.busy}>Retry same request</button>}
    {initial && <div className="provider-footer-actions"><button type="button" className="button-secondary" disabled={mutation.busy || !!mutation.pending} onClick={() => {
      if (window.confirm('Disconnect this API connection and stop its active runs? Its key will be removed after original transports have closed.')) void mutation.send('disconnect', { revision: initial.revision }).then(result => accept(result as ApiProviderMutation | undefined));
    }}>Disconnect</button><button type="button" className="button-secondary" disabled={mutation.busy || !!mutation.pending} onClick={() => {
      if (window.confirm(`Delete API connection “${initial.name}” and stop its active runs? Existing conversations are preserved.`)) void mutation.send('delete', { revision: initial.revision }).then(result => accept(result as ApiProviderMutation | undefined));
    }}>Delete connection</button></div>}
    {mutation.pending && ['disconnect', 'delete'].includes(mutation.pending.operation) && <button type="button" className="button-secondary" disabled={mutation.busy} onClick={() => void mutation.send(mutation.pending!.operation, { revision: mutation.pending!.revision }, true).then(result => accept(result as ApiProviderMutation | undefined))}>Finish original {mutation.pending.operation}</button>}
  </form>;
}
