import type { SkillList } from '../../../../shared/skills';
export class SkillError extends Error { constructor(message: string, readonly status: number) { super(message); } }
let loading: Promise<SkillList> | undefined;
export async function request<T>(method: string, path = '', body?: unknown, token?: string): Promise<T> {
  const response = await fetch('/api/skills' + path, { method, cache: 'no-store',
    headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...(token ? { 'X-CSRF-Token': token } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new SkillError(result.message ?? 'The skill request failed.', response.status);
  return result as T;
}
export function loadSkills() {
  if (!loading) { loading = request<SkillList>('GET'); void loading.finally(() => { loading = undefined; }).catch(() => {}); }
  return loading;
}
