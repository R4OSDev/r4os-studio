import { constants } from 'node:fs';
import { mkdir, open, rename, unlink, lstat, chmod } from 'node:fs/promises';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import type { GitHubConnection, GitHubConnectionChange, GitHubConnectionInput } from '../../../../shared/github-connections.js';
import { ProjectError } from '../projects/store.js';

interface PrivateConnection extends GitHubConnection { token: string }
interface Catalog { schema: 1; connections: PrivateConnection[]; deletedIds: string[] }
const uuid = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(value);
const validName = (value: unknown): value is string => typeof value === 'string' && !!value.trim() && value.length <= 120 && !/[\p{Cc}\p{Cs}]/u.test(value);
const validToken = (value: unknown): value is string => typeof value === 'string' && /^[\x21-\x7e]{20,4096}$/.test(value);
const revision = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) > 0;
const publicConnection = (v: PrivateConnection): GitHubConnection => ({ id: v.id, name: v.name, revision: v.revision,
  hasToken: true, createdAt: v.createdAt, updatedAt: v.updatedAt });
export const connectionId = (id: unknown) => { if (!uuid(id)) throw new ProjectError('Invalid connection ID.', 400); };
const exact = (value: unknown, required: string[], optional: string[] = []): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value) && required.every((k) => Object.hasOwn(value, k))
    && Object.keys(value).every((k) => [...required, ...optional].includes(k));

export function createInput(value: unknown): GitHubConnectionInput {
  if (!exact(value, ['id', 'name', 'token']) || !uuid(value.id) || !validName(value.name) || !validToken(value.token)) {
    throw new ProjectError('Enter a connection name (up to 120 characters) and a token (20–4096 characters, without spaces).', 400);
  }
  return { id: value.id, name: value.name.trim(), token: value.token };
}
export function changeInput(value: unknown): GitHubConnectionChange {
  if (!exact(value, ['revision', 'name'], ['token']) || !revision(value.revision) || !validName(value.name)
    || (Object.hasOwn(value, 'token') && !validToken(value.token))) throw new ProjectError('Invalid connection changes.', 400);
  return { revision: value.revision, name: value.name.trim(), ...(Object.hasOwn(value, 'token') ? { token: value.token as string } : {}) };
}
export function deleteInput(value: unknown): number {
  if (!exact(value, ['revision']) || !revision(value.revision)) throw new ProjectError('Invalid connection revision.', 400);
  return value.revision;
}

/** Private disk snapshot; only explicit public projections leave this module. */
export class GitHubStore {
  constructor(readonly directory: string) {}
  private async prepare() {
    await mkdir(this.directory, { recursive: true, mode: 0o700 });
    const info = await lstat(this.directory);
    if (!info.isDirectory() || info.isSymbolicLink()) throw new ProjectError('GitHub storage needs host maintenance.', 503);
    await chmod(this.directory, 0o700);
  }
  private async load(): Promise<Catalog> {
    const file = await open(join(this.directory, 'connections.json'), constants.O_RDONLY | constants.O_NOFOLLOW).catch((e: NodeJS.ErrnoException) => {
      if (e.code === 'ENOENT') return null; throw e;
    });
    if (!file) return { schema: 1, connections: [], deletedIds: [] };
    try {
      const stat = await file.stat();
      if (!stat.isFile() || stat.size > 8 * 1024 * 1024 || (stat.mode & 0o077)) throw new Error('Invalid storage.');
      const data = JSON.parse(await file.readFile('utf8')) as Catalog;
      if (data.schema !== 1 || !Array.isArray(data.connections) || data.connections.length > 1000
        || !Array.isArray(data.deletedIds) || !data.deletedIds.every(uuid) || data.deletedIds.length > 10000
        || !data.connections.every((v) => v && uuid(v.id) && validName(v.name) && validToken(v.token) && revision(v.revision)
          && typeof v.createdAt === 'string' && typeof v.updatedAt === 'string')
        || new Set(data.connections.map((v) => v.id)).size !== data.connections.length
        || data.connections.some((v) => data.deletedIds.includes(v.id))) throw new Error('Invalid storage.');
      return data;
    } finally { await file.close(); }
  }
  private async guarded<T>(operation: () => Promise<T>): Promise<T> {
    try { await this.prepare(); return await operation(); }
    catch (e) { if (e instanceof ProjectError) throw e; throw new ProjectError('GitHub storage is unavailable. Existing data was preserved.', 503); }
  }
  async list() { return this.guarded(async () => (await this.load()).connections.map(publicConnection)); }
  private async change<T>(operation: (catalog: Catalog) => T): Promise<T> {
    return this.guarded(async () => {
      const lock = await open(join(this.directory, '.write.lock'), 'wx', 0o600).catch(() => {
        throw new ProjectError('GitHub storage is busy. Retry; a persistent lock requires host maintenance.', 409);
      });
      const temporary = join(this.directory, `.connections-${randomUUID()}.tmp`);
      try {
        const data = await this.load(), result = operation(data);
        const file = await open(temporary, 'wx', 0o600);
        try { await file.writeFile(JSON.stringify(data) + '\n'); await file.sync(); } finally { await file.close(); }
        await rename(temporary, join(this.directory, 'connections.json'));
        const parent = await open(this.directory, constants.O_RDONLY | constants.O_DIRECTORY);
        try { await parent.sync(); } finally { await parent.close(); }
        return result;
      } finally {
        await lock.close(); await unlink(join(this.directory, '.write.lock'));
        await unlink(temporary).catch(() => {});
      }
    });
  }
  async create(input: GitHubConnectionInput) {
    return this.change((data) => {
      const previous = data.connections.find((v) => v.id === input.id);
      if (previous?.name === input.name && previous.token === input.token) return publicConnection(previous);
      if (previous || data.deletedIds.includes(input.id)) throw new ProjectError('This connection ID has already been used. Reload connections.', 409);
      if (data.connections.length >= 1000) throw new ProjectError('The connection limit has been reached.', 409);
      const now = new Date().toISOString();
      const next = { ...input, revision: 1, hasToken: true, createdAt: now, updatedAt: now };
      data.connections.push(next); return publicConnection(next);
    });
  }
  async update(id: string, input: GitHubConnectionChange) {
    return this.change((data) => {
      const value = data.connections.find((v) => v.id === id);
      if (!value) throw new ProjectError('Connection not found. Reload connections.', 404);
      const same = value.name === input.name && (input.token === undefined || input.token === value.token);
      if (value.revision !== input.revision && !(same && value.revision === input.revision + 1)) throw new ProjectError('This connection changed. Reload before saving.', 409);
      if (!same) { value.name = input.name; if (input.token !== undefined) value.token = input.token;
        value.revision++; value.updatedAt = new Date().toISOString(); }
      return publicConnection(value);
    });
  }
  async remove(id: string, expected: number) {
    await this.change((data) => {
      const value = data.connections.find((v) => v.id === id);
      if (!value && data.deletedIds.includes(id)) return;
      if (!value) throw new ProjectError('Connection not found.', 404);
      if (value.revision !== expected) throw new ProjectError('This connection changed. Reload before removing.', 409);
      if (data.deletedIds.length >= 10000) throw new ProjectError('Connection history requires host maintenance.', 503);
      data.connections = data.connections.filter((v) => v.id !== id); data.deletedIds.push(id);
    });
  }
}
