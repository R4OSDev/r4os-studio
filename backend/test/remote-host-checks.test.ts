import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { createApp } from '../src/app.js';

await test('connection HTTP routes use actual private broker and original receipts without exposing credentials', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-remote-check-api-'));
  const script = fileURLToPath(new URL('../../scripts/remote-hosts/test_server.py', import.meta.url));
  const broker = spawn('/usr/bin/python3', ['-B', script, root], { stdio: ['ignore', 'pipe', 'pipe'] });
  const previous = process.env.STUDIO_REMOTE_HOSTS_SOCKET; process.env.STUDIO_REMOTE_HOSTS_SOCKET = join(root, 'Runtime/host.sock');
  const app = createApp({ providers: { directory: join(root, 'LLMProvider') }, projectDirectory: join(root, 'Projects') });
  const url = '/api/remote-hosts';
  try {
    await new Promise<void>((resolve, reject) => { broker.stdout.once('data', () => resolve()); broker.once('error', reject); broker.once('exit', () => reject(new Error('Own fixture broker exited before ready.'))); });
    const first = await app.inject(url); assert.equal(first.statusCode, 200, first.body);
    const headers = { cookie: String(first.headers['set-cookie']).split(';')[0], 'x-csrf-token': first.json().csrfToken };
    assert.equal((await app.inject(url + '/capabilities')).statusCode, 403);
    assert.equal((await app.inject({ url: url + '/capabilities', headers })).json().test, true);
    const secret = 'own-test-login-secret';
    const created = await app.inject({ method: 'POST', url, headers, payload: { requestId: randomUUID(), name: 'Own native check fixture', address: '127.0.0.1', password: secret } });
    assert.equal(created.statusCode, 200, created.body); const host = created.json();
    const input = { requestId: randomUUID(), revision: host.revision }; const check = `${url}/${host.id}/test`;
    for (const invalid of [{}, { cookie: headers.cookie }, { ...headers, origin: 'https://foreign.example' }]) {
      assert.equal((await app.inject({ method: 'POST', url: check, payload: input, headers: invalid })).statusCode, 403);
    }
    const rejected = await app.inject({ method: 'POST', url: check, headers, payload: { ...input, command: 'arbitrary' } }); assert.equal(rejected.statusCode, 400, rejected.body);
    const accepted = await app.inject({ method: 'POST', url: check, headers, payload: input }); assert.equal(accepted.statusCode, 200, accepted.body);
    const status = `${url}/${host.id}/tests/${input.requestId}`; let result = accepted.json();
    for (let attempt = 0; attempt < 40 && result.phase !== 'complete'; attempt++) { await new Promise((resolve) => setTimeout(resolve, 25)); result = (await app.inject({ url: status, headers })).json(); }
    assert.equal(result.phase, 'complete'); assert.equal(result.host.lastTest.version, '0.0.1'); assert.equal(result.host.lastTest.kernel, '0.0.2');
    assert.equal(result.host.hostKey.state, 'trusted'); assert(!JSON.stringify(result).includes(secret)); assert(!Object.hasOwn(result, 'binding'));
    const repeated = await app.inject({ method: 'POST', url: check, headers, payload: input }); assert.deepEqual(repeated.json(), result);
    assert.equal(JSON.parse(await readFile(join(root, 'Runtime/calls.json'), 'utf8')), 1);
    assert.equal((await app.inject({ url: `${url}/${randomUUID()}/tests/${input.requestId}`, headers })).statusCode, 404);
    await writeFile(join(root, 'Runtime/outcome'), 'changed');
    const second = { requestId: randomUUID(), revision: result.host.revision };
    await app.inject({ method: 'POST', url: check, headers, payload: second });
    for (let attempt = 0; attempt < 40; attempt++) { result = (await app.inject({ url: `${url}/${host.id}/tests/${second.requestId}`, headers })).json(); if (result.phase === 'complete') break; await new Promise((resolve) => setTimeout(resolve, 25)); }
    assert.equal(result.host.lastTest.status, 'hostkey_changed');
    const reset = { requestId: randomUUID(), revision: result.host.revision, confirm: true };
    const rebound = await app.inject({ method: 'POST', url: `${url}/${host.id}/trust`, headers, payload: reset }); assert.equal(rebound.statusCode, 200, rebound.body);
    assert.equal(rebound.json().hostKey.state, 'unbound'); assert.equal(rebound.json().lastTest, null);
    assert.deepEqual((await app.inject({ method: 'POST', url: `${url}/${host.id}/trust`, headers, payload: reset })).json(), rebound.json());
    assert.equal(JSON.parse(await readFile(join(root, 'Runtime/calls.json'), 'utf8')), 2);
  } finally {
    await app.close(); const exited = new Promise<void>((resolve) => broker.once('exit', () => resolve())); broker.kill('SIGTERM'); if (broker.exitCode === null) await exited;
    if (previous === undefined) delete process.env.STUDIO_REMOTE_HOSTS_SOCKET; else process.env.STUDIO_REMOTE_HOSTS_SOCKET = previous;
    await rm(root, { recursive: true, force: true });
  }
});
