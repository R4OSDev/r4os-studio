import type { VmList } from '../../../../shared/virtual-machines.js';
export async function vmRequest<T>(path: string, token = '', method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api/vms${path}`, { method, cache: 'no-store', headers: {
    ...(method !== 'GET' ? { 'X-CSRF-Token': token } : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
  }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(error.message ?? 'The virtual machine request failed.'); }
  return response.status === 204 ? undefined as T : await response.json() as T;
}
export const loadVms = () => vmRequest<VmList>('');
