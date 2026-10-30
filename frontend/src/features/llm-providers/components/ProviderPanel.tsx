import type { Provider } from '../../../../../shared/llm-providers.js';
import type { ProviderApi } from '../useProviders';
import { NewProvider } from './NewProvider';
import { ProviderDetails } from './ProviderDetails';
import type { ApiProvider } from '../../../../../shared/api-providers';
import { ApiProviderDetails } from './ApiProviderDetails';
import type { LeaveGuard } from './ApiConnectionForm';
import '../styles.css';

export function ProviderPanel({ provider, api, select, setLeaveGuard }: {
  provider?: Provider | ApiProvider; api: ProviderApi; select: (id: string | null) => void; setLeaveGuard?: LeaveGuard;
}) {
  return <section className="provider-content" aria-label="LLM provider settings">
    {api.error && <div className="provider-alert" role="alert">{api.error}<button type="button" onClick={() => void api.reload()}>Retry</button></div>}
    {api.apiError && <div className="provider-alert" role="alert">{api.apiError}<button type="button" onClick={() => void api.reload()}>Reload API connections</button></div>}
    {provider?.type === 'api' ? <ApiProviderDetails key={provider.id} initial={provider} api={api} removed={() => select(null)} setLeaveGuard={setLeaveGuard} /> : provider ? <ProviderDetails key={`${provider.id}:${provider.status}:${provider.account?.email ?? ''}:${provider.account?.plan ?? ''}`} initial={provider} api={api} removed={() => select(null)} />
      : <NewProvider api={api} created={select} setLeaveGuard={setLeaveGuard} />}
  </section>;
}

