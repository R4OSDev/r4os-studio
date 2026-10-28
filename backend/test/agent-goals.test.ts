import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createApp } from '../src/app.js';

await test('Goal routes bind project/skill owners and protect native commands', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-goal-api-'));
  const socket = join(root, 'host.sock'), previous = process.env.STUDIO_AGENTS_SOCKET;
  process.env.STUDIO_AGENTS_SOCKET = socket;
  const calls: Record<string, unknown>[] = [];
  const ownerId = randomUUID(), sessionId = randomUUID(), requestId = randomUUID();
  const server = createServer((client) => {
    let raw = ''; client.setEncoding('utf8');
    client.on('data', (part) => {
      raw += part; if (!raw.includes('\n')) return;
      const call = JSON.parse(raw); calls.push(call);
      const snapshot = { owner: { type: call.ownerType, id: call.ownerId }, sessionId, threadId: null, revision: 0, goal: null, lastIntent: null, phase: 'idle' };
      const result = call.operation === 'capabilities' ? { nativeGoals: 1 }
        : call.operation === 'goal' ? snapshot : { requestId, action: 'save', state: 'pending', snapshot };
      client.end(JSON.stringify({ result }) + '\n');
    });
  });
  await new Promise<void>((resolve) => server.listen(socket, resolve));
  const app = createApp({ projectDirectory: join(root, 'Projects'), providers: { directory: join(root, 'Providers') } });
  try {
    for (const scope of ['projects', 'skills']) {
      const url = `/api/${scope}/${ownerId}/sessions/${sessionId}/goal`;
      const auth = await app.inject(`/api/${scope}`);
      const headers = { cookie: String(auth.headers['set-cookie']).split(';')[0], 'x-csrf-token': auth.json().csrfToken };
      const payload = { requestId, revision: 0, action: 'save', objective: 'Own goal 😀' };
      assert.equal((await app.inject({ method: 'POST', url, payload })).statusCode, 403);
      assert.equal((await app.inject({ method: 'POST', url, payload, headers: { ...headers, origin: 'http://foreign.test' } })).statusCode, 403);
      const response = await app.inject({ method: 'POST', url, payload, headers });
      assert.equal(response.statusCode, 202, response.body);
      const command = calls.at(-1)!;
      assert.deepEqual(command, { operation: 'goal_command', ownerType: scope === 'projects' ? 'project' : 'skill', ownerId, sessionId, input: payload });
      assert.equal((await app.inject({ url, headers })).statusCode, 200);
      assert.equal((await app.inject({ url: url + '/requests/' + requestId, headers })).statusCode, 200);
      const before = calls.length;
      assert.equal((await app.inject({ method: 'POST', url, payload: { ...payload, action: 'invented' }, headers })).statusCode, 400);
      assert.equal(calls.length, before);
    }
  } finally {
    await app.close(); await new Promise<void>((resolve) => server.close(() => resolve()));
    if (previous === undefined) delete process.env.STUDIO_AGENTS_SOCKET; else process.env.STUDIO_AGENTS_SOCKET = previous;
    await rm(root, { recursive: true, force: true });
  }
});
