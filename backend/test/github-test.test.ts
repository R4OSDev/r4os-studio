import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, mkdir, writeFile, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { testToken } from '../src/modules/github-connections/test.js';
import { createApp } from '../src/app.js';
import type { GitHubTestResult } from '../../shared/github-connections.js';

await test('GitHub identity adapter fixes destination, projects metadata and bounds failure/timeout responses', async () => {
  const token = 'ghp_adapter_fixture_token_1234567890';
  let calls = 0;
  const success: typeof fetch = async (url, init) => {
    calls++; assert.equal(url, 'https://api.github.com/user'); assert.equal(init?.method, 'GET'); assert.equal(init?.redirect, 'manual');
    assert.deepEqual(init?.headers, { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': 'R4OS-Studio' });
    return new Response(JSON.stringify({ login: 'octocat', id: 123, email: 'private@example.invalid', bio: token }), { status: 200 });
  };
  const good = await testToken(token, success);
  assert.equal(calls, 1); assert.equal(good.status, 'success'); assert.equal(good.login, 'octocat'); assert.equal(good.userId, 123);
  assert(!JSON.stringify(good).includes(token)); assert(!JSON.stringify(good).includes('private@example'));
  for (const [status, headers, expected] of [
    [401, {}, 'authentication_failed'], [403, {}, 'forbidden'], [403, { 'x-ratelimit-remaining': '0' }, 'rate_limited'],
    [403, { 'retry-after': '1' }, 'rate_limited'], [429, {}, 'rate_limited'], [503, {}, 'server_error'],
    [302, { location: 'https://evil.invalid/' }, 'invalid_response'],
  ] as const) {
    let requests = 0;
    const response = await testToken(token, async () => { requests++; return new Response('{}', { status, headers }); });
    assert.equal(response.status, expected); assert.equal(requests, 1);
  }
  for (const body of ['{invalid', 'null', '{"login":"<script>","id":1}', '{"login":"valid","id":0}', 'x'.repeat(70000)]) {
    assert.equal((await testToken(token, async () => new Response(body, { status: 200 }))).status, 'invalid_response');
  }
  assert.equal((await testToken(token, async () => { throw new Error('certificate error ' + token); })).status, 'network_error');
  const stalled: typeof fetch = async (_url, init) => new Promise((_resolve, reject) => {
    init!.signal!.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
  });
  assert.equal((await testToken(token, stalled, 10)).status, 'timeout');
});

await test('draft tests never save, stored results bind token generation, removed/replaced or superseded tests cannot publish', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-github-test-'));
  const pending: Array<(value: GitHubTestResult) => void> = [];
  let signalStart: (() => void) | undefined;
  const app = createApp({ providers: { directory: join(root, 'LLMProvider') }, projectDirectory: join(root, 'Projects'),
    githubTester: () => new Promise((resolve) => { pending.push(resolve); signalStart?.(); }) });
  const result: GitHubTestResult = { status: 'success', checkedAt: new Date().toISOString(), login: 'octocat', userId: 123 };
  try {
    const first = await app.inject('/api/github');
    const headers = { cookie: String(first.headers['set-cookie']).split(';')[0], 'x-csrf-token': first.json().csrfToken };
    const send = (url: string, payload: unknown, method: 'POST' | 'PATCH' | 'DELETE' = 'POST') => app.inject({ method, url: '/api/github' + url, payload, headers });
    assert.equal((await app.inject({ method: 'POST', url: '/api/github/test', payload: { token: 'ghp_fixture_value_1234567890' } })).statusCode, 403);
    assert.equal(pending.length, 0);
    async function start(url: string, payload: unknown) {
      const started = new Promise<void>((resolve) => { signalStart = resolve; });
      const response = send(url, payload); void response.then(() => {});
      await started; signalStart = undefined; return { response };
    }
    const draft = await start('/test', { token: 'ghp_draft_token_1234567890' });
    pending.shift()!(result); assert.equal((await draft.response).json().status, 'success');
    assert.equal((await app.inject('/api/github')).json().connections.length, 0);
    const id = randomUUID(); const token = 'ghp_stored_token_1234567890';
    assert.equal((await send('', { id, name: 'Test', token })).statusCode, 200);
    const old = await start('/' + id + '/test', { revision: 1 });
    assert.equal((await send('/' + id, { revision: 1, name: 'Test', token: 'ghp_replacement_token_1234567890' }, 'PATCH')).statusCode, 200);
    pending.shift()!(result); assert.equal((await old.response).statusCode, 409);
    assert.equal((await app.inject('/api/github')).json().connections[0].lastTest, undefined);
    assert.equal((await send('/' + id + '/test', { revision: 1 })).statusCode, 409);
    const earlier = await start('/' + id + '/test', { revision: 2 });
    const later = await start('/' + id + '/test', { revision: 2 });
    const earlierResolve = pending.shift()!, laterResolve = pending.shift()!;
    laterResolve(result); assert.equal((await later.response).json().lastTest.login, 'octocat');
    earlierResolve({ status: 'authentication_failed', checkedAt: new Date().toISOString() });
    assert.equal((await earlier.response).statusCode, 409);
    assert.equal((await app.inject('/api/github')).json().connections[0].lastTest.status, 'success');
    const renamed = await send('/' + id, { revision: 2, name: 'Renamed' }, 'PATCH');
    assert.equal(renamed.json().tokenRevision, 2); assert.equal(renamed.json().lastTest.status, 'success');
    const removed = await start('/' + id + '/test', { revision: 3 });
    assert.equal((await send('/' + id, { revision: 3 }, 'DELETE')).statusCode, 204);
    pending.shift()!(result); assert.equal((await removed.response).statusCode, 409);
    assert.equal((await app.inject('/api/github')).json().connections.length, 0);
  } finally { pending.forEach((resolve) => resolve(result)); await app.close(); await rm(root, { recursive: true, force: true }); }
});

await test('0.4.1 catalogs remain readable without rewriting credentials or inferring an old test', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-github-legacy-'));
  const directory = join(root, 'GitHub'); await mkdir(directory, { mode: 0o700 });
  const data = JSON.stringify({ schema: 1, deletedIds: [], connections: [{ id: randomUUID(), name: 'Legacy',
    token: 'ghp_old_private_fixture_1234567890', revision: 5, hasToken: true, createdAt: '2026-10-25T12:00:00Z', updatedAt: '2026-10-25T12:00:00Z' }] });
  const path = join(directory, 'connections.json'); await writeFile(path, data, { mode: 0o600 });
  const app = createApp({ providers: { directory: join(root, 'LLMProvider') }, projectDirectory: join(root, 'Projects') });
  try {
    const response = await app.inject('/api/github');
    assert.equal(response.statusCode, 200); assert.equal(response.json().connections[0].revision, 5);
    assert.equal(response.json().connections[0].tokenRevision, 1); assert.equal(response.json().connections[0].lastTest, undefined);
    assert.equal(await readFile(path, 'utf8'), data);
  } finally { await app.close(); await rm(root, { recursive: true, force: true }); }
});
