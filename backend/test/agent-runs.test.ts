import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createApp } from '../src/app.js';

await test('run API protects mutations and resumes durable events', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-run-api-'));
  const socket = join(root, 'host.sock'), previous = process.env.STUDIO_AGENTS_SOCKET;
  process.env.STUDIO_AGENTS_SOCKET = socket;
  const calls: Record<string, unknown>[] = [];
  const id = randomUUID(), sessionId = randomUUID(), runId = randomUUID();
  const server = createServer((client) => {
    let input = '';
    client.setEncoding('utf8');
    client.on('data', (part) => {
      input += part;
      if (!input.includes('\n')) return;
      const call = JSON.parse(input); calls.push(call);
      client.end(JSON.stringify({ result: call.operation === 'events' ? {
        events: [{ seq: 7, runId, kind: 'notice', payload: { text: 'Grüße 🦀' } }], session: {},
      } : { id: runId, sessionId, state: 'queued' } }) + '\n');
    });
  });
  await new Promise<void>((resolve) => server.listen(socket, resolve));
  const app = createApp({ projectDirectory: join(root, 'Projects'), providers: { directory: join(root, 'Providers') } });
  const url = `/api/projects/${id}/sessions/${sessionId}`;
  try {
    const auth = await app.inject('/api/projects');
    const headers = { cookie: String(auth.headers['set-cookie']).split(';')[0], 'x-csrf-token': auth.json().csrfToken };
    const payload = { requestId: randomUUID(), revision: 1, text: 'Hello' };
    assert.equal((await app.inject({ method: 'POST', url: url + '/runs', payload })).statusCode, 403);
    const accepted = await app.inject({ method: 'POST', url: url + '/runs', payload, headers });
    assert.equal(accepted.statusCode, 202); assert.equal(accepted.json().run.id, runId);
    assert.deepEqual(calls[0], { operation: 'start_run', projectId: id, sessionId, input: payload });
    assert.equal((await app.inject({ method: 'POST', url: url + '/runs', payload: { ...payload, cwd: '/tmp' }, headers })).statusCode, 202);
    assert(!Object.hasOwn(calls.at(-1)!.input as object, 'cwd'));
    assert.equal((await app.inject({ method: 'POST', url: url + `/runs/${runId}/stop`, headers: { ...headers, origin: 'http://foreign.test' } })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: url + `/runs/${runId}/stop`, headers })).statusCode, 200);
    await app.listen({ host: '127.0.0.1', port: 0 });
    const address = app.server.address(); assert(address && typeof address !== 'string');
    const response = await fetch(`http://127.0.0.1:${address.port}${url}/events?after=4`, { headers: { cookie: headers.cookie, 'last-event-id': '6' } });
    assert.equal(response.status, 200); assert(response.headers.get('content-type')?.includes('text/event-stream'));
    const reader = response.body!.getReader();
    const frame = new TextDecoder().decode((await reader.read()).value);
    assert(frame.includes('id: 7')); assert(frame.includes('Grüße 🦀'));
    assert.equal(calls.at(-1)?.after, 6);
    await reader.cancel();
  } finally {
    await app.close(); await new Promise<void>((resolve) => server.close(() => resolve()));
    if (previous === undefined) delete process.env.STUDIO_AGENTS_SOCKET; else process.env.STUDIO_AGENTS_SOCKET = previous;
    await rm(root, { recursive: true, force: true });
  }
});
