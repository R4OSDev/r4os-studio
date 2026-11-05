import { useCallback } from 'react';
import { useSubscriptionLimits } from '../llm-providers/useSubscriptionLimits';
import { ZaiLimitsView } from '../llm-providers/components/ZaiLimitsView';
import { useSessionApi } from './api';

export function SessionZaiLimits({ base, token, providerId }: { base: string; token: string; providerId: string }) {
  const { request } = useSessionApi();
  const transport = useCallback(<T,>(suffix: string, method = 'GET', body?: unknown) => {
    const path = suffix.startsWith('/requests/') ? base + '/zai-limit-requests/' + suffix.slice(10)
      : base + '/zai-limits' + (suffix === '/check' ? '/check' : '');
    return request<T>(path, token, method, body);
  }, [base, token, request]);
  const limits = useSubscriptionLimits(providerId, transport);
  if (!limits.sample && !limits.loading && !limits.error) return null;
  return <ZaiLimitsView {...limits} compact refresh={() => void limits.refresh()} recover={() => void limits.recover()} />;
}
