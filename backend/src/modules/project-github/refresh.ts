import { randomUUID } from 'node:crypto';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import type { GitHubJob, GitHubProjectBinding, GitHubProjectStatus } from '../../../../shared/project-github.js';
import { projectBinding } from '../github-connections/references.js';
import { GitHubStore } from '../github-connections/store.js';
import { RefreshSettings } from '../github-connections/refresh-settings.js';
import { githubDirectory, withGitHubLock } from '../github-connections/private-storage.js';
import { listProjects, ProjectError, projectStore } from '../projects/store.js';
import { gitHost } from './client.js';
import { GitHubIssues } from './issues.js';
import { bindingKey, GitHubObservations, observationKey } from './observations.js';

export class ProjectGitHubRefresh {
  nextDelay = 10_000;
  readonly issues: GitHubIssues;
  readonly settings: RefreshSettings;
  readonly observations: GitHubObservations;
  private readonly credentials: GitHubStore;
  private readonly checks = new Map<string, Promise<GitHubProjectStatus>>();

  constructor(readonly projects: string, readonly directory: string, transport: typeof fetch = fetch) {
    this.credentials = new GitHubStore(directory);
    this.settings = new RefreshSettings(directory);
    this.observations = new GitHubObservations(directory);
    this.issues = new GitHubIssues(this.credentials, id => this.readBinding(id), transport, this.observations,
      async () => (await this.settings.read()).intervalHours * 3_600_000);
  }

  async readBinding(id: string) {
    const project = await projectStore<{ deleting?: boolean }>(this.projects, { operation: 'get_settings', id });
    if (project.deleting) throw new ProjectError('The project is being deleted. GitHub is unavailable.', 409);
    return projectBinding(this.projects, id);
  }

  async scope(id: string, binding: GitHubProjectBinding) {
    const { connection } = await this.credentials.credential(binding.connectionId);
    return observationKey(id, binding, connection.tokenRevision);
  }

  async status(id: string) {
    const binding = await this.readBinding(id);
    if (!binding) return { status: null };
    const scope = await this.scope(id, binding);
    const saved = await this.observations.status(id, scope);
    if (!saved) return { status: null };
    const current = await this.readBinding(id);
    if (!current || await this.scope(id, current) !== scope) throw new ProjectError('The repository connection changed.', 409);
    if (!saved.value) return { status: null, error: saved.error };
    const age = (await this.settings.read()).intervalHours * 3_600_000;
    return { status: { ...saved.value, fresh: false, ...(saved.error || Date.now() - Date.parse(saved.value.checkedAt!) >= age ? { stale: true } : {}) },
      error: saved.error };
  }

  async check(id: string, binding: GitHubProjectBinding, requestId: string = randomUUID(), signal?: AbortSignal) {
    const scope = await this.scope(id, binding);
    let pending = this.checks.get(scope);
    if (!pending) {
      pending = this.checkRemote(id, binding, scope, requestId, signal);
      this.checks.set(scope, pending);
      void pending.finally(() => this.checks.delete(scope)).catch(() => {});
    }
    return pending;
  }

  private async checkRemote(id: string, binding: GitHubProjectBinding, scope: string, requestId: string, signal?: AbortSignal) {
    const started = Date.now();
    try {
      signal?.throwIfAborted();
      let job = await gitHost<GitHubJob>({ operation: 'submit', projectId: id, requestId, kind: 'check', input: { bindingRevision: binding.revision } });
      const original = job.id;
      const end = started + 310_000;
      for (;;) {
        if (job.id !== original || job.projectId !== id || job.kind !== 'check') throw new ProjectError('The original GitHub check could not be matched.');
        if (job.state !== 'queued' && job.state !== 'running') break;
        if (Date.now() >= end) throw new ProjectError('The original GitHub check remains pending.', 503);
        await delay(1000, undefined, { signal });
        job = await gitHost<GitHubJob>({ operation: 'job', projectId: id, requestId: original });
      }
      const result = job.result;
      if (job.state !== 'completed' || !result || !('snapshot' in result) || !result.binding || !result.fresh
          || !result.checkedAt || !Number.isFinite(Date.parse(result.checkedAt)) || bindingKey(result.binding) !== bindingKey(binding)) {
        throw new ProjectError(job.error ?? 'GitHub did not confirm this branch check.', job.code || 503);
      }
      const current = await this.readBinding(id);
      if (!current || await this.scope(id, current) !== scope) throw new ProjectError('The repository connection changed.', 409);
      await this.observations.saveStatus(id, scope, started, result);
      return result;
    } catch (error) {
      if (error instanceof ProjectError) await this.observations.saveStatus(id, scope, started, null, error.message,
        [401, 403, 404].includes(error.statusCode));
      throw error;
    }
  }

  async runDue(signal: AbortSignal, now = Date.now()) {
    const due = await this.settings.read();
    this.nextDelay = due.enabled && due.nextRefreshAt !== null ? Math.max(250, Math.min(10_000, due.nextRefreshAt - now)) : 10_000;
    if (!due.enabled || (due.nextRefreshAt !== null && due.nextRefreshAt > now)) return false;
    await githubDirectory(this.directory);
    return withGitHubLock(join(this.directory, '.refresh-run.lock'), async () => {
      if (signal.aborted) return false;
      const settings = await this.settings.claim(now);
      if (!settings) return false;
      const current = async () => !signal.aborted && (await this.settings.read()).revision === settings.revision;
      const projects = await listProjects(this.projects);
      for (const project of projects) {
        if (!await current()) break;
        if (project.deleting) continue;
        const binding = await this.readBinding(project.id).catch(() => null);
        if (!binding || !await current()) continue;
        await this.issues.read(project.id, binding.revision, 'open', null, true).catch(() => null);
        if (!await current()) break;
        if (!await this.issues.onCooldown(binding.userId)) await this.check(project.id, binding, undefined, signal).catch(() => null);
      }
      return true;
    });
  }
}
