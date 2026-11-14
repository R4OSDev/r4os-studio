import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import type { GitHubIssueOutcome } from '../../../../shared/project-github-issues.js';
import { ProjectError } from '../projects/store.js';

type Action = 'discard' | 'status';

export function issueAction(projects: string, github: string, projectId: string, operation: Action, input: Record<string, unknown>):
Promise<(GitHubIssueOutcome & { text?: string }) | null> {
  return new Promise((resolve, reject) => {
    const bridge = fileURLToPath(new URL('../../../../scripts/project-roadmaps/github_issue_action.py', import.meta.url));
    const child = spawn('/usr/bin/python3', ['-B', bridge, projects, github], {
      stdio: ['pipe', 'pipe', 'ignore'], env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' },
    });
    let output = '', timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; child.kill('SIGKILL'); }, 120_000);
    const unconfirmed = () => new ProjectError('The original GitHub issue outcome is unconfirmed. Reopen its action to reconcile.', 503);
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', part => {
      if (timedOut) return;
      output += part;
      if (output.length > 32768) { timedOut = true; child.kill('SIGKILL'); }
    });
    child.stdin.on('error', () => {});
    child.on('error', () => { clearTimeout(timeout); reject(unconfirmed()); });
    child.once('close', () => {
      clearTimeout(timeout);
      if (timedOut) { reject(unconfirmed()); return; }
      try {
        const value = JSON.parse(output);
        if (typeof value?.error === 'string' && Number.isInteger(value.code)) reject(new ProjectError(value.error, value.code));
        else if (value && Object.hasOwn(value, 'result')) resolve(value.result);
        else reject(unconfirmed());
      } catch { reject(unconfirmed()); }
    });
    child.stdin.end(JSON.stringify({ projectId, operation, input }));
  });
}
