import { createHash } from 'node:crypto';
import { join } from 'node:path';
import type { GitHubIssuePage } from '../../../../shared/project-github-issues.js';
import type { GitHubProjectBinding, GitHubProjectStatus } from '../../../../shared/project-github.js';
import { githubDirectory, readGitHubJson, saveGitHubJson, withGitHubLock } from '../github-connections/private-storage.js';

export const bindingKey = (binding: GitHubProjectBinding) => JSON.stringify([
  binding.revision, binding.connectionId, binding.userId, binding.repository.id, binding.repository.owner, binding.repository.name, binding.branch,
]);
export const observationKey = (projectId: string, binding: GitHubProjectBinding, credentialRevision: number) =>
  createHash('sha256').update(JSON.stringify([projectId, bindingKey(binding), credentialRevision])).digest('hex');

export type SavedIssuePage = Omit<GitHubIssuePage, 'nextCursor' | 'expiresAt' | 'cached'> & { after: string | null };
type Observation<T> = { scope: string; started: number; value: T | null; error?: string };
type IssueObservation = Observation<{ openCount: number; checkedAt: string; openPage?: SavedIssuePage }>;

export class GitHubObservations {
  readonly directory: string;
  constructor(directory: string) { this.directory = join(directory, 'Observations'); }

  async issues(id: string, scope: string): Promise<IssueObservation | null> {
    return this.read('issues', id, scope);
  }

  async status(id: string, scope: string): Promise<Observation<GitHubProjectStatus> | null> {
    return this.read('status', id, scope);
  }

  async saveIssues(id: string, scope: string, started: number, value: SavedIssuePage, firstPage: boolean) {
    await this.write<IssueObservation['value']>('issues', id, scope, started, previous => ({
      scope, started,
      value: { openCount: value.openCount, checkedAt: value.checkedAt, openPage: firstPage ? value : previous?.value?.openPage },
    }));
  }

  async issueFailure(id: string, scope: string, started: number, error: string, revoke: boolean) {
    await this.write<IssueObservation['value']>('issues', id, scope, started, previous =>
      ({ scope, started, value: revoke ? null : previous?.value ?? null, error }));
  }

  async saveStatus(id: string, scope: string, started: number, value: GitHubProjectStatus | null, error?: string, revoke = false) {
    await this.write<GitHubProjectStatus>('status', id, scope, started, previous =>
      ({ scope, started, value: value ?? (revoke ? null : previous?.value ?? null), ...(error ? { error } : {}) }));
  }

  private async read<T>(kind: 'issues' | 'status', id: string, scope: string): Promise<Observation<T> | null> {
    const value = await readGitHubJson<Observation<T>>(join(this.directory, id + '.' + kind + '.json'));
    return value?.scope === scope ? value : null;
  }

  private async write<T>(kind: 'issues' | 'status', id: string, scope: string, started: number,
    update: (previous: Observation<T> | null) => Observation<T>) {
    await githubDirectory(this.directory);
    const path = join(this.directory, id + '.' + kind + '.json');
    for (let attempt = 0; attempt < 20; attempt++) {
      const saved = await withGitHubLock(path + '.lock', async () => {
        const previous = await readGitHubJson<Observation<T>>(path);
        if (!previous || previous.started <= started) await saveGitHubJson(path, update(previous?.scope === scope ? previous : null));
        return true;
      });
      if (saved) return;
      await new Promise(resolve => setTimeout(resolve, 20));
    }
    throw new Error('GitHub observation is busy.');
  }
}
