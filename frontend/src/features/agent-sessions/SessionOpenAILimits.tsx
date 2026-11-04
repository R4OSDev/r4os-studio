import { useProviders } from '../llm-providers/useProviders';
import { ProviderUsage } from '../llm-providers/components/ProviderUsage';
import '../llm-providers/styles.css';

/** Same account reader, normalizer and refresh behavior as provider settings. */
export function SessionOpenAILimits({ providerId }: { providerId: string }) {
  const api = useProviders(false);
  const provider = api.nativeProviders.find(p => p.id === providerId);
  if (api.loading) return <p role="status">Loading OpenAI account limits…</p>;
  if (api.error || !provider || provider.status !== 'connected') return <p className="provider-alert">OpenAI account limits are unavailable. Review this connection in System settings.</p>;
  return <section aria-label="OpenAI account limits">
    <p className="field-help">Subscription limits for this connection’s signed-in account and workspace.</p>
    <ProviderUsage key={provider.id + ':' + provider.account?.scope} id={provider.id} accountEmail={provider.account?.email ?? null} accountScope={provider.account?.scope} request={api.request} />
  </section>;
}
