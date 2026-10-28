import { useEffect, useRef, useState } from 'react';
import type { GitHubJob, GitHubProjectBinding, GitHubProjectStatus } from '../../../../shared/project-github';
import { projectRequest, projectRequestId } from '../projects/api';
import { pullProject, waitGitJob } from './projectApi';

interface Opening { id: string | null; phase: 'checking' | 'prompt' | 'updating' | 'ready'; status?: GitHubProjectStatus; error?: string; notice?: string }
export function useProjectOpening(id: string | null, token: string) {
  const [value, setValue] = useState<Opening>({ id: null, phase: 'checking' });
  const generation = useRef(0);
  const opened = useRef<string | null>(null);
  useEffect(() => {
    // CSRF rotation is not another project opening. Preserve mounted forms and
    // the user's existing Update/Ignore decision when refreshing browser auth.
    if (id && opened.current === id) return;
    opened.current = null;
    const controller = new AbortController(), current = ++generation.current;
    const timer = window.setTimeout(() => {
      if (!id || !token) return;
      setValue({ id, phase: 'checking' });
      void (async () => {
        try {
          const bound = await projectRequest<{ binding: GitHubProjectBinding | null }>(`/${id}/github`, '', 'GET', undefined, controller.signal);
          if (!bound.binding) { if (!controller.signal.aborted && generation.current === current) { opened.current = id; setValue({ id, phase: 'ready' }); } return; }
          const requestId = projectRequestId();
          const accepted = await projectRequest<GitHubJob>(`/${id}/github/jobs`, token, 'POST', { requestId, kind: 'check', input: {} }, controller.signal);
          const job = await waitGitJob(id, requestId, accepted, undefined, controller.signal);
          if (controller.signal.aborted || generation.current !== current) return;
          if (job.state !== 'completed' || !job.result || !('snapshot' in job.result)) throw new Error(job.error ?? 'Remote state could not be checked.');
          const status = job.result;
          opened.current = id;
          setValue({ id, phase: status.behind > 0 && ['behind', 'diverged'].includes(status.state) ? 'prompt' : 'ready', status });
        } catch (e) {
          if (!controller.signal.aborted && generation.current === current) { opened.current = id; setValue({ id, phase: 'ready', notice: 'GitHub status unavailable: ' + (e as Error).message }); }
        }
      })();
    }, 0);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [id, token]);
  async function update() {
    if (!id || value.id !== id || value.phase !== 'prompt' || !value.status) return;
    const current = generation.current, status = value.status;
    setValue({ ...value, phase: 'updating', error: '' });
    try {
      const result = await pullProject(id, token, status);
      if (generation.current !== current) return;
      if (result.result && 'nothingApplied' in result.result && result.result.nothingApplied) throw new Error('No update was applied. Review the original operation in GitHub or choose Ignore.');
      setValue({ id, phase: 'ready' });
    } catch (e) { if (generation.current === current) setValue({ id, phase: 'prompt', status, error: (e as Error).message }); }
  }
  return {
    ready: value.id === id && value.phase === 'ready',
    deciding: value.id === id && ['prompt', 'updating'].includes(value.phase),
    updating: value.id === id && value.phase === 'updating',
    status: value.id === id ? value.status : undefined,
    notice: value.id === id ? value.notice : '', error: value.id === id ? value.error : '',
    ignore: () => { if (id && value.id === id && value.phase === 'prompt') setValue({ id, phase: 'ready' }); },
    update,
  };
}
