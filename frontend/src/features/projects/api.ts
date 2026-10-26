export class ProjectRequestError extends Error {
  constructor(message: string, public status = 0) { super(message); }
}

// getRandomValues is also available on the Studio HTTP LAN origin.
export function projectRequestId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export async function studioRequest<T>(base: string, path: string, token = '', method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${base}${path}`, { method, cache: 'no-store', signal,
    headers: { ...(method === 'GET' ? {} : { 'x-csrf-token': token }), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const result = await response.json();
  if (!response.ok) throw new ProjectRequestError(result.message ?? 'The request failed.', response.status);
  return result as T;
}

export function projectRequest<T>(path: string, token = '', method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  return studioRequest<T>('/api/projects', path, token, method, body, signal);
}
