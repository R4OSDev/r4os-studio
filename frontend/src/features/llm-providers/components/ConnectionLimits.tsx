import { useCallback } from 'react';
import type { ApiProvider } from '../../../../../shared/api-providers';
import type { ConnectionLimits as Snapshot } from '../../../../../shared/connection-limits';
import type { ProviderApi } from '../useProviders';
import { useSubscriptionLimits } from '../useSubscriptionLimits';
import { ConnectionLimitsView } from './ConnectionLimitsView';

export function ConnectionLimits({ provider, api }: { provider: ApiProvider; api: ProviderApi }) {
  const { request } = api;
  const transport = useCallback(<T,>(suffix: string, method = 'GET', body?: unknown) => {
    const base = '/api-connections/'+provider.id;
    const path = suffix.startsWith('/requests/') ? base+'/limit-requests/'+suffix.slice(10) : base+'/limits'+(suffix === '/check' ? '/check' : '');
    return request<T>(path, method, body);
  }, [provider.id, request]);
  const sample = api.connectionLimits[provider.id];
  const matching = sample?.configRevision === provider.revision && sample.credentialRevision === provider.credentialRevision ? sample : null;
  const limits = useSubscriptionLimits<Snapshot>(provider.id, transport, matching, provider.revision);
  return <ConnectionLimitsView {...limits} kind={provider.kind} enabled={provider.enabled && provider.keyConfigured} refresh={() => void limits.refresh()} recover={() => void limits.recover()} />;
}
