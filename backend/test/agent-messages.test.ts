import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createApp } from '../src/app.js';

await test('message API binds owner and session and protects mutation/readback', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-messages-'));
  const previous = process.env.STUDIO_AGENTS_SOCKET, socket = join(root, 'host.sock');
  process.env.STUDIO_AGENTS_SOCKET = socket;
  const calls: Record<string, unknown>[] = [];
  const server = createServer(client => {
    let pending = ''; client.setEncoding('utf8');
    client.on('data', part => {
      pending += part;
      if (!pending.includes('\n')) return;
      const call = JSON.parse(pending); calls.push(call);
      client.end(JSON.stringify({ result: { requestId: call.input?.requestId ?? call.requestId, state: 'queued' } }) + '\n');
    });
  });
  await new Promise<void>(resolve => server.listen(socket, resolve));
  const app = createApp({ projectDirectory: join(root, 'Projects'), providers: { directory: join(root, 'Providers') } });
  try {
    const auth = await app.inject('/api/projects');
    const headers = { cookie: String(auth.headers['set-cookie']).split(';')[0], 'x-csrf-token': auth.json().csrfToken };
    const projectId = randomUUID(), sessionId = randomUUID(), requestId = randomUUID();
    const url = `/api/projects/${projectId}/sessions/${sessionId}/messages`;
    const payload = { requestId, revision: 1, mode: 'queue', text: 'One message' };
    assert.equal((await app.inject({ method: 'POST', url, payload })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url, payload, headers: { cookie: headers.cookie } })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url, payload, headers: { ...headers, origin: 'http://foreign.test' } })).statusCode, 403);
    assert.equal((await app.inject({ url, headers: { ...headers, origin: 'http://foreign.test' } })).statusCode, 403);
    assert.equal(calls.length, 0);
    const accepted = await app.inject({ method: 'POST', url, payload, headers });
    assert.equal(accepted.statusCode, 202, accepted.body);
    assert.equal(accepted.json().message.requestId, requestId);
    assert.deepEqual(calls.at(-1), { operation: 'submit_message', projectId, sessionId, input: payload });
    const receipt = await app.inject({ url: url + '/' + requestId, headers });
    assert.equal(receipt.statusCode, 200); assert.equal(receipt.headers['cache-control'], 'private, no-store');
    assert.deepEqual(calls.at(-1), { operation: 'message_receipt', projectId, sessionId, requestId });
    for (const change of [{ mode: 'other' }, { attachments: ['../secret'] }, { text: 'x'.repeat(74000) }])
      assert([400, 413].includes((await app.inject({ method: 'POST', url, headers, payload: { ...payload, ...change } })).statusCode));
    const control = { requestId: randomUUID(), revision: 1, action: 'resume' };
    assert.equal((await app.inject({ method: 'POST', url: url + '/control', payload: control, headers: { cookie: headers.cookie } })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: url + '/control', payload: control, headers })).statusCode, 200);
    assert.deepEqual(calls.at(-1), { operation: 'message_control', projectId, sessionId, input: control });
    const skillUrl = `/api/skills/${projectId}/sessions/${sessionId}/messages`;
    const skillAuth = await app.inject('/api/skills');
    const skillHeaders = { cookie: String(skillAuth.headers['set-cookie']).split(';')[0], 'x-csrf-token': skillAuth.json().csrfToken };
    const skill = await app.inject({ method: 'POST', url: skillUrl, headers: skillHeaders, payload });
    assert.equal(skill.statusCode, 202, skill.body);
    assert.deepEqual(calls.at(-1), { operation: 'submit_message', ownerType: 'skill', ownerId: projectId, sessionId, input: payload });
  } finally {
    await app.close(); await new Promise<void>(resolve => server.close(() => resolve()));
    if (previous === undefined) delete process.env.STUDIO_AGENTS_SOCKET; else process.env.STUDIO_AGENTS_SOCKET = previous;
    await rm(root, { recursive: true, force: true });
  }
});
