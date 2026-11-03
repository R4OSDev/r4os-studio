import { useCallback } from 'react';
import type { ApiProvider } from '../../../../../shared/api-providers';
import type { ProviderApi } from '../useProviders';
import { useZaiLimits } from '../useZaiLimits';
import { ZaiLimitsView } from './ZaiLimitsView';

export function ZaiProviderLimits({ provider, api }: { provider: ApiProvider; api: ProviderApi }) {
  const { request } = api;
  const transport = useCallback(<T,>(suffix: string, method = 'GET', body?: unknown) => {
    const base = '/api-connections/' + provider.id;
    const path = suffix.startsWith('/requests/') ? base + '/subscription-limit-requests/' + suffix.slice(10)
      : base + '/subscription-limits' + (suffix === '/check' ? '/check' : '');
    return request<T>(path, method, body);
  }, [provider.id, request]);
  const limits = useZaiLimits(provider.id, transport);
  return <ZaiLimitsView {...limits} enabled={provider.enabled && provider.keyConfigured} refresh={() => void limits.refresh()} recover={() => void limits.recover()} />;
}
