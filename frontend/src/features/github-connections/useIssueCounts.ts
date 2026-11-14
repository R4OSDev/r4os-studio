import { useEffect, useState } from 'react';
import type { GitHubIssueCount } from '../../../../shared/project-github-issues';
import { projectRequest } from '../projects/api';

export const issueCountChanged = 'studio-github-issue-count-changed';
export const issueCountText = (value: GitHubIssueCount) =>
  value.count === null ? value.state === 'unknown' ? 'Open issue count not checked' : 'Open issue count unavailable'
    : `${value.count} open issue${value.count === 1 ? '' : 's'}${value.state === 'stale' ? ' · Out of date' : ''}`
      + (value.checkedAt ? ' · Checked ' + new Date(value.checkedAt).toLocaleString() : '');

export function useIssueCounts(ready: boolean) {
  const [counts, setCounts] = useState<Record<string, GitHubIssueCount>>({});
  useEffect(() => {
    if (!ready) return;
    let request: AbortController | undefined;
    let disposed = false;
    const load = async () => {
      if (disposed || document.hidden) return;
      request?.abort();
      const controller = new AbortController();
      request = controller;
      try {
        const data = await projectRequest<{ counts: Record<string, GitHubIssueCount> }>('/github/issue-counts', '', 'GET', undefined, controller.signal);
        if (!controller.signal.aborted) setCounts(data.counts ?? {});
      } catch {
        if (!controller.signal.aborted) setCounts({});
      }
    };
    const update = () => { void load(); };
    const interval = window.setInterval(update, 15_000);
    const initial = window.setTimeout(update, 0);
    window.addEventListener('focus', update);
    window.addEventListener(issueCountChanged, update);
    window.addEventListener('studio-project-github-changed', update);
    document.addEventListener('visibilitychange', update);
    return () => {
      disposed = true; request?.abort();
      window.clearTimeout(initial); window.clearInterval(interval);
      window.removeEventListener('focus', update);
      window.removeEventListener(issueCountChanged, update);
      window.removeEventListener('studio-project-github-changed', update);
      document.removeEventListener('visibilitychange', update);
    };
  }, [ready]);
  return ready ? counts : {};
}
