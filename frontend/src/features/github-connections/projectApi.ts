import type { GitHubJob } from '../../../../shared/project-github';
import { projectRequest } from '../projects/api';

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
