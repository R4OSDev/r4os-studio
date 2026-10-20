import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { once } from 'node:events';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createApp } from '../src/app.js';

await test('component downloads/defaults require session and CSRF and accept only fixed component identities', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'studio-components-'));
  process.env.STUDIO_COMPONENT_SOCKET = join(directory, 'host.sock');
  const received: Record<string, unknown>[] = [];
  const server = createServer((socket) => {
    let pending = '';
    socket.on('data', (chunk) => {
      pending += chunk.toString();
      if (!pending.includes('\n')) return;
      received.push(JSON.parse(pending));
      socket.end(JSON.stringify({ status: { enabled: true, components: {}, job: null, message: 'Ready' } }) + '\n');
    });
  });
  server.listen(process.env.STUDIO_COMPONENT_SOCKET); await once(server, 'listening');
  const app = createApp();
  try {
    const result = await app.inject('/api/updates/components');
    const headers = { cookie: String(result.headers['set-cookie']).split(';')[0], 'x-csrf-token': result.json().csrfToken };
    assert.equal((await app.inject({ method: 'POST', url: '/api/updates/components/download', payload: { kind: 'zig', id: '0.16.0' } })).statusCode, 403);
    const before = received.length;
    for (const payload of [{ kind: 'shell', id: '0.16.0' }, { kind: 'zig', id: '../../outside' }, { kind: 'zig', id: '0.16.0', url: 'https://evil.test' }]) {
      assert.equal((await app.inject({ method: 'POST', url: '/api/updates/components/download', headers, payload })).statusCode, 400);
    }
    assert.equal(received.length, before);
    assert.equal((await app.inject({ method: 'POST', url: '/api/updates/components/default', headers: { ...headers, origin: 'https://evil.test' }, payload: { kind: 'zig', id: '0.16.0' } })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: '/api/updates/components/default', headers, payload: { kind: 'zig', id: '0.16.0' } })).statusCode, 200);
    assert.deepEqual(received.at(-1), { command: 'default', kind: 'zig', id: '0.16.0' });
  } finally {
    await app.close(); await new Promise<void>((resolve) => server.close(() => resolve()));
    delete process.env.STUDIO_COMPONENT_SOCKET; await rm(directory, { recursive: true, force: true });
  }
});
