import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { randomUUID } from 'node:crypto';

await test('VM guest access requires VM session/CSRF and keeps stored credentials out of responses', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-vm-access-'));
  const previous = { r4os: process.env.STUDIO_R4OS_DIR, socket: process.env.STUDIO_DEVELOPMENT_SOCKET };
  const r4os = join(root, 'R4OS'), socket = join(root, 'host.sock'), id = randomUUID(), revision = randomUUID();
  process.env.STUDIO_R4OS_DIR = r4os; process.env.STUDIO_DEVELOPMENT_SOCKET = socket;
  await mkdir(join(r4os, 'Instances', id), { recursive: true });
  await writeFile(join(r4os, 'Instances', id, 'vm.json'), JSON.stringify({ schema: 1, id, revision, name: 'Fixture',
    imageId: 'test-full', imageSha256: 'a'.repeat(64), cpus: 2, memoryMiB: 2048, networkEnabled: true, createdAt: new Date().toISOString() }));
  const calls: Record<string, unknown>[] = [];
  const server = createServer((client) => {
    let data = '';
    client.setEncoding('utf8'); client.on('data', (part) => {
      data += part;
      if (!data.includes('\n')) return;
      calls.push(JSON.parse(data));
      client.end(JSON.stringify({ result: { revision: 1, vmRevision: revision, enabled: true, username: 'guest', credentialsStored: true, ready: false } }) + '\n');
    });
  });
  await new Promise<void>((resolve) => server.listen(socket, resolve));
  const { createApp } = await import('../src/app.js');
  const app = createApp({ projectDirectory: join(root, 'Projects'), providers: { directory: join(root, 'Providers') } });
  try {
    const auth = await app.inject('/api/vms');
    assert.equal(auth.statusCode, 200);
    const headers = { cookie: String(auth.headers['set-cookie']).split(';')[0], 'x-csrf-token': auth.json().csrfToken };
    const url = `/api/vms/${id}/development-access`;
    const payload = { revision: 0, vmRevision: revision, enabled: true, username: 'guest', password: 'fixture-private' };
    assert.equal((await app.inject({ method: 'PATCH', url, payload })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: url + '/check', headers: { ...headers, origin: 'http://foreign.test' } })).statusCode, 403);
    assert.equal(calls.length, 0);
    const saved = await app.inject({ method: 'PATCH', url, payload, headers });
    assert.equal(saved.statusCode, 200); assert(!Object.hasOwn(saved.json(), 'password')); assert(!saved.body.includes('fixture-private'));
    assert.deepEqual(calls.at(-1), { operation: 'access_save', vmId: id, input: payload });
    const withoutPassword = { revision: 1, vmRevision: revision, enabled: true, username: 'guest' };
    assert.equal((await app.inject({ method: 'PATCH', url, payload: withoutPassword, headers })).statusCode, 200);
    assert.deepEqual(calls.at(-1), { operation: 'access_save', vmId: id, input: withoutPassword });
    assert.equal((await app.inject({ method: 'POST', url: url + '/check', headers })).statusCode, 200);
    assert.deepEqual(calls.at(-1), { operation: 'access_check', vmId: id });
  } finally {
    await app.close(); await new Promise<void>((resolve) => server.close(() => resolve()));
    if (previous.r4os === undefined) delete process.env.STUDIO_R4OS_DIR; else process.env.STUDIO_R4OS_DIR = previous.r4os;
    if (previous.socket === undefined) delete process.env.STUDIO_DEVELOPMENT_SOCKET; else process.env.STUDIO_DEVELOPMENT_SOCKET = previous.socket;
    await rm(root, { recursive: true, force: true });
  }
});
