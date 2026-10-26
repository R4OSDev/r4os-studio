import type { GitHubJob } from '../../../../shared/project-github';
import { projectRequest, projectRequestId } from '../projects/api';

export interface PendingGit { requestId: string; kind: string; input: Record<string, unknown> }
const pendingKey = (id: string) => 'studio.github.pending.' + id;
export function pendingGit(id: string): PendingGit | null {
  try { const value = JSON.parse(sessionStorage.getItem(pendingKey(id)) ?? 'null'); return typeof value?.requestId === 'string' && typeof value.kind === 'string' && value.input ? value : null; } catch { return null; }
}
export function clearGit(id: string) { sessionStorage.removeItem(pendingKey(id)); }
export async function runGitJob(id: string, token: string, kind: string, input: Record<string, unknown>, changed?: (job: GitHubJob) => void, original?: PendingGit) {
  const read = ['status', 'check', 'diff'].includes(kind);
  if (!read && !original && pendingGit(id)) throw new Error('Recheck the original Git operation before starting another.');
  const request = original ?? { requestId: projectRequestId(), kind, input };
  if (!read) sessionStorage.setItem(pendingKey(id), JSON.stringify(request));
  const accepted = await projectRequest<GitHubJob>(`/${id}/github/jobs`, token, 'POST', request);
  const job = await waitGitJob(id, request.requestId, accepted, changed);
  if (!read && ['completed', 'failed'].includes(job.state)) clearGit(id);
  if (job.state !== 'completed') throw new Error(job.error ?? 'This operation is uncertain. Reconcile its original request.');
  return job;
}

export async function waitGitJob(projectId: string, requestId: string, initial?: GitHubJob, changed?: (job: GitHubJob) => void, signal?: AbortSignal) {
  let job = initial;
  const deadline = Date.now() + 330_000;
  for (;;) {
    if (signal?.aborted) throw new Error('The view closed. The original Git job was preserved.');
    job ??= await projectRequest<GitHubJob>(`/${projectId}/github/jobs/${requestId}`, '', 'GET', undefined, signal);
    changed?.(job);
    if (!['queued', 'running'].includes(job.state)) return job;
    if (Date.now() > deadline) throw new Error('Git operation has not finished. Recheck the original job; do not create another request.');
    await new Promise((resolve) => window.setTimeout(resolve, 1000)); job = undefined;
  }
}
