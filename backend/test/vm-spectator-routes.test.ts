import test, { mock } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { createServer } from 'node:net';
import { once } from 'node:events';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import Fastify from 'fastify';
import { WebSocket } from 'ws';
import type { VirtualMachine } from '../../shared/virtual-machines.js';

await test('spectator HTTP/WS grants preserve session, origin, CSRF, channel and mode binding', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-spectator-routes-'));
  process.env.STUDIO_R4OS_DIR = join(root, 'R4OS'); process.env.STUDIO_VM_RUNTIME_DIR = join(root, 'run');
  const { vmRoutes } = await import('../src/modules/virtual-machines/routes.js');
  const { VmManager } = await import('../src/modules/virtual-machines/service.js');
  const id = 'a1a1a1a1-1111-4111-8111-111111111111';
  const vm: VirtualMachine = { schema: 1, id, name: 'Fixture', cpus: 2, memoryMiB: 2048,
    imageId: 'fixture', imageSha256: 'a'.repeat(64), createdAt: new Date().toISOString(),
    state: 'running', sharePath: '/unused', shareMode: 'fat32-persistent' };
  await mkdir(join(root, 'R4OS/Instances', id), { recursive: true });
  await writeFile(join(root, 'R4OS/Instances', id, 'vm.json'), JSON.stringify(vm));
  await mkdir(join(root, 'run', id), { recursive: true });
  const upstreams = new Set<import('node:net').Socket>();
  const server = createServer((socket) => {
    upstreams.add(socket); socket.on('close', () => upstreams.delete(socket)); socket.on('error', () => {});
    socket.write(Buffer.from('RFB 003.008\n'));
  });
  await new Promise<void>((resolve) => server.listen(join(root, 'run', id, 'vnc.sock'), resolve));
  const get = mock.method(VmManager.prototype, 'get', async () => vm);
  const list = mock.method(VmManager.prototype, 'list', async () => [vm]);
  const app = Fastify(); app.setErrorHandler((error, _request, reply) => reply.code((error as { statusCode?: number }).statusCode ?? 500).send({ message: (error as Error).message }));
  await app.register(vmRoutes, { prefix: '/api/vms' }); await app.listen({ host: '127.0.0.1', port: 0 });
  const address = app.server.address(); assert(address && typeof address !== 'string');
  const origin = `http://127.0.0.1:${address.port}`, host = `127.0.0.1:${address.port}`;
  const inject = (options: Parameters<typeof app.inject>[0]) => app.inject(options);
  const auth = await app.inject({ url: '/api/vms', headers: { host } }); assert.equal(auth.statusCode, 200);
  const headers = { host, origin, cookie: String(auth.headers['set-cookie']).split(';')[0], 'x-csrf-token': auth.json().csrfToken };
  const url = `/api/vms/${id}/console-ticket`;
  const clients: WebSocket[] = [];
  try {
    assert.equal((await inject({ method: 'POST', url, payload: { mode: 'spectator' }, headers: { host } })).statusCode, 403);
    assert.equal((await inject({ method: 'POST', url, payload: { mode: 'spectator' }, headers: { ...headers, origin: 'http://foreign.invalid' } })).statusCode, 403);
    assert.equal((await inject({ method: 'POST', url, payload: { mode: 'spectator' }, headers: { ...headers, host: 'foreign.invalid' } })).statusCode, 403);
    assert.equal((await inject({ method: 'POST', url, payload: { mode: 'admin' }, headers })).statusCode, 400);
    const ticket = await inject({ method: 'POST', url, payload: { mode: 'spectator' }, headers });
    assert.equal(ticket.statusCode, 200); assert.equal(ticket.json().mode, 'spectator');
    const ws = (path: string, grant: string, custom = headers) => {
      const client = new WebSocket(origin.replace('http:', 'ws:') + `/api/vms/${id}/${path}`, ['binary', `studio-ticket.${grant}`], { headers: custom });
      clients.push(client); return client;
    };
    const foreign = ws('console', ticket.json().ticket, { ...headers, cookie: '' });
    const rejected = once(foreign, 'unexpected-response'); foreign.on('error', () => {});
    const [, response] = await rejected; assert.equal(response.statusCode, 403); response.resume(); foreign.terminate();
    const viewer = ws('console?mode=interactive', ticket.json().ticket);
    const frame = once(viewer, 'message'); await once(viewer, 'open'); assert.equal((await frame)[0].toString(), 'RFB 003.008\n');
    const replay = ws('console', ticket.json().ticket); replay.on('error', () => {});
    const [, refused] = await once(replay, 'unexpected-response'); assert.equal(refused.statusCode, 403); refused.resume(); replay.terminate();
    // The forged query never upgrades the read-only grant: unsupported client
    // authentication fails before a raw guest input path can be established.
    const closed = once(viewer, 'close'); viewer.send(Buffer.from('RFB 003.003\n')); assert.equal((await closed)[0], 1008);
    vm.state = 'stopped';
    assert.equal((await inject({ method: 'POST', url, payload: { mode: 'spectator' }, headers })).statusCode, 409);
    vm.state = 'running';
    // Older clients send no body; default admission remains compatible.
    assert.equal((await inject({ method: 'POST', url, headers })).statusCode, 200);
  } finally {
    for (const client of clients) client.terminate();
    await app.close(); for (const socket of upstreams) socket.destroy();
    await new Promise<void>((resolve) => server.close(() => resolve()));
    get.mock.restore(); list.mock.restore(); await rm(root, { recursive: true, force: true });
  }
});
