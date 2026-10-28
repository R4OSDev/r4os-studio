import type { RemoteHost, RemoteHostInput, RemoteHostChange, RemoteHostRemoval, RemoteHostList, RemoteHostCapabilities, RemoteHostCheck } from '../../../../shared/remote-hosts';
import type { RemoteJobSummary, RemoteJobDetail, RemoteReviewInput, RemoteReviewReceipt } from '../../../../shared/remote-hosts';

export class RemoteHostRequestError extends Error { constructor(message: string, public status: number) { super(message); } }
async function request<T>(path: string, method = 'GET', body?: unknown, token?: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch('/api/remote-hosts' + path, { method, signal, credentials: 'same-origin',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json', 'X-CSRF-Token': token ?? '' }, body: body === undefined ? undefined : JSON.stringify(body) });
  const value = await response.json();
  if (!response.ok) throw new RemoteHostRequestError(value.message ?? 'Remote Host request failed.', response.status);
  return value as T;
}
export const listHosts = (signal?: AbortSignal) => request<RemoteHostList>('', 'GET', undefined, undefined, signal);
export const getHost = (id: string, signal?: AbortSignal) => request<RemoteHost>('/' + encodeURIComponent(id), 'GET', undefined, undefined, signal);
export const createHost = (body: RemoteHostInput, token: string) => request<RemoteHost>('', 'POST', body, token);
export const updateHost = (id: string, body: RemoteHostChange, token: string) => request<RemoteHost>('/' + encodeURIComponent(id), 'PATCH', body, token);
export const removeHost = (id: string, body: RemoteHostRemoval, token: string) => request<{ id: string; removed: true }>('/' + encodeURIComponent(id), 'DELETE', body, token);
export const hostCapabilities = (signal?: AbortSignal) => request<RemoteHostCapabilities>('/capabilities', 'GET', undefined, undefined, signal);
export const checkHost = (id: string, body: { requestId: string; revision: number }, token: string) => request<RemoteHostCheck>('/' + encodeURIComponent(id) + '/test', 'POST', body, token);
export const readHostCheck = (id: string, requestId: string, signal?: AbortSignal) => request<RemoteHostCheck>('/' + encodeURIComponent(id) + '/tests/' + encodeURIComponent(requestId), 'GET', undefined, undefined, signal);
export const resetHostTrust = (id: string, body: RemoteHostRemoval, token: string) => request<RemoteHost>('/' + encodeURIComponent(id) + '/trust', 'POST', body, token);
const jobPath = (hostId: string, projectId: string, jobId: string) => '/' + encodeURIComponent(hostId) + '/jobs/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(jobId);
export const listHostJobs = (hostId: string, signal?: AbortSignal) => request<{ jobs: RemoteJobSummary[]; truncated: boolean }>('/' + encodeURIComponent(hostId) + '/jobs', 'GET', undefined, undefined, signal);
export const getHostJob = (hostId: string, projectId: string, jobId: string, signal?: AbortSignal) => request<RemoteJobDetail>(jobPath(hostId, projectId, jobId), 'GET', undefined, undefined, signal);
export const reviewHostJob = (hostId: string, projectId: string, jobId: string, body: RemoteReviewInput, token: string) => request<RemoteReviewReceipt>(jobPath(hostId, projectId, jobId) + '/review', 'POST', body, token);
export const getHostReview = (hostId: string, projectId: string, jobId: string, requestId: string, signal?: AbortSignal) => request<RemoteReviewReceipt>(jobPath(hostId, projectId, jobId) + '/reviews/' + encodeURIComponent(requestId), 'GET', undefined, undefined, signal);
