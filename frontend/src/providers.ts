import { useCallback, useEffect, useRef, useState } from 'react';
import type { ProviderList } from '../../shared/providers.js';

let loadingRequest: Promise<ProviderList> | null = null;
function loadProviders(): Promise<ProviderList> {
  if (loadingRequest) return loadingRequest;
  const request = fetch('/api/providers', { cache: 'no-store' }).then(async (response) => {
    if (!response.ok) throw new Error('Provider settings could not be loaded. Please try again.');
    return await response.json() as ProviderList;
  });
  loadingRequest = request;
  void request.finally(() => { if (loadingRequest === request) loadingRequest = null; }).catch(() => {});
  return request;
}

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

  const request = useCallback(async <T,>(path: string, method = 'GET', body?: unknown): Promise<T> => {
    const response = await fetch(`/api/providers${path}`, {
      method, cache: 'no-store',
      headers: { ...(method !== 'GET' ? { 'X-CSRF-Token': csrf.current } : {}),
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (!response.ok) {
      const result = await response.json().catch(() => ({})) as { message?: string };
      throw new Error(result.message ?? 'The provider request failed. Please try again.');
    }
    return response.status === 204 ? undefined as T : await response.json() as T;
  }, []);

  return { ...data, loading, error, reload, request };
}

export type ProviderApi = ReturnType<typeof useProviders>;
