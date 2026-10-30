import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createServer } from 'node:net';
import { createApp } from '../src/app.js';

await test('project Git routes keep session/CSRF/host gates and reject arbitrary commands before the private bridge', async () => {
  const root = await mkdtemp(join(tmpdir(), 'project-github-http-')), socket = join(root, 'git.sock'), calls: Record<string, unknown>[] = [];
  const previous = process.env.STUDIO_GIT_SOCKET; process.env.STUDIO_GIT_SOCKET = socket;
  const server = createServer((client) => { let raw = ''; client.on('data', (part) => { raw += part.toString();
    if (raw.includes('\n')) { const value = JSON.parse(raw); calls.push(value); client.end(JSON.stringify({ result: { available: true, id: value.requestId, state: 'queued' } }) + '\n'); }
  }); });
  await new Promise<void>((resolve) => server.listen(socket, resolve));
  const app = createApp({ providers: { directory: join(root, 'LLMProvider') }, projectDirectory: join(root, 'Projects') });
  try {
    const first = await app.inject('/api/projects');
    const headers = { cookie: String(first.headers['set-cookie']).split(';')[0], 'x-csrf-token': first.json().csrfToken };
    const id = randomUUID(), url = '/api/projects/' + id + '/github/jobs', requestId = randomUUID();
    assert.equal((await app.inject('/api/projects/github/capabilities')).statusCode, 403);
    assert.equal((await app.inject({ url: '/api/projects/github/capabilities', headers })).json().available, true);
    assert.equal((await app.inject({ method: 'POST', url, payload: { kind: 'initialize', requestId, input: {} } })).statusCode, 403);
    for (const payload of [{ kind: 'shell', requestId, input: {} }, { kind: 'initialize', requestId, input: { cmd: 'whoami' } }, { kind: 'check', requestId, input: {}, token: 'forbidden' }]) {
      assert.equal((await app.inject({ method: 'POST', url, headers, payload })).statusCode, 400);
    }
    const result = await app.inject({ method: 'POST', url, headers, payload: { kind: 'initialize', requestId, input: {} } });
    assert.equal(result.statusCode, 200); assert.equal(result.json().id, requestId);
    assert.deepEqual(calls.at(-1), { operation: 'submit', projectId: id, kind: 'initialize', requestId, input: {} });
    const check = await app.inject({ method: 'POST', url, headers, payload: { kind: 'check', requestId, input: { bindingRevision: 3 } } });
    assert.equal(check.statusCode, 200);
    assert.deepEqual(calls.at(-1), { operation: 'submit', projectId: id, kind: 'check', requestId, input: { bindingRevision: 3 } });
    assert.equal((await app.inject({ method: 'POST', url, headers: { ...headers, origin: 'http://foreign.test' }, payload: { kind: 'check', requestId, input: {} } })).statusCode, 403);
  } finally { await app.close(); await new Promise<void>((resolve) => server.close(() => resolve()));
    if (previous === undefined) delete process.env.STUDIO_GIT_SOCKET; else process.env.STUDIO_GIT_SOCKET = previous;
    await rm(root, { recursive: true, force: true }); }
});
