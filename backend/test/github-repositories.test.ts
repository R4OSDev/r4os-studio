import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createApp } from '../src/app.js';
import { GitHubApi, GitHubRepositories } from '../src/modules/github-connections/repositories.js';
import { GitHubStore } from '../src/modules/github-connections/store.js';
import { projectBinding } from '../src/modules/github-connections/references.js';

const repo = { id: 11, owner: { login: 'octocat' }, name: 'app', full_name: 'octocat/app', private: true, archived: false,
  default_branch: 'main', permissions: { pull: true, push: false }, secret: 'must-not-project' };
await test('repository APIs verify account, protect CSRF, paginate and only project allowed metadata', async () => {
  const root = await mkdtemp(join(tmpdir(), 'github-repos-')), calls: string[] = [];
  const transport: typeof fetch = async (url, init) => {
    assert.equal(init?.redirect, 'manual'); assert.equal(init?.method, 'GET');
    const value = String(url); calls.push(value); assert(value.startsWith('https://api.github.com/'));
    return new Response(JSON.stringify(value.endsWith('/user') ? { login: 'octocat', id: 7, email: 'private.invalid' }
      : value.includes('/branches?') ? [{ name: 'feature/a', commit: { sha: 'a'.repeat(40) }, protected: false }]
      : value.includes('/user/repos?') ? [repo] : repo));
  };
  const app = createApp({ providers: { directory: join(root, 'LLMProvider') }, projectDirectory: join(root, 'Projects'), githubTransport: transport });
  const id = randomUUID(), token = 'dummy-private-token-1234567890';
  try {
    const first = await app.inject('/api/github'), headers = { cookie: String(first.headers['set-cookie']).split(';')[0], 'x-csrf-token': first.json().csrfToken };
    await app.inject({ method: 'POST', url: '/api/github', headers, payload: { id, name: 'Friendly', token } });
    const url = '/api/github/' + id;
    assert.equal((await app.inject({ method: 'POST', url: url + '/account', payload: { tokenRevision: 1 } })).statusCode, 403);
    const account = await app.inject({ method: 'POST', url: url + '/account', headers, payload: { tokenRevision: 1 } });
    assert.equal(account.statusCode, 200); assert.equal(account.json().connectionName, 'Friendly'); assert.equal(account.json().create, 'unverified');
    const list = await app.inject({ method: 'POST', url: url + '/repositories', headers, payload: { tokenRevision: 1, page: 2, query: 'app' } });
    assert.equal(list.statusCode, 200); assert.equal(list.json().repositories[0].push, false); assert.equal(list.json().page, 2);
    assert(calls.some((v) => v.includes('page=2'))); assert(!list.body.includes(token)); assert(!list.body.includes('secret')); assert(!list.body.includes('private.invalid'));
    const branches = await app.inject({ method: 'POST', url: url + '/branches', headers, payload: { tokenRevision: 1, owner: 'octocat', name: 'app', repositoryId: 11 } });
    assert.equal(branches.statusCode, 200); assert.equal(branches.json().branches[0].name, 'feature/a');
    assert.equal((await app.inject({ method: 'POST', url: url + '/branches', headers, payload: { tokenRevision: 1, owner: 'octocat', name: 'app', repositoryId: 12 } })).statusCode, 409);
    assert.equal((await app.inject({ method: 'POST', url: url + '/repositories', headers, payload: { tokenRevision: 1, page: -1 } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: url + '/account', headers, payload: { tokenRevision: 1, token } })).statusCode, 400);
  } finally { await app.close(); await rm(root, { recursive: true, force: true }); }
});

await test('in-flight token replacement cannot publish stale repository account data; rename keeps identity', async () => {
  const root = await mkdtemp(join(tmpdir(), 'github-account-race-')), store = new GitHubStore(root), id = randomUUID();
  try {
    await store.create({ id, name: 'Before', token: 'first-dummy-token-1234567890' });
    const client = new GitHubRepositories(store, async () => { await store.update(id, { revision: 1, name: 'After', token: 'second-dummy-token-1234567890' }); return new Response('{"login":"octocat","id":7}'); });
    await assert.rejects(client.account(id, 1), /token changed/);
    await store.update(id, { revision: 2, name: 'Renamed' });
    const renamed = new GitHubRepositories(store, async () => new Response('{"login":"octocat","id":7}'));
    assert.equal((await renamed.account(id, 2)).account.connectionName, 'Renamed');
    await store.remove(id, 3); await assert.rejects(renamed.account(id, 2), /removed/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

await test('GitHub adapter rejects redirects, unsafe metadata and oversized responses without upstream secret errors', async () => {
  for (const status of [301, 401, 403, 404, 422, 429, 500]) {
    const api = new GitHubApi('dummy', async () => new Response('PRIVATE UPSTREAM SECRET', { status }));
    await assert.rejects(api.request('/user'), (e: Error) => !e.message.includes('PRIVATE'));
  }
  await assert.rejects(new GitHubApi('dummy', async () => new Response('x'.repeat(2 * 1024 * 1024 + 1))).request('/user'), /limit/);
  const root = await mkdtemp(join(tmpdir(), 'github-binding-')), id = randomUUID();
  try {
    const privateRoot = join(root, id, '.studio/git'); await mkdir(privateRoot, { recursive: true });
    const binding = { schema: 1, revision: 1, connectionId: randomUUID(), userId: 7, repository: { id: 11 }, branch: 'main' };
    await writeFile(join(privateRoot, 'binding.json'), JSON.stringify(binding));
    assert.equal((await projectBinding(root, id))?.repository.id, 11);
    await rm(join(privateRoot, 'binding.json')); await symlink('/etc/passwd', join(privateRoot, 'binding.json'));
    await assert.rejects(projectBinding(root, id));
  } finally { await rm(root, { recursive: true, force: true }); }
});
