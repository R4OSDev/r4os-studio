import type { ProviderList } from '../../../../shared/llm-providers.js';

export class ProviderRequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

let loadingRequest: Promise<ProviderList> | null = null;
export function loadProviders(): Promise<ProviderList> {
  if (loadingRequest) return loadingRequest;
  const request = fetch('/api/providers', { cache: 'no-store' }).then(async (response) => {
    if (!response.ok) throw new Error('Provider settings could not be loaded. Please try again.');
    return await response.json() as ProviderList;
  });
  loadingRequest = request;
  void request.finally(() => { if (loadingRequest === request) loadingRequest = null; }).catch(() => {});
  return request;
}

export async function requestProvider<T>(path: string, csrfToken: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api/providers${path}`, {
    method, cache: 'no-store',
    headers: { ...(method !== 'GET' ? { 'X-CSRF-Token': csrfToken } : {}),
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    const result = await response.json().catch(() => ({})) as { message?: string };
    throw new ProviderRequestError(result.message ?? 'The provider request failed. Please try again.', response.status);
  }
  return response.status === 204 ? undefined as T : await response.json() as T;
}
