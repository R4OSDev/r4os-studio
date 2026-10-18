import type { Provider } from '../../../../../shared/llm-providers.js';
import type { ProviderApi } from '../useProviders';
import { NewProvider } from './NewProvider';
import { ProviderDetails } from './ProviderDetails';
import '../styles.css';

export function ProviderPanel({ provider, api, select }: {
  provider?: Provider; api: ProviderApi; select: (id: string | null) => void;
}) {
  return <section className="provider-content" aria-label="LLM provider settings">
    {api.error && <div className="provider-alert" role="alert">{api.error}<button type="button" onClick={() => void api.reload()}>Retry</button></div>}
    {provider ? <ProviderDetails key={provider.id} initial={provider} api={api} removed={() => select(null)} />
      : <NewProvider api={api} created={select} />}
  </section>;
}

