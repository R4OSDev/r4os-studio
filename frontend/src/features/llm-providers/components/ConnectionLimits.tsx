import type { ApiProvider } from '../../../../../shared/api-providers';
import type { ProviderApi } from '../useProviders';
import { useConnectionLimits } from '../useConnectionLimits';
import { ConnectionLimitsView } from './ConnectionLimitsView';

export function ConnectionLimits({ provider, api }: { provider: ApiProvider; api: ProviderApi }) {
  const limits = useConnectionLimits(provider, api);
  return <ConnectionLimitsView {...limits} kind={provider.kind} enabled={provider.enabled && provider.keyConfigured} refresh={() => void limits.refresh()} recover={() => void limits.recover()} />;
}
