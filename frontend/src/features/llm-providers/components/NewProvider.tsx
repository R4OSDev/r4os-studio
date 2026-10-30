import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { Provider } from '../../../../../shared/llm-providers.js';
import type { ProviderApi } from '../useProviders';
import { Icon } from '../../../app/Icon';
import { ApiConnectionForm, apiKinds } from './ApiConnectionForm';
import type { LeaveGuard } from './ApiConnectionForm';
import type { ApiProviderKind } from '../../../../../shared/api-providers';

export function NewProvider({ api, created, setLeaveGuard }: { api: ProviderApi; created: (id: string) => void; setLeaveGuard?: LeaveGuard }) {
  const [type, setType] = useState<'openai' | ApiProviderKind>(() => {
    try { const kind = JSON.parse(sessionStorage.getItem('studio.api.provider.new') ?? 'null')?.kind as ApiProviderKind; return Object.hasOwn(apiKinds, kind) ? kind : 'openai'; }
    catch { return 'openai'; }
  });
  const guard = useRef<(() => boolean) | null>(null);
  const [name, setName] = useState('OpenAI');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError(null);
    try {
      const result = await api.request<{ provider: Provider }>('', 'POST', { type: 'openai', name: name.trim() });
      await api.reload();
      created(result.provider.id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The provider could not be added.'); }
    finally { setBusy(false); }
  }

  return <div className="provider-card">
    <div className="provider-card-heading"><span className="provider-brand"><Icon name="box" /></span><div><h2>Connect an AI provider</h2><p>Choose an account subscription or an API connection.</p></div></div>
    <div className="provider-form"><label htmlFor="provider-type">Provider</label>
      <select id="provider-type" value={type} disabled={busy} onChange={event => { if (!guard.current || guard.current()) setType(event.target.value as typeof type); }}><option value="openai">OpenAI · ChatGPT subscription</option>{Object.entries(apiKinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
    {type === 'openai' ? <form onSubmit={(event) => void submit(event)} className="provider-form">
      <p className="field-help">ChatGPT subscription access. No API key required.</p>
      <label htmlFor="provider-name">Display name</label>
      <input id="provider-name" value={name} onChange={(event) => setName(event.target.value)} required maxLength={80} autoComplete="off" disabled={busy} />
      <p className="field-help">This name appears in the Views column.</p>
      {error && <p className="provider-alert" role="alert">{error}</p>}
      <div className="provider-actions"><button className="button-primary" type="submit" disabled={busy || api.loading || !!api.error || !name.trim()}>{busy ? 'Adding provider…' : 'Add OpenAI provider'}</button></div>
    </form> : <ApiConnectionForm key={type} api={api} kind={type} saved={created} setLeaveGuard={value => { guard.current = value; setLeaveGuard?.(value); }} />}
    <div className="provider-hint"><Icon name="system" /><p>{type === 'openai' ? 'Manage the connection here. OpenAI handles your sign-in in a separate browser tab.' : 'API keys stay on the Studio host. Add model metadata after saving the connection.'}</p></div>
  </div>;
}

