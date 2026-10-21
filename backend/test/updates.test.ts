import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { createApp } from '../src/app.js';
import type { UpdateStatus } from '../../shared/updates.js';

await test('update administration binds browser session, validates release selection and exposes no arbitrary host commands', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'studio-updates-'));
  process.env.STUDIO_UPDATE_SOCKET = join(directory, 'host.sock');
  const received: unknown[] = [];
  const status: UpdateStatus = { enabled: true, installed: { version: '0.1.15', commit: null },
    latest: { version: '0.1.16', tag: 'v0.1.16', commit: 'a'.repeat(40) }, available: true,
    source: 'https://example.test/studio.git', phase: 'idle', message: 'An update is available.', error: null,
    lastChecked: null, nextCheck: null, checkIntervalSeconds: 21600, history: [] };
  const server = createServer((socket) => {
    let pending = '';
    socket.on('data', (chunk) => {
      pending += chunk.toString();
      if (!pending.includes('\n')) return;
      received.push(JSON.parse(pending)); socket.end(JSON.stringify({ status }) + '\n');
    });
  });
  server.listen(process.env.STUDIO_UPDATE_SOCKET); await once(server, 'listening');
  const app = createApp({ projectDirectory: join(directory, 'Projects') });
  try {
    const initial = await app.inject({ url: '/api/updates' });
    assert.equal(initial.statusCode, 200);
    assert.equal(initial.headers['cache-control'], 'no-store');
    const token = initial.json().csrfToken;
    const cookie = String(initial.headers['set-cookie']).split(';')[0];
    const headers = { cookie, 'x-csrf-token': token, origin: 'http://localhost:80' };
    assert.equal((await app.inject({ method: 'POST', url: '/api/updates/check', payload: {} })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: '/api/updates/check', headers: { cookie }, payload: {} })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: '/api/updates/check', headers: { ...headers, origin: 'http://evil.test' }, payload: {} })).statusCode, 403);
    assert.equal((await app.inject({ url: '/api/updates', headers: { host: 'evil.test' } })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: '/api/updates/check', headers: { cookie, 'x-csrf-token': token }, payload: {} })).statusCode, 202);
    const valid = { cookie, 'x-csrf-token': token };
    const before = received.length;
    assert.equal((await app.inject({ method: 'POST', url: '/api/updates/install', headers: valid, payload: { tag: '../../shell', commit: 'a'.repeat(40) } })).statusCode, 400);
    assert.equal(received.length, before);
    assert.equal((await app.inject({ method: 'POST', url: '/api/updates/install', headers: valid, payload: { tag: 'v0.1.16', commit: 'a'.repeat(40) } })).statusCode, 202);
    assert.deepEqual(received.at(-1), { command: 'install', release: { tag: 'v0.1.16', commit: 'a'.repeat(40) } });
    const other = await app.inject({ url: '/api/updates' });
    assert.equal((await app.inject({ method: 'POST', url: '/api/updates/check', headers: { cookie: String(other.headers['set-cookie']).split(';')[0], 'x-csrf-token': token }, payload: {} })).statusCode, 403);
    const health = (await app.inject('/api/health')).json();
    assert.match(health.version, /^\d+\.\d+\.\d+$/);
    assert.equal(health.service, 'r4os-studio');
  } finally {
    await app.close(); await new Promise<void>((resolve) => server.close(() => resolve()));
    delete process.env.STUDIO_UPDATE_SOCKET; await rm(directory, { recursive: true, force: true });
  }
});

await test('missing host update support is shown as unavailable and never starts an install', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'studio-update-missing-'));
  process.env.STUDIO_UPDATE_SOCKET = '/nonexistent/studio-update-test.sock';
  const app = createApp({ projectDirectory: join(directory, 'Projects') });
  try {
    const result = await app.inject('/api/updates');
    assert.equal(result.json().enabled, false);
    assert.equal(result.json().available, false);
    const install = await app.inject({ method: 'POST', url: '/api/updates/install', headers: {
      cookie: String(result.headers['set-cookie']).split(';')[0], 'x-csrf-token': result.json().csrfToken,
    }, payload: { tag: 'v0.1.16', commit: 'a'.repeat(40) } });
    assert.equal(install.statusCode, 503);
  } finally { await app.close(); delete process.env.STUDIO_UPDATE_SOCKET; await rm(directory, { recursive: true, force: true }); }
});
