import { useCallback, useEffect, useRef, useState } from 'react';
import type { ProviderList, ProviderUsage } from '../../../../shared/llm-providers.js';
import type { ApiProvider } from '../../../../shared/api-providers.js';
import type { ClaudeSubscriptionProvider } from '../../../../shared/claude-subscription.js';
import { loadProviders, requestProvider } from './api';
import { remainingUsage } from './usage-format';
import type { ConnectionLimits } from '../../../../shared/connection-limits';

export function useProviders(usageVisible = true) {
  const [data, setData] = useState<ProviderList>({ providers: [], csrfToken: '', signInAvailable: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [apiProviders, setApiProviders] = useState<ApiProvider[]>([]), [apiError, setApiError] = useState('');
  const [claudeProviders, setClaudeProviders] = useState<ClaudeSubscriptionProvider[]>([]), [claudeError, setClaudeError] = useState('');
  const csrf = useRef('');
  const usageGeneration = useRef(0);
  const usageRequests = useRef<Record<string, number>>({});
  const accountScopes = useRef<Record<string, string | undefined>>({});
  const connectionScopes = useRef<Record<string, { revision: number; credentialRevision: number; enabled: boolean }>>({});
  const [connectionLimits, setConnectionLimits] = useState<Record<string, ConnectionLimits | null>>({});
  const [remainingByProvider, setRemainingByProvider] = useState<Record<string, number | null>>({});

  const accept = useCallback((next: ProviderList) => {
    // A reconnect can change the account behind an existing provider ID.
    usageGeneration.current++;
    usageRequests.current = {};
    accountScopes.current = Object.fromEntries(next.providers.map(p => [p.id, p.account?.scope]));
    setRemainingByProvider({});
    setConnectionLimits({});
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
      try {
        const providers = (await requestProvider<{ providers: ApiProvider[] }>('/api-connections', next.csrfToken)).providers;
        connectionScopes.current = Object.fromEntries(providers.map(p => [p.id, p]));
        setApiProviders(providers); setApiError('');
      }
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
        if (active) { connectionScopes.current = Object.fromEntries(result.providers.map(p => [p.id, p])); setApiProviders(result.providers); setApiError(''); }
      } catch (cause) { if (active) setApiError(cause instanceof Error ? cause.message : 'API connections are unavailable.'); }
      try {
        const result = await requestProvider<{ providers: ClaudeSubscriptionProvider[] }>('/claude-subscriptions', next.csrfToken);
        if (active) { setClaudeProviders(result.providers); setClaudeError(''); }
      } catch (cause) { if (active) setClaudeError(cause instanceof Error ? cause.message : 'Claude subscriptions are unavailable.'); }
    }).catch((cause: unknown) => { if (active) fail(cause); });
    return () => { active = false; };
  }, [accept, fail]);

  const rememberUsage = useCallback((id: string, usage: ProviderUsage | null) => {
    const remaining = usage?.accountScope && usage.accountScope !== accountScopes.current[id] ? null : remainingUsage(usage);
    setRemainingByProvider((previous) => previous[id] === remaining ? previous : { ...previous, [id]: remaining });
  }, []);

  const request = useCallback(<T,>(path: string, method = 'GET', body?: unknown): Promise<T> => {
    const usageId = /^\/([^/?]+)\/usage(?:\/resets)?(?:\?.*)?$/.exec(path)?.[1];
    const limitId = method === 'GET' ? /^\/api-connections\/([^/?]+)\/limits$/.exec(path)?.[1] : undefined;
    const configId = method === 'GET' ? /^\/api-connections\/([^/?]+)$/.exec(path)?.[1] : undefined;
    const sampleId = usageId ?? limitId ?? (configId ? 'config:'+configId : undefined);
    const generation = usageGeneration.current;
    const sequence = sampleId ? (usageRequests.current[sampleId] = (usageRequests.current[sampleId] ?? 0) + 1) : 0;
    return requestProvider<T>(path, csrf.current, method, body).then((result) => {
      if (usageId && generation === usageGeneration.current && usageRequests.current[usageId] === sequence) {
        rememberUsage(usageId, (result as { usage?: ProviderUsage | null } | null)?.usage ?? null);
      }
      if (limitId && generation === usageGeneration.current && usageRequests.current[limitId] === sequence) {
        const sample = result as ConnectionLimits | null, scope = connectionScopes.current[limitId];
        const accepted = scope?.enabled && sample?.providerId === limitId && sample.configRevision === scope.revision && sample.credentialRevision === scope.credentialRevision ? sample : null;
        setConnectionLimits(previous => ({ ...previous, [limitId]: accepted }));
        const value = accepted?.state !== 'unknown' ? accepted?.remainingPercent : null;
        setRemainingByProvider(previous => ({ ...previous, [limitId]: typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100 ? value : null }));
      }
      if (configId && generation === usageGeneration.current && usageRequests.current['config:'+configId] === sequence) {
        const provider = (result as { provider?: ApiProvider })?.provider, previous = connectionScopes.current[configId];
        if (provider?.id === configId && provider.type === 'api' && (!previous || provider.revision >= previous.revision)) {
          connectionScopes.current[configId] = provider;
          if (!previous || provider.revision !== previous.revision || provider.credentialRevision !== previous.credentialRevision || !provider.enabled) {
            setConnectionLimits(values => ({ ...values, [configId]: null }));
            setRemainingByProvider(values => ({ ...values, [configId]: null }));
          }
          setApiProviders(values => values.map(value => value.id === configId ? provider : value));
        }
      }
      return result;
    }).catch((cause: unknown) => {
      if (usageId && generation === usageGeneration.current && usageRequests.current[usageId] === sequence) rememberUsage(usageId, null);
      if (limitId && generation === usageGeneration.current && usageRequests.current[limitId] === sequence) {
        setConnectionLimits(previous => ({ ...previous, [limitId]: previous[limitId] ? { ...previous[limitId], state: 'stale' } : null }));
      }
      throw cause;
    });
  }, [rememberUsage]);

  useEffect(() => {
    if (!usageVisible) return;
    const refresh = () => {
      if (document.hidden) return;
      for (const provider of data.providers) {
        if (provider.type === 'openai' && provider.status === 'connected' && provider.account) {
          rememberUsage(provider.id, null);
          void request(`/${provider.id}/usage`).catch(() => { /* Unknown usage is shown as a dash. */ });
        }
      }
      for (const provider of apiProviders) {
        if (provider.enabled && provider.keyConfigured && ['claude-plan', 'openrouter'].includes(provider.kind)) {
          void request(`/api-connections/${provider.id}/limits`).catch(() => { /* Cached limits retain their source and stale state. */ });
        }
      }
    };
    refresh();
    const timer = setInterval(refresh, 60_000);
    document.addEventListener('visibilitychange', refresh);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, [data.providers, apiProviders, request, rememberUsage, usageVisible]);

  const managed = new Set(apiProviders.filter(p => p.kind === 'codex-subscription').map(p => p.id));
  return { ...data, nativeProviders: data.providers, providers: [...data.providers.filter(p => !managed.has(p.id)), ...apiProviders, ...claudeProviders], apiError, claudeError, remainingByProvider, connectionLimits, loading, error, reload, request };
}

export type ProviderApi = ReturnType<typeof useProviders>;
