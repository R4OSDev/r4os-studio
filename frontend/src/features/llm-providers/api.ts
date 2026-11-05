import { invalidateSessionReads, sessionReadIdentity, sessionReadMetadata } from '../agent-sessions/sessionReads';
import type { ProviderList } from '../../../../shared/llm-providers.js';

// getRandomValues is also available on the Studio HTTP LAN origin.
export function providerRequestId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export class ProviderRequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

let loadingRequest: Promise<ProviderList> | null = null;
export function loadProviders(): Promise<ProviderList> {
  if (loadingRequest) return loadingRequest;
  const request = fetch('/api/providers', { cache: 'no-store' }).then(async (response) => {
    if (!response.ok) throw new Error('Provider settings could not be loaded. Please try again.');
    const result = await response.json() as ProviderList;
    sessionReadIdentity('/api/providers',result.csrfToken);
    sessionReadMetadata('native-accounts',result.providers.map(p=>[p.id,p.status,p.account?.scope,p.account?.workspaceId]));
    return result;
  });
  loadingRequest = request;
  void request.finally(() => { if (loadingRequest === request) loadingRequest = null; }).catch(() => {});
  return request;
}

export async function requestProvider<T>(path: string, csrfToken: string, method = 'GET', body?: unknown): Promise<T> {
  if (method !== 'GET') invalidateSessionReads('options');
  try {
    const response = await fetch(`/api/providers${path}`, {
      method, cache: 'no-store',
      headers: { ...(method !== 'GET' ? { 'X-CSRF-Token': csrfToken } : {}),
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (!response.ok) {
      if(response.status===403)invalidateSessionReads(undefined,false);
      const result = await response.json().catch(() => ({})) as { message?: string };
      throw new ProviderRequestError(result.message ?? 'The provider request failed. Please try again.', response.status);
    }
    const result = response.status === 204 ? undefined as T : await response.json() as T;
    if (method === 'GET' && (/^\/api-connections(?:\/[^/?]+)?$/.test(path) || /\/(models|catalog)$/.test(path) || path === '/claude-subscriptions')) {
      sessionReadMetadata('provider:'+path,result);
    }
    return result;
  } finally { if (method !== 'GET') invalidateSessionReads('options'); }
}
