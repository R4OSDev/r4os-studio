import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createApp } from '../src/app.js';

await test('GitHub connections protect secrets, revisioned changes and restart persistence', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-github-'));
  const options = { providers: { directory: join(root, 'LLMProvider') }, projectDirectory: join(root, 'Projects') };
  let app = createApp(options);
  const url = '/api/github';
  const token = 'ghp_private_test_value_1234567890';
  try {
    const first = await app.inject(url);
    assert.equal(first.statusCode, 200); assert.deepEqual(first.json().connections, []);
    assert.equal(first.headers['cache-control'], 'no-store');
    assert(String(first.headers['set-cookie']).includes('Path=/api/github; HttpOnly; SameSite=Strict'));
    let headers = { cookie: String(first.headers['set-cookie']).split(';')[0], 'x-csrf-token': first.json().csrfToken };
    const payload = { id: randomUUID(), name: 'Main', token };
    assert.equal((await app.inject({ method: 'POST', url, payload })).statusCode, 403);
    for (const extra of [{ origin: 'http://foreign.test' }, { host: 'foreign.test' }, { origin: 'https://localhost:80' }, { 'sec-fetch-site': 'cross-site' }, { 'x-csrf-token': 'bad' }]) {
      assert.equal((await app.inject({ method: 'POST', url, payload, headers: { ...headers, ...extra } })).statusCode, 403);
    }
    for (const change of [{ name: '' }, { token: '' }, { token: 'short' }, { token: token + '\n' }, { name: '\u0000' }, { name: 'x'.repeat(121) }, { accountId: 'extra' }]) {
      const reply = await app.inject({ method: 'POST', url, payload: { ...payload, ...change }, headers });
      assert.equal(reply.statusCode, 400); assert(!reply.body.includes(token));
    }
    const added = await app.inject({ method: 'POST', url, payload, headers });
    assert.equal(added.statusCode, 200); assert.equal(added.json().hasToken, true); assert(!added.body.includes(token));
    assert.deepEqual(Object.keys(added.json()).sort(), ['createdAt', 'hasToken', 'id', 'name', 'revision', 'tokenRevision', 'updatedAt']);
    assert.equal((await app.inject({ method: 'POST', url, payload, headers })).json().id, payload.id);
    const other = await app.inject({ method: 'POST', url, payload: { ...payload, id: randomUUID() }, headers });
    assert.equal(other.statusCode, 200); assert.notEqual(other.json().id, payload.id);
    assert.equal((await app.inject(url)).json().connections.length, 2);
    const path = url + '/' + payload.id;
    const saved = await app.inject({ method: 'PATCH', url: path, payload: { revision: 1, name: 'Renamed' }, headers });
    assert.equal(saved.statusCode, 200); assert.equal(saved.json().revision, 2);
    assert.equal((await app.inject({ method: 'PATCH', url: path, payload: { revision: 1, name: 'Renamed' }, headers })).json().revision, 2);
    assert.equal((await app.inject({ method: 'PATCH', url: path, payload: { revision: 1, name: 'Stale' }, headers })).statusCode, 409);
    assert.equal((await app.inject({ method: 'PATCH', url: path, payload: { revision: 2, name: 'Renamed', token: '' }, headers })).statusCode, 400);
    const stored = join(root, 'GitHub/connections.json');
    assert((await readFile(stored, 'utf8')).includes(token));
    assert.equal((await stat(stored)).mode & 0o777, 0o600);
    assert.equal((await stat(join(root, 'GitHub'))).mode & 0o777, 0o700);
    await app.close(); app = createApp(options);
    const restored = await app.inject(url);
    assert.equal(restored.statusCode, 200); assert(!restored.body.includes(token));
    assert.equal(restored.json().connections[0].name, 'Renamed');
    headers = { cookie: String(restored.headers['set-cookie']).split(';')[0], 'x-csrf-token': restored.json().csrfToken };
    const nextToken = 'github_pat_new_test_value_1234567890';
    const replacement = await app.inject({ method: 'PATCH', url: path, payload: { revision: 2, name: 'Renamed', token: nextToken }, headers });
    assert.equal(replacement.statusCode, 200); assert.equal(replacement.json().revision, 3); assert(!replacement.body.includes(nextToken));
    assert.equal((await app.inject({ method: 'DELETE', url: path, payload: { revision: 2 }, headers })).statusCode, 409);
    assert.equal((await app.inject({ method: 'DELETE', url: path, payload: { revision: 3 }, headers })).statusCode, 204);
    assert.equal((await app.inject({ method: 'DELETE', url: path, payload: { revision: 3 }, headers })).statusCode, 204);
    assert.equal((await app.inject({ method: 'POST', url, payload, headers })).statusCode, 409);
    assert(!(await readFile(stored, 'utf8')).includes(nextToken));
    assert.equal((await app.inject(url)).json().connections.length, 1);
    const corrupt = '{"private":"' + token + '" invalid'; await writeFile(stored, corrupt, { mode: 0o600 });
    const broken = await app.inject(url); assert.equal(broken.statusCode, 503); assert(!broken.body.includes(token));
    assert.equal(await readFile(stored, 'utf8'), corrupt);
  } finally { await app.close(); await rm(root, { recursive: true, force: true }); }
});

await test('independent server instances read current revisions and refuse an active storage lock', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-github-race-'));
  const options = { providers: { directory: join(root, 'LLMProvider') }, projectDirectory: join(root, 'Projects') };
  const apps = [createApp(options), createApp(options)];
  try {
    const headers = await Promise.all(apps.map(async (app) => {
      const response = await app.inject('/api/github');
      return { cookie: String(response.headers['set-cookie']).split(';')[0], 'x-csrf-token': response.json().csrfToken };
    }));
    const payload = { id: randomUUID(), name: 'Shared', token: 'ghp_test_shared_token_123456789' };
    assert.equal((await apps[0].inject({ method: 'POST', url: '/api/github', payload, headers: headers[0] })).statusCode, 200);
    const change = { method: 'PATCH' as const, url: '/api/github/' + payload.id, payload: { revision: 1, name: 'First' } };
    assert.equal((await apps[1].inject({ ...change, headers: headers[1] })).statusCode, 200);
    assert.equal((await apps[0].inject({ ...change, payload: { revision: 1, name: 'Lost update' }, headers: headers[0] })).statusCode, 409);
    const lock = join(root, 'GitHub/.write.lock'); await writeFile(lock, 'held', { mode: 0o600 });
    assert.equal((await apps[0].inject({ ...change, headers: headers[0] })).statusCode, 409);
    assert.equal((await apps[0].inject('/api/github')).json().connections[0].name, 'First');
    await rm(lock);
  } finally { await Promise.all(apps.map((app) => app.close())); await rm(root, { recursive: true, force: true }); }
});
