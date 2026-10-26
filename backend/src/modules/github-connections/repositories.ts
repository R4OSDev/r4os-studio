import type { GitHubAccount, GitHubRepository, GitHubBranch } from '../../../../shared/project-github.js';
import { ProjectError } from '../projects/store.js';
import { GitHubStore } from './store.js';

export const ownerName = (v: unknown): v is string => typeof v === 'string' && /^[a-z\d](?:[a-z\d-]{0,37}[a-z\d])?$/i.test(v);
export const repoName = (v: unknown): v is string => typeof v === 'string' && /^[a-z\d_.-]{1,100}$/i.test(v) && !['.', '..'].includes(v);
const numberId = (v: unknown): v is number => Number.isSafeInteger(v) && (v as number) > 0;
const text = (v: unknown, limit: number): v is string => typeof v === 'string' && !!v && v.length <= limit && !/[\p{Cc}\p{Cs}]/u.test(v);
export function repository(value: unknown): GitHubRepository {
  const v = value as { id: number; owner: { login: string }; name: string; full_name: string; private: boolean; default_branch?: string; archived: boolean; permissions?: { pull?: boolean; push?: boolean } };
  if (!v || !numberId(v.id) || !ownerName(v.owner?.login) || !repoName(v.name) || v.full_name !== v.owner.login + '/' + v.name
    || typeof v.private !== 'boolean' || typeof v.archived !== 'boolean' || (v.default_branch != null && !text(v.default_branch, 255))) {
    throw new ProjectError('GitHub returned invalid repository metadata.', 502);
  }
  return { id: v.id, owner: v.owner.login, name: v.name, fullName: v.full_name,
    url: `https://github.com/${v.owner.login}/${v.name}`, private: v.private,
    defaultBranch: v.default_branch ?? null, archived: v.archived, read: v.permissions?.pull === true || !v.private, push: v.permissions?.push === true && !v.archived };
}

/** No caller-controlled host, redirects, error bodies or unbounded JSON. */
export class GitHubApi {
  constructor(private token: string, private transport: typeof fetch = fetch) {}
  async request(path: string, method = 'GET', body?: unknown): Promise<unknown> {
    if (!path.startsWith('/') || path.startsWith('//') || /[\r\n#]/.test(path)) throw new ProjectError('Invalid GitHub operation.', 400);
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 10_000);
    try {
      const response = await this.transport('https://api.github.com' + path, { method, redirect: 'manual', signal: controller.signal,
        credentials: 'omit', cache: 'no-store', headers: { Authorization: `Bearer ${this.token}`, Accept: 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': 'R4OS-Studio', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
      try {
        if (response.status === 401) throw new ProjectError('GitHub authentication expired. Update this connection.', 401);
        if (response.status === 429 || (response.status === 403 && (response.headers.get('x-ratelimit-remaining') === '0' || response.headers.has('retry-after')))) throw new ProjectError('GitHub rate limit reached. Retry later.', 429);
        if (response.status === 403) throw new ProjectError('GitHub denied this operation. Check token permissions, SSO and repository rules.', 403);
        if (response.status === 404) throw new ProjectError('Repository or branch not found, or this token cannot access it.', 404);
        if (response.status === 422) throw new ProjectError('GitHub rejected these repository parameters. Check the name and permissions.', 422);
        if (!response.ok || response.status >= 300) throw new ProjectError('GitHub could not complete this operation. No redirect was followed.', 502);
        if (!response.body || Number(response.headers.get('content-length')) > 2 * 1024 * 1024) throw new ProjectError('GitHub response exceeded its limit.', 502);
        const reader = response.body.getReader(); let bytes = 0; const chunks: Uint8Array[] = [];
        try { for (;;) { const part = await reader.read(); if (part.done) break; bytes += part.value.length;
          if (bytes > 2 * 1024 * 1024) throw new ProjectError('GitHub response exceeded its limit.', 502); chunks.push(part.value); }
        } finally { await reader.cancel().catch(() => {}); }
        try { return JSON.parse(Buffer.concat(chunks).toString('utf8')); }
        catch { throw new ProjectError('GitHub returned invalid JSON.', 502); }
      } finally { await response.body?.cancel().catch(() => {}); }
    } catch (error) {
      if (error instanceof ProjectError) throw error;
      throw new ProjectError(controller.signal.aborted ? 'GitHub request timed out. Its result may need reconciliation.' : 'GitHub network or TLS request failed.', 503);
    } finally { clearTimeout(timer); controller.abort(); }
  }
}

export class GitHubRepositories {
  constructor(readonly store: GitHubStore, private transport: typeof fetch = fetch) {}
  async account(id: string, tokenRevision: number) {
    const snapshot = await this.store.credential(id, tokenRevision), api = new GitHubApi(snapshot.token, this.transport);
    const identity = await api.request('/user') as { login?: unknown; id?: unknown };
    if (!identity || !ownerName(identity.login) || !numberId(identity.id)) throw new ProjectError('GitHub returned invalid account metadata.', 502);
    await this.store.assertCredential(id, tokenRevision);
    const account: GitHubAccount = { connectionId: id, connectionName: snapshot.connection.name, tokenRevision,
      login: identity.login, userId: identity.id, checkedAt: new Date().toISOString(), create: 'unverified' };
    return { api, account };
  }
  async repositories(id: string, tokenRevision: number, page: number, query = '') {
    const { api, account } = await this.account(id, tokenRevision);
    const raw = await api.request(`/user/repos?per_page=50&page=${page}&sort=full_name&affiliation=owner,collaborator,organization_member`);
    if (!Array.isArray(raw) || raw.length > 50) throw new ProjectError('GitHub returned an invalid repository list.', 502);
    const repositories = raw.map(repository).filter((v) => v.fullName.toLowerCase().includes(query.toLowerCase()));
    await this.store.assertCredential(id, tokenRevision);
    return { account, repositories, page, hasMore: raw.length === 50 };
  }
  async get(id: string, tokenRevision: number, owner: string, name: string, expectedId?: number) {
    if (!ownerName(owner) || !repoName(name)) throw new ProjectError('Invalid GitHub repository.', 400);
    const result = await this.account(id, tokenRevision);
    const repo = repository(await result.api.request(`/repos/${owner}/${name}`));
    if (expectedId !== undefined && repo.id !== expectedId) throw new ProjectError('This repository identity changed. Reconnect explicitly.', 409);
    await this.store.assertCredential(id, tokenRevision);
    return { ...result, repository: repo };
  }
  async branches(id: string, tokenRevision: number, owner: string, name: string, repositoryId: number, page: number) {
    const { api, account, repository: repo } = await this.get(id, tokenRevision, owner, name, repositoryId);
    const raw = await api.request(`/repos/${repo.owner}/${repo.name}/branches?per_page=50&page=${page}`);
    if (!Array.isArray(raw) || raw.length > 50) throw new ProjectError('GitHub returned an invalid branch list.', 502);
    const branches: GitHubBranch[] = raw.map((v: { name?: unknown; commit?: { sha?: unknown }; protected?: unknown }) => {
      if (!text(v?.name, 255) || typeof v.commit?.sha !== 'string' || !/^[a-f0-9]{40,64}$/.test(v.commit.sha) || typeof v.protected !== 'boolean') throw new ProjectError('GitHub returned invalid branch metadata.', 502);
      return { name: v.name, sha: v.commit.sha, protected: v.protected };
    });
    await this.store.assertCredential(id, tokenRevision);
    return { account, repository: repo, branches, page, hasMore: raw.length === 50 };
  }
}
