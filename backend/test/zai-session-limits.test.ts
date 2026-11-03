import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createServer } from 'node:net';
import { createApp } from '../src/app.js';

await test('subscription reads and refreshes keep project/skill session ownership and normal HTTP security', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-zai-session-'));
  const previous = process.env.STUDIO_AGENTS_SOCKET, socket = join(root, 'host.sock');
  process.env.STUDIO_AGENTS_SOCKET = socket;
  const calls: Record<string, unknown>[] = [], id = randomUUID(), sid = randomUUID(), rid = randomUUID();
  const server = createServer(client => {
    let raw = ''; client.on('data', chunk => {
      raw += chunk; if (!raw.includes('\n')) return;
      calls.push(JSON.parse(raw)); client.end(JSON.stringify({ result: { state: 'unknown' } }) + '\n');
    });
  });
  await new Promise<void>(resolve => server.listen(socket, resolve));
  const app = createApp({ projectDirectory: join(root, 'Projects'), providers: { directory: join(root, 'Providers') } });
  try {
    for (const scope of ['projects', 'skills']) {
      const auth = await app.inject('/api/' + scope);
      const headers = { cookie: String(auth.headers['set-cookie']).split(';')[0], 'x-csrf-token': auth.json().csrfToken };
      const base = `/api/${scope}/${id}/sessions/${sid}`;
      const count = calls.length;
      assert.equal((await app.inject(base + '/zai-limits')).statusCode, 403);
      assert.equal(calls.length, count);
      assert.equal((await app.inject({ url: base + '/zai-limits', headers })).statusCode, 200);
      const owner = scope === 'projects' ? { projectId: id } : { ownerType: 'skill', ownerId: id };
      assert.deepEqual(calls.at(-1), { operation: 'session_zai_limits', ...owner, sessionId: sid });
      const payload = { requestId: rid, providerRevision: 1 };
      assert.equal((await app.inject({ method: 'POST', url: base + '/zai-limits/check', headers: { cookie: headers.cookie }, payload })).statusCode, 403);
      assert.equal((await app.inject({ method: 'POST', url: base + '/zai-limits/check', headers, payload: { ...payload, providerId: randomUUID() } })).statusCode, 400);
      assert.equal((await app.inject({ method: 'POST', url: base + '/zai-limits/check', headers, payload })).statusCode, 200);
      assert.deepEqual(calls.at(-1), { operation: 'session_zai_limit_refresh', ...owner, sessionId: sid, input: payload });
      assert.equal((await app.inject({ url: base + '/zai-limit-requests/' + rid, headers })).statusCode, 200);
      assert.deepEqual(calls.at(-1), { operation: 'session_zai_limit_receipt', ...owner, sessionId: sid, requestId: rid });
      assert.equal((await app.inject({ url: base + '/zai-limits', headers: { ...headers, origin: 'http://foreign.invalid' } })).statusCode, 403);
    }
  } finally {
    await app.close(); await new Promise<void>(resolve => server.close(() => resolve()));
    if (previous === undefined) delete process.env.STUDIO_AGENTS_SOCKET; else process.env.STUDIO_AGENTS_SOCKET = previous;
    await rm(root, { recursive: true, force: true });
  }
});
