import { useCallback, useEffect, useRef, useState } from 'react';
import type { ProviderList } from '../../../../shared/llm-providers.js';
import { loadProviders, requestProvider } from './api';

export function useProviders() {
  const [data, setData] = useState<ProviderList>({ providers: [], csrfToken: '', signInAvailable: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const csrf = useRef('');

  const accept = useCallback((next: ProviderList) => {
    csrf.current = next.csrfToken;
    setData(next); setError(null); setLoading(false);
  }, []);
  const fail = useCallback((cause: unknown) => {
    setError(cause instanceof Error ? cause.message : 'Provider settings are unavailable.');
    setLoading(false);
  }, []);
  const reload = useCallback(async () => {
    try { accept(await loadProviders()); } catch (cause) { fail(cause); }
  }, [accept, fail]);

  useEffect(() => {
    let active = true;
    void loadProviders().then((next) => { if (active) accept(next); }).catch((cause: unknown) => { if (active) fail(cause); });
    return () => { active = false; };
  }, [accept, fail]);

  const request = useCallback(<T,>(path: string, method = 'GET', body?: unknown): Promise<T> =>
    requestProvider<T>(path, csrf.current, method, body), []);

  return { ...data, loading, error, reload, request };
}

export type ProviderApi = ReturnType<typeof useProviders>;
