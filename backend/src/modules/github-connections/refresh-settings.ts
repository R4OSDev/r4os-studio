import { join } from 'node:path';
import type { GitHubRefreshSettings } from '../../../../shared/github-connections.js';
import { ProjectError } from '../projects/store.js';
import { githubDirectory, readGitHubJson, saveGitHubJson, withGitHubLock } from './private-storage.js';

const hour = 3_600_000;
const validHours = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value > 0 && value * hour < 8e15;
const dueAt = (now: number, hours: number) => Math.ceil(now + hours * hour);
const defaults: GitHubRefreshSettings = { enabled: true, intervalHours: 1, revision: 0, nextRefreshAt: null };

export class RefreshSettings {
  constructor(readonly directory: string) {}

  private get path() { return join(this.directory, 'refresh-settings.json'); }

  async read() {
    const value = await readGitHubJson<GitHubRefreshSettings>(this.path);
    if (!value) return { ...defaults };
    if (typeof value.enabled !== 'boolean' || !validHours(value.intervalHours)
        || !Number.isSafeInteger(value.revision) || value.revision < 0
        || (value.nextRefreshAt !== null && !Number.isSafeInteger(value.nextRefreshAt))) {
      throw new ProjectError('GitHub refresh settings are invalid.', 503);
    }
    return value;
  }

  async save(input: unknown) {
    const value = input as Partial<GitHubRefreshSettings> | null;
    if (!value || Object.keys(value).length !== 3 || typeof value.enabled !== 'boolean'
        || !validHours(value.intervalHours) || !Number.isSafeInteger(value.revision)) {
      throw new ProjectError('Enter a positive interval in hours.', 400);
    }
    const { enabled, intervalHours, revision } = value;
    const saved = await this.change(async current => {
      if (current.revision !== revision) throw new ProjectError('GitHub refresh settings changed. Reload before saving.', 409);
      return { enabled, intervalHours, revision: current.revision + 1, nextRefreshAt: enabled ? dueAt(Date.now(), intervalHours) : null };
    });
    if (!saved) throw new ProjectError('GitHub refresh settings are busy. Try again.', 409);
    return saved;
  }

  async claim(now: number) {
    return this.change(async current => {
      if (!current.enabled || (current.nextRefreshAt !== null && current.nextRefreshAt > now)) return undefined;
      return { ...current, nextRefreshAt: dueAt(now, current.intervalHours) };
    });
  }

  private async change(change: (current: GitHubRefreshSettings) => Promise<GitHubRefreshSettings | undefined>) {
    await githubDirectory(this.directory);
    return withGitHubLock(join(this.directory, '.refresh-settings.lock'), async () => {
      const value = await change(await this.read());
      if (value) await saveGitHubJson(this.path, value);
      return value;
    });
  }
}
