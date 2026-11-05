import type { ApiProvider } from '../../../../../shared/api-providers';
import type { ProviderApi } from '../useProviders';
import { useConnectionLimits } from '../useConnectionLimits';
import { ZaiLimitsView } from './ZaiLimitsView';

export function ZaiProviderLimits({ provider, api }: { provider: ApiProvider; api: ProviderApi }) {
  const limits = useConnectionLimits(provider, api);
  const sample = limits.sample?.zai ? { ...limits.sample.zai, state: limits.sample.state, error: limits.sample.error } : null;
  return <ZaiLimitsView {...limits} sample={sample} enabled={provider.enabled && provider.keyConfigured} refreshAvailable refresh={() => void limits.refresh()} recover={() => void limits.recover()} />;
}
