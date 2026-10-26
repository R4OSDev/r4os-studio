import type { GitHubConnectionList } from '../../../../shared/github-connections';

// getRandomValues also works on the Studio HTTP LAN origin.
export function connectionRequestId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export class GitHubError extends Error { constructor(message: string, readonly status: number) { super(message); } }
let pending: Promise<GitHubConnectionList> | undefined;
export async function request<T>(method = 'GET', path = '', body?: unknown, csrfToken?: string): Promise<T> {
  const response = await fetch('/api/github' + path, { method, cache: 'no-store',
    headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  if (response.status === 204) return undefined as T;
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new GitHubError(result.message ?? 'GitHub settings could not be loaded.', response.status);
  return result as T;
}
export function loadConnections() {
  if (!pending) {
    pending = request<GitHubConnectionList>();
    void pending.finally(() => { pending = undefined; }).catch(() => {});
  }
  return pending;
}
