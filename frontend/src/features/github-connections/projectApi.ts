import type { GitHubJob, GitHubProjectStatus } from '../../../../shared/project-github';
import { projectRequest, projectRequestId, ProjectRequestError } from '../projects/api';
import { editorRegistry } from '../project-editor/registry';

export interface PendingGit { requestId: string; kind: string; input: Record<string, unknown> }
const pendingKey = (id: string) => 'studio.github.pending.' + id;
export function pendingGit(id: string): PendingGit | null {
  try { const value = JSON.parse(sessionStorage.getItem(pendingKey(id)) ?? 'null'); return typeof value?.requestId === 'string' && typeof value.kind === 'string' && value.input ? value : null; } catch { return null; }
}
export function clearGit(id: string) { sessionStorage.removeItem(pendingKey(id)); }
interface PullRequest { prepare: PendingGit; apply?: PendingGit }
const pullKey = (id: string) => 'studio.github.pull.' + id;
export function pendingPull(id: string): PullRequest | null {
  try { const value = JSON.parse(sessionStorage.getItem(pullKey(id)) ?? 'null'); return value?.prepare?.kind === 'prepare_pull' ? value : null; } catch { return null; }
}
export function clearPull(id: string) { sessionStorage.removeItem(pullKey(id)); }
export async function pullProject(id: string, token: string, status: GitHubProjectStatus, changed?: (job: GitHubJob) => void) {
  if (!status.binding) throw new Error('Connect a repository first.');
  if (editorRegistry.hasUnsavedFor(id)) throw new Error('Save or close this project’s editor drafts before Pull.');
  const retained = pendingGit(id), old = pendingPull(id);
  if (retained && retained.requestId !== old?.prepare.requestId && retained.requestId !== old?.apply?.requestId) throw new Error('Reconcile the original Git operation before pulling.');
  const request: PullRequest = old ?? { prepare: { requestId: projectRequestId(), kind: 'prepare_pull', input: { bindingRevision: status.binding.revision, snapshot: status.snapshot, remoteHead: status.remoteHead } } };
  sessionStorage.setItem(pullKey(id), JSON.stringify(request));
  let last: GitHubJob | undefined;
  const progress = (job: GitHubJob) => { last = job; changed?.(job); };
  try {
    if (!request.apply) {
      const prepared = await runGitJob(id, token, 'prepare_pull', request.prepare.input, progress, request.prepare);
      if (prepared.result && 'nothingToPull' in prepared.result && prepared.result.nothingToPull) { clearPull(id); if (prepared.result.commit !== status.head) editorRegistry.workspaceChanged(id); return prepared; }
      await projectRequest(`/${id}/github/pulls/${request.prepare.requestId}/validate`, token, 'POST', {});
      if (editorRegistry.hasUnsavedFor(id)) throw new Error('Editor drafts appeared during validation. Save or close them before applying.');
      request.apply = { requestId: projectRequestId(), kind: 'pull', input: { preparationId: request.prepare.requestId, bindingRevision: request.prepare.input.bindingRevision, snapshot: request.prepare.input.snapshot } };
      sessionStorage.setItem(pullKey(id), JSON.stringify(request));
    }
    const result = await runGitJob(id, token, 'pull', request.apply.input, progress, request.apply);
    clearPull(id); if (result.result && 'pulled' in result.result && result.result.pulled) editorRegistry.workspaceChanged(id); return result;
  } catch (e) {
    const final = last as GitHubJob | undefined;
    if (final?.state === 'failed') clearPull(id);
    if (final?.state === 'unknown') {
      const reconciled = await projectRequest<GitHubJob>(`/${id}/github/jobs/${final.id}/reconcile`, token, 'POST', {}).catch(() => null);
      if (reconciled) changed?.(reconciled);
      if (reconciled?.state === 'completed' && reconciled.result && (('pulled' in reconciled.result && reconciled.result.pulled) || ('nothingApplied' in reconciled.result && reconciled.result.nothingApplied))) { clearGit(id); clearPull(id); if ('pulled' in reconciled.result && reconciled.result.pulled) editorRegistry.workspaceChanged(id); return reconciled; }
    }
    throw e;
  }
}
export async function runGitJob(id: string, token: string, kind: string, input: Record<string, unknown>, changed?: (job: GitHubJob) => void, original?: PendingGit) {
  const read = ['status', 'check', 'diff'].includes(kind);
  if (!read && !original && pendingGit(id)) throw new Error('Recheck the original Git operation before starting another.');
  const request = original ?? { requestId: projectRequestId(), kind, input };
  if (!read) sessionStorage.setItem(pendingKey(id), JSON.stringify(request));
  let accepted: GitHubJob;
  try { accepted = await projectRequest<GitHubJob>(`/${id}/github/jobs`, token, 'POST', request); }
  catch (e) { if (!read && e instanceof ProjectRequestError && e.status >= 400 && e.status < 500) clearGit(id); throw e; }
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
