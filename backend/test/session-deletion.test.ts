import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createApp } from '../src/app.js';

await test('session deletion protects both owner scopes, original status and unavailable hosts', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-session-deletion-')), socket = join(root, 'host.sock');
  const previous = process.env.STUDIO_AGENTS_SOCKET; process.env.STUDIO_AGENTS_SOCKET = socket;
  const owner = randomUUID(), sid = randomUUID(), rid = randomUUID(), calls: Record<string, unknown>[] = [];
  let available = true;
  const server = createServer(client => {
    let raw = ''; client.on('data', chunk => {
      raw += chunk; if (!raw.includes('\n')) return;
      const value = JSON.parse(raw); calls.push(value);
      client.end(JSON.stringify({ result: value.operation === 'capabilities' ? { sessionDeletion: available ? 1 : 0 }
        : { requestId: rid, sessionId: sid, state: value.operation === 'session_delete_receipt' ? 'deleted' : 'deleting', phase: 'reserved' } }) + '\n');
    });
  });
  await new Promise<void>(resolve => server.listen(socket, resolve));
  const app = createApp({ projectDirectory: join(root, 'Projects'), providers: { directory: join(root, 'LLMProvider') } });
  try {
    for (const [prefix, kind] of [['projects', 'project'], ['skills', 'skill']]) {
      const base = `/api/${prefix}/${owner}/sessions/${sid}/deletion`;
      const payload = { requestId: rid, revision: 1, scopeHash: 'a'.repeat(64), confirmName: 'Own fixture session' };
      assert.equal((await app.inject(base)).statusCode, 403);
      const auth = await app.inject('/api/' + prefix + (prefix === 'projects' ? '/' : ''));
      assert.equal(auth.statusCode, 200, auth.body);
      const headers = { cookie: String(auth.headers['set-cookie']).split(';')[0], 'x-csrf-token': auth.json().csrfToken };
      assert.equal((await app.inject({ method: 'POST', url: base, headers: { ...headers, origin: 'http://foreign.invalid' }, payload })).statusCode, 403);
      assert.equal((await app.inject({ method: 'POST', url: base, headers: { cookie: headers.cookie }, payload })).statusCode, 403);
      assert.equal((await app.inject({ method: 'POST', url: base, headers, payload })).statusCode, 202);
      assert.deepEqual(calls.at(-1), { operation: 'session_delete', ownerType: kind, ownerId: owner, sessionId: sid, input: payload });
      assert.equal((await app.inject({ url: base + '/' + rid, headers })).json().state, 'deleted');
      assert.equal((await app.inject({ method: 'POST', url: base, headers, payload: { ...payload, revision: 0 } })).statusCode, 400);
      available = false; assert.equal((await app.inject({ url: base, headers })).statusCode, 503); available = true;
    }
  } finally {
    await app.close(); await new Promise<void>(resolve => server.close(() => resolve()));
    if (previous === undefined) delete process.env.STUDIO_AGENTS_SOCKET; else process.env.STUDIO_AGENTS_SOCKET = previous;
    await rm(root, { recursive: true, force: true });
  }
});
