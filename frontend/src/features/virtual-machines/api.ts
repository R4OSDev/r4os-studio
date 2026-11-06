import type { VmList } from '../../../../shared/virtual-machines.js';
export class VmRequestError extends Error { constructor(message: string, public status: number) { super(message); } }
export async function vmRequest<T>(path: string, token = '', method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/vms${path}`, { method, cache: 'no-store', headers: {
    ...(method !== 'GET' ? { 'X-CSRF-Token': token } : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
  }, ...(body === undefined ? {} : { body: JSON.stringify(body) }), ...(signal ? { signal } : {}) });
  if (!response.ok) { const error = await response.json().catch(() => ({})); throw new VmRequestError(error.message ?? 'The virtual machine request failed.', response.status); }
  return response.status === 204 ? undefined as T : await response.json() as T;
}
export const loadVms = (refresh = true, signal?: AbortSignal) => vmRequest<VmList>(refresh ? '?refresh=true' : '', '', 'GET', undefined, signal);

export function vmRequestId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16)); bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const value = Array.from(bytes, (v) => v.toString(16).padStart(2, '0')).join('');
  return `${value.slice(0, 8)}-${value.slice(8, 12)}-${value.slice(12, 16)}-${value.slice(16, 20)}-${value.slice(20)}`;
}
