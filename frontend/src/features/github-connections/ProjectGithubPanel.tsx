import { useCallback, useEffect, useState } from 'react';
import type { GitHubJob, GitHubProjectBinding } from '../../../../shared/project-github';
import { projectRequest } from '../projects/api';

export function ProjectGithubPanel({ id, token }: { id: string; token: string }) {
  const [value, setValue] = useState<{ binding: GitHubProjectBinding | null; job?: GitHubJob | null }>();
  const [error, setError] = useState('');
  const refresh = useCallback(() => {
    void projectRequest<{ binding: GitHubProjectBinding | null; job?: GitHubJob | null }>(`/${id}/github`)
      .then((v) => { setValue(v); setError(''); }).catch((e: Error) => setError(e.message));
  }, [id]);
  useEffect(() => { const timer = window.setTimeout(refresh, 0); return () => window.clearTimeout(timer); }, [refresh]);
  async function reconcile() {
    if (!value?.job) return;
    try { await projectRequest(`/${id}/github/jobs/${value.job.id}/reconcile`, token, 'POST', {}); refresh(); }
    catch (e) { setError((e as Error).message); }
  }
  return <section className="github-panel" aria-label="Project GitHub">
    {!value && !error && <p role="status">Loading GitHub binding…</p>}
    {value?.binding ? <><p><a href={value.binding.repository.url} target="_blank" rel="noreferrer">{value.binding.repository.fullName}</a></p>
      <p>Branch: {value.binding.branch}</p><p>Repository connected.</p>
      <p>Commit author: {value.binding.author.name} &lt;{value.binding.author.email}&gt;</p>
    </> : value && <p>No GitHub repository connected.</p>}
    {value?.job && <><p role="status">Last operation: {value.job.kind} · {value.job.state} · {value.job.phase}</p>
      {value.job.error && <p role="alert">{value.job.error}</p>}
      {value.job.state === 'unknown' && <button type="button" onClick={() => void reconcile()}>Reconcile original operation</button>}
      {value.job.kind === 'create_repository' && value.job.state === 'completed' && <p>Not pushed yet. Your project files remain local.</p>}
    </>}
    {error && <p role="alert">{error}</p>}
    <button type="button" onClick={refresh}>Refresh</button>
  </section>;
}
