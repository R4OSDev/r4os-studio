import { useCallback, useEffect, useRef, useState } from 'react';
import type { ProviderList, ProviderUsage } from '../../../../shared/llm-providers.js';
import type { ApiProvider } from '../../../../shared/api-providers.js';
import type { ClaudeSubscriptionProvider } from '../../../../shared/claude-subscription.js';
import { loadProviders, requestProvider } from './api';
import { remainingUsage } from './usage-format';

export function useProviders(usageVisible = true) {
  const [data, setData] = useState<ProviderList>({ providers: [], csrfToken: '', signInAvailable: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [apiProviders, setApiProviders] = useState<ApiProvider[]>([]), [apiError, setApiError] = useState('');
  const [claudeProviders, setClaudeProviders] = useState<ClaudeSubscriptionProvider[]>([]), [claudeError, setClaudeError] = useState('');
  const csrf = useRef('');
  const usageGeneration = useRef(0);
  const usageRequests = useRef<Record<string, number>>({});
  const [remainingByProvider, setRemainingByProvider] = useState<Record<string, number | null>>({});

  const accept = useCallback((next: ProviderList) => {
    // A reconnect can change the account behind an existing provider ID.
    usageGeneration.current++;
    usageRequests.current = {};
    setRemainingByProvider({});
    csrf.current = next.csrfToken;
    setData(next); setError(null); setLoading(false);
  }, []);
  const fail = useCallback((cause: unknown) => {
    setError(cause instanceof Error ? cause.message : 'Provider settings are unavailable.');
    setLoading(false);
  }, []);
  const reload = useCallback(async () => {
    try {
      const next = await loadProviders(); accept(next);
      try { setApiProviders((await requestProvider<{ providers: ApiProvider[] }>('/api-connections', next.csrfToken)).providers); setApiError(''); }
      catch (cause) { setApiError(cause instanceof Error ? cause.message : 'API connections are unavailable.'); }
      try { setClaudeProviders((await requestProvider<{ providers: ClaudeSubscriptionProvider[] }>('/claude-subscriptions', next.csrfToken)).providers); setClaudeError(''); }
      catch (cause) { setClaudeError(cause instanceof Error ? cause.message : 'Claude subscriptions are unavailable.'); }
    } catch (cause) { fail(cause); }
  }, [accept, fail]);

  useEffect(() => {
    let active = true;
    void loadProviders().then(async (next) => {
      if (!active) return; accept(next);
      try {
        const result = await requestProvider<{ providers: ApiProvider[] }>('/api-connections', next.csrfToken);
        if (active) { setApiProviders(result.providers); setApiError(''); }
      } catch (cause) { if (active) setApiError(cause instanceof Error ? cause.message : 'API connections are unavailable.'); }
      try {
        const result = await requestProvider<{ providers: ClaudeSubscriptionProvider[] }>('/claude-subscriptions', next.csrfToken);
        if (active) { setClaudeProviders(result.providers); setClaudeError(''); }
      } catch (cause) { if (active) setClaudeError(cause instanceof Error ? cause.message : 'Claude subscriptions are unavailable.'); }
    }).catch((cause: unknown) => { if (active) fail(cause); });
    return () => { active = false; };
  }, [accept, fail]);

  const rememberUsage = useCallback((id: string, usage: ProviderUsage | null) => {
    const remaining = remainingUsage(usage);
    setRemainingByProvider((previous) => previous[id] === remaining ? previous : { ...previous, [id]: remaining });
  }, []);

  const request = useCallback(<T,>(path: string, method = 'GET', body?: unknown): Promise<T> => {
    const usageId = /^\/([^/?]+)\/usage(?:\/resets)?(?:\?.*)?$/.exec(path)?.[1];
    const generation = usageGeneration.current;
    const sequence = usageId ? (usageRequests.current[usageId] = (usageRequests.current[usageId] ?? 0) + 1) : 0;
    return requestProvider<T>(path, csrf.current, method, body).then((result) => {
      if (usageId && generation === usageGeneration.current && usageRequests.current[usageId] === sequence) {
        rememberUsage(usageId, (result as { usage?: ProviderUsage | null } | null)?.usage ?? null);
      }
      return result;
    }).catch((cause: unknown) => {
      if (usageId && generation === usageGeneration.current && usageRequests.current[usageId] === sequence) rememberUsage(usageId, null);
      throw cause;
    });
  }, [rememberUsage]);

  useEffect(() => {
    if (!usageVisible) return;
    const refresh = () => {
      if (document.hidden) return;
      for (const provider of data.providers) {
        if (provider.type === 'openai' && provider.status === 'connected' && provider.account) {
          void request(`/${provider.id}/usage`).catch(() => { /* Unknown usage is shown as a dash. */ });
        }
      }
    };
    refresh();
    const timer = setInterval(refresh, 60_000);
    document.addEventListener('visibilitychange', refresh);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, [data.providers, request, usageVisible]);

  return { ...data, providers: [...data.providers, ...apiProviders, ...claudeProviders], apiError, claudeError, remainingByProvider, loading, error, reload, request };
}

export type ProviderApi = ReturnType<typeof useProviders>;
