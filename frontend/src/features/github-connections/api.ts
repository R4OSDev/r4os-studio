import type { GitHubConnectionList } from '../../../../shared/github-connections';
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
