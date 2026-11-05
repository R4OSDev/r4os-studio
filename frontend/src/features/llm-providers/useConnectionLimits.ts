import { useCallback } from 'react';
import type { ApiProvider } from '../../../../shared/api-providers';
import type { ConnectionLimits } from '../../../../shared/connection-limits';
import type { ZaiSubscriptionLimits } from '../../../../shared/zai-subscription';
import type { ProviderApi } from './useProviders';
import { useSubscriptionLimits } from './useSubscriptionLimits';
import { zaiSnapshot } from './limit-windows';

/** Shared original-request refresh controls; managed samples never add a poller. */
export function useConnectionLimits(provider: ApiProvider, api: ProviderApi) {
  const { request } = api;
  const zai = provider.kind === 'zai-coding-plan';
  const transport = useCallback(async <T,>(suffix: string, method = 'GET', body?: unknown): Promise<T> => {
    const base = '/api-connections/' + provider.id;
    const endpoint = zai ? '/subscription-limits' : '/limits';
    const path = suffix.startsWith('/requests/') ? base + (zai ? '/subscription-limit-requests/' : '/limit-requests/') + suffix.slice(10)
      : base + endpoint + (suffix === '/check' ? '/check' : '');
    if (zai && suffix === '/limits') {
      const value = await request<ZaiSubscriptionLimits | null>(path);
      return (value ? zaiSnapshot(value) : null) as T;
    }
    return request<T>(path, method, body);
  }, [provider.id, request, zai]);
  const sample = api.connectionLimits[provider.id];
  const matching = sample?.configRevision === provider.revision && sample.credentialRevision === provider.credentialRevision ? sample : null;
  return useSubscriptionLimits<ConnectionLimits>(provider.id, transport, matching, provider.revision);
}
