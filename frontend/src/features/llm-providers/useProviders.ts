import { useCallback, useEffect, useRef, useState } from 'react';
import type { ProviderList, ProviderUsage } from '../../../../shared/llm-providers.js';
import type { ApiProvider } from '../../../../shared/api-providers.js';
import type { ClaudeSubscriptionProvider } from '../../../../shared/claude-subscription.js';
import { loadProviders, requestProvider } from './api';
import { remainingUsage } from './usage-format';
import type { ConnectionLimits } from '../../../../shared/connection-limits';
import type { ZaiSubscriptionLimits } from '../../../../shared/zai-subscription';
import { usageIsStale, zaiSnapshot } from './limit-windows';
import type { UsageObservation } from './limit-windows';

export function useProviders(usageVisible = true) {
  const [data, setData] = useState<ProviderList>({ providers: [], csrfToken: '', signInAvailable: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [apiProviders, setApiProviders] = useState<ApiProvider[]>([]), [apiError, setApiError] = useState('');
  const [claudeProviders, setClaudeProviders] = useState<ClaudeSubscriptionProvider[]>([]), [claudeError, setClaudeError] = useState('');
  const csrf = useRef(''), familyGeneration = useRef(0);
  const usageGeneration = useRef(0);
  const usageRequests = useRef<Record<string, number>>({});
  const accountScopes = useRef<Record<string, string | undefined>>({});
  const zaiFlights = useRef(new Set<string>());
  const connectionScopes = useRef<Record<string, { revision: number; credentialRevision: number; enabled: boolean }>>({});
  const [connectionLimits, setConnectionLimits] = useState<Record<string, ConnectionLimits | null>>({});
  const connectionLimitsRef = useRef(connectionLimits);
  useEffect(() => { connectionLimitsRef.current = connectionLimits; }, [connectionLimits]);
  const [usageByProvider, setUsageByProvider] = useState<Record<string, UsageObservation>>({});
  const [remainingByProvider, setRemainingByProvider] = useState<Record<string, number | null>>({});

  const accept = useCallback((next: ProviderList) => {
    // A reconnect can change the account behind an existing provider ID.
    usageGeneration.current++;
    usageRequests.current = {};
    accountScopes.current = Object.fromEntries(next.providers.map(p => [p.id, p.account?.scope]));
    setRemainingByProvider({});
    setConnectionLimits({});
    setUsageByProvider({});
    csrf.current = next.csrfToken;
    setData(next); setError(null); setLoading(false);
  }, []);
  const fail = useCallback((cause: unknown) => {
    setError(cause instanceof Error ? cause.message : 'Provider settings are unavailable.');
    setLoading(false);
  }, []);
  const acceptConnections = useCallback((providers: ApiProvider[]) => {
    const scopes = Object.fromEntries(providers.map(p => [p.id, p]));
    const changed = Object.entries(connectionScopes.current).filter(([id, old]) => !scopes[id]
      || scopes[id].revision !== old.revision || scopes[id].credentialRevision !== old.credentialRevision || scopes[id].enabled !== old.enabled).map(([id]) => id);
    connectionScopes.current = scopes;
    for (const id of changed) usageRequests.current[id] = (usageRequests.current[id] ?? 0) + 1;
    if (changed.length) {
      setConnectionLimits(previous => ({ ...previous, ...Object.fromEntries(changed.map(id => [id, null])) }));
      setRemainingByProvider(previous => ({ ...previous, ...Object.fromEntries(changed.map(id => [id, null])) }));
    }
    setApiProviders(providers); setApiError('');
  }, []);
  const load = useCallback(async (active: () => boolean = () => true) => {
    const generation = ++familyGeneration.current;
    try {
      const next = await loadProviders();
      if (!active() || generation !== familyGeneration.current) return;
      accept(next);
      const current = () => active() && generation === familyGeneration.current;
      const api = async () => {
        try {
          const result = await requestProvider<{providers:ApiProvider[]}>('/api-connections',next.csrfToken);
          if(current()) acceptConnections(result.providers);
        } catch(cause) { if(current()) setApiError(cause instanceof Error ? cause.message : 'API connections are unavailable.'); }
      };
      const claude = async () => {
        try {
          const result = await requestProvider<{providers:ClaudeSubscriptionProvider[]}>('/claude-subscriptions',next.csrfToken);
          if(current()) { setClaudeProviders(result.providers); setClaudeError(''); }
        } catch(cause) { if(current()) setClaudeError(cause instanceof Error ? cause.message : 'Claude subscriptions are unavailable.'); }
      };
      await Promise.all([api(),claude()]);
    } catch (cause) { if(active() && generation===familyGeneration.current) fail(cause); }
  }, [accept,fail,acceptConnections]);
  const reload = useCallback(() => load(),[load]);
  useEffect(() => {
    let active=true; void Promise.resolve().then(() => { if(active) return load(() => active); });
    return () => { active=false; };
  },[load]);

  const rememberUsage = useCallback((id: string, usage: ProviderUsage | null) => {
    const matching = usage?.accountScope && usage.accountScope !== accountScopes.current[id] ? null : usage;
    const remaining = remainingUsage(matching);
    setRemainingByProvider((previous) => previous[id] === remaining ? previous : { ...previous, [id]: remaining });
    setUsageByProvider(previous => ({ ...previous, [id]: { usage: matching, state: matching ? usageIsStale(matching, Date.now()) ? 'stale' : 'current' : 'unknown', error: null } }));
  }, []);

  const request = useCallback(<T,>(path: string, method = 'GET', body?: unknown): Promise<T> => {
    const usageId = /^\/([^/?]+)\/usage(?:\/resets)?(?:\?.*)?$/.exec(path)?.[1];
    const limit = method === 'GET' ? /^\/api-connections\/([^/?]+)\/(limits|subscription-limits)(?:\?ensureFresh=true)?$/.exec(path) : null;
    const limitId = limit?.[1];
    const configId = method === 'GET' ? /^\/api-connections\/([^/?]+)$/.exec(path)?.[1] : undefined;
    const sampleId = usageId ?? limitId ?? (configId ? 'config:'+configId : undefined);
    const generation = usageGeneration.current;
    const sequence = sampleId ? (usageRequests.current[sampleId] = (usageRequests.current[sampleId] ?? 0) + 1) : 0;
    return requestProvider<T>(path, csrf.current, method, body).then((result) => {
      if (usageId && generation === usageGeneration.current && usageRequests.current[usageId] === sequence) {
        rememberUsage(usageId, (result as { usage?: ProviderUsage | null } | null)?.usage ?? null);
      }
      if (limitId && generation === usageGeneration.current && usageRequests.current[limitId] === sequence) {
        const sample = limit?.[2] === 'subscription-limits' && result ? zaiSnapshot(result as unknown as ZaiSubscriptionLimits) : result as ConnectionLimits | null;
        const scope = connectionScopes.current[limitId];
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
      if (usageId && generation === usageGeneration.current && usageRequests.current[usageId] === sequence) {
        setUsageByProvider(previous => ({ ...previous, [usageId]: { usage: previous[usageId]?.usage ?? null,
          state: previous[usageId]?.usage ? 'stale' : 'unknown', error: 'Usage could not be refreshed. Reload the connection if its account changed.' } }));
      }
      if (limitId && generation === usageGeneration.current && usageRequests.current[limitId] === sequence) {
        setConnectionLimits(previous => ({ ...previous, [limitId]: previous[limitId] ? { ...previous[limitId], state: 'stale' } : null }));
      }
      throw cause;
    });
  }, [rememberUsage]);

  useEffect(() => {
    if (!usageVisible) return;
    let lastAccountRead = 0;
    const refresh = (demand = false) => {
      if (document.hidden) return;
      const accountDue = Date.now() - lastAccountRead >= 60_000;
      if (accountDue) lastAccountRead = Date.now();
      for (const provider of accountDue ? data.providers : []) {
        if (provider.type === 'openai' && provider.status === 'connected' && provider.account) {
          void request(`/${provider.id}/usage`).catch(() => { /* Unknown usage is shown as a dash. */ });
        }
      }
      for (const provider of apiProviders) {
        if (provider.enabled && provider.keyConfigured && provider.kind === 'zai-coding-plan') {
          const pending = connectionLimitsRef.current[provider.id]?.zai?.monitor?.pendingState === 'pending';
          if ((!accountDue && !demand && !pending) || zaiFlights.current.has(provider.id)) continue;
          zaiFlights.current.add(provider.id);
          void request(`/api-connections/${provider.id}/subscription-limits${accountDue || demand ? '?ensureFresh=true' : ''}`)
            .catch(() => { /* Shared state retains the original stale/unknown evidence. */ })
            .finally(() => zaiFlights.current.delete(provider.id));
        } else if (accountDue && provider.enabled && provider.keyConfigured && ['claude-plan', 'openrouter'].includes(provider.kind)) {
          void request(`/api-connections/${provider.id}/limits`).catch(() => { /* Cached limits retain their source and stale state. */ });
        }
      }
    };
    refresh();
    const timer = setInterval(refresh, 2_000);
    const visible = () => refresh(true);
    document.addEventListener('visibilitychange', visible); window.addEventListener('focus', visible);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', visible); window.removeEventListener('focus', visible); };
  }, [data.providers, apiProviders, request, usageVisible]);

  const managed = new Set(apiProviders.filter(p => p.kind === 'codex-subscription').map(p => p.id));
  return { ...data, nativeProviders: data.providers, providers: [...data.providers.filter(p => !managed.has(p.id)), ...apiProviders, ...claudeProviders], apiError, claudeError, remainingByProvider, connectionLimits, usageByProvider, loading, error, reload, request };
}

export type ProviderApi = ReturnType<typeof useProviders>;
