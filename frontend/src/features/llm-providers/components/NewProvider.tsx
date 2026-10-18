import { useState } from 'react';
import type { FormEvent } from 'react';
import type { Provider } from '../../../../../shared/llm-providers.js';
import type { ProviderApi } from '../useProviders';
import { Icon } from '../../../app/Icon';

export function NewProvider({ api, created }: { api: ProviderApi; created: (id: string) => void }) {
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
    <div className="provider-card-heading"><span className="provider-brand"><Icon name="box" /></span><div><h2>Connect an AI provider</h2><p>Add OpenAI and sign in with your ChatGPT account.</p></div></div>
    <form onSubmit={(event) => void submit(event)} className="provider-form">
      <label htmlFor="provider-type">Provider</label>
      <select id="provider-type" value="openai" disabled={busy} onChange={() => {}}><option value="openai">OpenAI</option></select>
      <p className="field-help">ChatGPT subscription access. No API key required.</p>
      <label htmlFor="provider-name">Display name</label>
      <input id="provider-name" value={name} onChange={(event) => setName(event.target.value)} required maxLength={80} autoComplete="off" disabled={busy} />
      <p className="field-help">This name appears in the Views column.</p>
      {error && <p className="provider-alert" role="alert">{error}</p>}
      <div className="provider-actions"><button className="button-primary" type="submit" disabled={busy || api.loading || !!api.error || !name.trim()}>{busy ? 'Adding provider…' : 'Add OpenAI provider'}</button></div>
    </form>
    <div className="provider-hint"><Icon name="system" /><p>Manage the connection here. OpenAI handles your sign-in in a separate browser tab.</p></div>
  </div>;
}

