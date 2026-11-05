import { useCallback } from 'react';
import type { ConnectionLimits } from '../../../../shared/connection-limits';
import { useSubscriptionLimits } from '../llm-providers/useSubscriptionLimits';
import { ConnectionLimitsView } from '../llm-providers/components/ConnectionLimitsView';
import { useSessionApi } from './api';

export function SessionConnectionLimits({ base, token, providerId }: { base: string; token: string; providerId: string }) {
  const { request } = useSessionApi();
  const transport = useCallback(<T,>(suffix: string, method = 'GET', body?: unknown) => {
    const path = suffix.startsWith('/requests/') ? base+'/connection-limit-requests/'+suffix.slice(10) : base+'/connection-limits'+(suffix === '/check' ? '/check' : '');
    return request<T>(path, token, method, body);
  }, [base, token, request]);
  const limits = useSubscriptionLimits<ConnectionLimits>(providerId, transport);
  if (!limits.sample && !limits.loading && !limits.error) return null;
  return <ConnectionLimitsView {...limits} compact refresh={() => void limits.refresh()} recover={() => void limits.recover()} />;
}
