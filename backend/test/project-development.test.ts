import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createApp } from '../src/app.js';

await test('development API binds project scope and protects build and stop', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-development-api-'));
  const socket = join(root, 'host.sock'), previous = process.env.STUDIO_DEVELOPMENT_SOCKET;
  process.env.STUDIO_DEVELOPMENT_SOCKET = socket;
  const calls: Record<string, unknown>[] = [], id = randomUUID(), jobId = randomUUID();
  const server = createServer((client) => {
    let pending = '';
    client.setEncoding('utf8'); client.on('data', (part) => {
      pending += part;
      if (!pending.includes('\n')) return;
      calls.push(JSON.parse(pending)); client.end(JSON.stringify({ result: { id: jobId, state: 'queued' } }) + '\n');
    });
  });
  await new Promise<void>((resolve) => server.listen(socket, resolve));
  const app = createApp({ projectDirectory: join(root, 'Projects'), providers: { directory: join(root, 'Providers') } });
  try {
    const auth = await app.inject('/api/projects');
    const headers = { cookie: String(auth.headers['set-cookie']).split(';')[0], 'x-csrf-token': auth.json().csrfToken };
    const url = `/api/projects/${id}/development`, payload = { requestId: randomUUID(), projectRevision: 1, settingsRevision: 1 };
    assert.equal((await app.inject({ method: 'POST', url: url + '/builds', payload })).statusCode, 403);
    assert.equal(calls.length, 0);
    assert.equal((await app.inject({ method: 'POST', url: url + '/builds', headers, payload: { ...payload, vmId: randomUUID() } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: url + '/builds', headers, payload })).statusCode, 202);
    assert.deepEqual(calls.at(-1), { operation: 'build', projectId: id, input: payload });
    assert.equal((await app.inject({ method: 'GET', url: url + `/jobs/${jobId}?offset=12`, headers })).statusCode, 200);
    assert.deepEqual(calls.at(-1), { operation: 'read_job', projectId: id, id: jobId, offset: 12 });
    assert.equal((await app.inject({ method: 'POST', url: url + `/jobs/${jobId}/stop`, headers: { ...headers, origin: 'http://foreign.test' } })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: url + `/jobs/${jobId}/stop`, headers })).statusCode, 200);
  } finally {
    await app.close(); await new Promise<void>((resolve) => server.close(() => resolve()));
    if (previous === undefined) delete process.env.STUDIO_DEVELOPMENT_SOCKET; else process.env.STUDIO_DEVELOPMENT_SOCKET = previous;
    await rm(root, { recursive: true, force: true });
  }
});
