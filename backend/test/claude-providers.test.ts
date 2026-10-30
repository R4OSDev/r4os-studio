import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createApp } from '../src/app.js';

await test('Claude native auth requires same-origin browser/CSRF and binds every code and receipt to that owner', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-claude-http-')), socket = join(root, 'host.sock');
  const previous = process.env.STUDIO_AGENTS_SOCKET; process.env.STUDIO_AGENTS_SOCKET = socket;
  const id = randomUUID(), requestId = randomUUID(), calls: Record<string, unknown>[] = [];
  const server = createServer(client => {
    let raw = ''; client.on('data', chunk => {
      raw += chunk; if (!raw.includes('\n')) return;
      const value = JSON.parse(raw); calls.push(value);
      client.end(JSON.stringify({ result: value.action === 'list' ? [] : { requestId, state: 'pending', providerId: id } }) + '\n');
    });
  });
  await new Promise<void>(resolve => server.listen(socket, resolve));
  const app = createApp({ projectDirectory: join(root, 'Projects'), providers: { directory: join(root, 'Providers') } });
  const base = '/api/providers/claude-subscriptions';
  try {
    assert.equal((await app.inject(base)).statusCode, 403); assert.equal(calls.length, 0);
    const auth = await app.inject('/api/providers/');
    const headers = { cookie: String(auth.headers['set-cookie']).split(';')[0], 'x-csrf-token': auth.json().csrfToken };
    assert.equal((await app.inject({ url: base, headers })).statusCode, 200);
    for (const extra of [{ origin: 'http://foreign.invalid' }, { host: 'foreign.invalid' }, { 'sec-fetch-site': 'cross-site' }]) {
      assert.equal((await app.inject({ url: base, headers: { ...headers, ...extra } })).statusCode, 403);
    }
    const input = { requestId, revision: 1, action: 'connect' };
    assert.equal((await app.inject({ method: 'POST', url: base + '/' + id + '/auth', headers: { cookie: headers.cookie }, payload: input })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: base + '/' + id + '/auth', headers, payload: input })).statusCode, 200);
    const owner = calls.at(-1)?.owner; assert.match(String(owner), /^[a-f0-9]{64}$/);
    const original = base + '/' + id + '/auth-requests/' + requestId;
    assert.equal((await app.inject({ url: original, headers })).statusCode, 200);
    assert.equal(calls.at(-1)?.owner, owner); assert.equal(calls.at(-1)?.action, 'auth_receipt');
    const code = 'owned-code-only#original-native-sign-in-state';
    assert.equal((await app.inject({ method: 'POST', url: original + '/code', headers, payload: { code } })).statusCode, 200);
    assert.equal(calls.at(-1)?.owner, owner); assert.equal(calls.at(-1)?.code, code);
    assert.equal((await app.inject({ method: 'POST', url: original + '/cancel', headers, payload: {} })).statusCode, 200);
    const before = calls.length;
    for (const [url, payload] of [[base, { requestId, name: 'Own', token: 'forbidden' }],
      [base + '/' + id + '/auth', { ...input, revision: '1' }], [base + '/' + id + '/auth', { ...input, action: 'console' }],
      [original + '/code', { code, token: 'forbidden' }], [original + '/code', { code: 123 }], [original + '/cancel', { replay: true }]]) {
      assert.equal((await app.inject({ method: 'POST', url: url as string, headers, payload })).statusCode, 400);
    }
    assert.equal(calls.length, before);
    const other = await app.inject('/api/providers/');
    const otherHeaders = { cookie: String(other.headers['set-cookie']).split(';')[0] };
    await app.inject({ url: original, headers: otherHeaders }); assert.notEqual(calls.at(-1)?.owner, owner);
    assert.ok(calls.every(value => value.operation === 'claude_provider'));
  } finally {
    await app.close(); await new Promise<void>(resolve => server.close(() => resolve()));
    if (previous === undefined) delete process.env.STUDIO_AGENTS_SOCKET; else process.env.STUDIO_AGENTS_SOCKET = previous;
    await rm(root, { recursive: true, force: true });
  }
});
