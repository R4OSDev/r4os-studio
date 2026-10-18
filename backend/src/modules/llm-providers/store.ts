import { mkdir, readFile, writeFile, rename, chmod } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { join } from 'node:path';
import type { Provider } from '../../../../shared/llm-providers.js';

export type ProviderRecord = Omit<Provider, 'status'> & { connected: boolean };
export const validProviderId = (value: string) => /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(value);

export class ProviderStore {
  private records: ProviderRecord[] = [];
  private ready: Promise<void>;
  private queue: Promise<unknown> = Promise.resolve();

  constructor(readonly directory: string) {
    this.ready = this.load();
    void this.ready.catch(() => {});
  }

  private async load() {
    await mkdir(this.directory, { recursive: true, mode: 0o700 });
    await chmod(this.directory, 0o700);
    try {
      const data: unknown = JSON.parse(await readFile(join(this.directory, 'providers.json'), 'utf8'));
      if (!Array.isArray(data) || !data.every((entry) => entry && validProviderId(entry.id) && entry.type === 'openai'
        && typeof entry.name === 'string' && typeof entry.connected === 'boolean' && typeof entry.createdAt === 'string')) {
        throw new Error('Invalid provider storage.');
      }
      this.records = data;
    } catch (error) {
      if (!(error instanceof Error && 'code' in error && error.code === 'ENOENT')) throw error;
    }
  }

  async list(): Promise<ProviderRecord[]> {
    await this.ready;
    await this.queue;
    return structuredClone(this.records);
  }

  async change(update: (records: ProviderRecord[]) => void): Promise<void> {
    const result = this.queue.then(async () => {
      await this.ready;
      const next = structuredClone(this.records);
      update(next);
      const destination = join(this.directory, 'providers.json');
      const temporary = `${destination}.${randomUUID()}.tmp`;
      await writeFile(temporary, JSON.stringify(next, null, 2) + '\n', { mode: 0o600, flag: 'wx' });
      await rename(temporary, destination);
      this.records = next;
    });
    this.queue = result.catch(() => {});
    await result;
  }

  async home(id: string): Promise<string> {
    if (!validProviderId(id)) throw new Error('Invalid provider ID.');
    await this.ready;
    const directory = join(this.directory, id);
    await mkdir(directory, { recursive: true, mode: 0o700 });
    return directory;
  }
}
