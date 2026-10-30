import { useCallback, useEffect, useRef, useState } from 'react';
import type { ApiProvider } from '../../../../../shared/api-providers';
import type { ProviderApi } from '../useProviders';
import { ProviderRequestError } from '../api';
import { ApiConnectionForm, apiKinds } from './ApiConnectionForm';
import type { LeaveGuard } from './ApiConnectionForm';
import { ApiModels } from './ApiModels';
import { Icon } from '../../../app/Icon';

export function ApiProviderDetails({ initial, api, removed, setLeaveGuard }: { initial: ApiProvider; api: ProviderApi; removed: () => void; setLeaveGuard?: LeaveGuard }) {
  const [provider, setProvider] = useState(initial), [error, setError] = useState('');
  const guards = useRef<Record<string, (() => boolean) | null>>({});
  const connectionGuard = useCallback((guard: (() => boolean) | null) => { guards.current.connection = guard; }, []);
  const modelGuard = useCallback((guard: (() => boolean) | null) => { guards.current.models = guard; }, []);
  useEffect(() => { setLeaveGuard?.(() => Object.values(guards.current).every(guard => !guard || guard())); return () => setLeaveGuard?.(() => true); }, [setLeaveGuard]);
  async function reload() {
    try { setProvider((await api.request<{ provider: ApiProvider }>(`/api-connections/${provider.id}`)).provider); setError(''); }
    catch (cause) {
      if (cause instanceof ProviderRequestError && cause.status === 410) { await api.reload(); removed(); }
      else setError((cause as Error).message);
    }
  }
  return <div className="provider-card api-provider-card">
    <div className="provider-card-heading"><span className="provider-brand"><Icon name="box" /></span><div><h2>{provider.name}</h2><p>{apiKinds[provider.kind]} · {provider.protocol === 'responses' ? 'Responses' : 'Chat Completions'}</p></div><span className={`provider-status ${provider.enabled ? 'connected' : ''}`}><span />{provider.enabled ? 'Configured' : 'Disabled'}</span></div>
    {error && <p className="provider-alert" role="alert">{error}<button type="button" onClick={() => void reload()}>Reload connection</button></p>}
    <button type="button" className="button-secondary" onClick={() => { if (Object.values(guards.current).every(guard => !guard || guard())) void reload(); }}>Reload saved connection</button>
    <ApiConnectionForm key={provider.revision} initial={provider} kind={provider.kind} api={api} saved={() => void reload()} setLeaveGuard={connectionGuard} />
    <ApiModels key={`models-${provider.revision}`} provider={provider} api={api} setLeaveGuard={modelGuard} />
  </div>;
}
