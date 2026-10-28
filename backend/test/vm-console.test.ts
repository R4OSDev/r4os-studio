import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { mkdtemp, mkdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import Fastify from 'fastify';
import websocket from '@fastify/websocket';
import { WebSocket } from 'ws';

const runtime = await mkdtemp(join(tmpdir(), 'studio-console-test-'));
process.env.STUDIO_VM_RUNTIME_DIR = runtime;
const { PointerControllers } = await import('../src/modules/virtual-machines/pointer.js');
const { ConsoleTickets, ConsoleBridge } = await import('../src/modules/virtual-machines/console.js');
const id = 'a1a1a1a1-1111-4111-8111-111111111111';
await mkdir(join(runtime, id));

await test('console grants bind VM and browser session, expire and cannot be replayed', () => {
  const tickets = new ConsoleTickets();
  const value = tickets.issue(id, 'browser-A');
  const protocols = `binary, studio-ticket.${value}`;
  assert.throws(() => tickets.consume(id, 'browser-B', protocols), /Reload the console/);
  assert.throws(() => tickets.consume('other-vm', 'browser-A', protocols), /Reload the console/);
  assert.throws(() => tickets.consume(id, 'browser-A', protocols, 'pointer'), /Reload the console/);
  tickets.consume(id, 'browser-A', protocols);
  assert.throws(() => tickets.consume(id, 'browser-A', protocols), /Reload the console/);
  const expired = tickets.issue(id, 'browser-A'), original = Date.now;
  try { Date.now = () => original() + 20_001; assert.throws(() => tickets.consume(id, 'browser-A', `studio-ticket.${expired}`), /Reload the console/); }
  finally { Date.now = original; }
  const spectator = tickets.issue(id, 'browser-A', 'display', 'spectator');
  assert.equal(tickets.consume(id, 'browser-A', `studio-ticket.${spectator}`), 'spectator');
});
await test('development takeover closes controls with a reconnect signal and preserves spectator frames', async () => {
  const upstream = createServer((socket) => {
    socket.on('error', () => {});
    socket.write(Buffer.from('RFB 003.008\n'));
    socket.on('data', () => socket.write(Buffer.from([1, 1])));
  });
  upstream.listen(join(runtime, id, 'vnc.sock')); await once(upstream, 'listening');
  const bridge = new ConsoleBridge(), app = Fastify(); await app.register(websocket);
  app.addHook('preClose', async () => bridge.close());
  app.get('/control', { websocket: true }, (socket) => bridge.attach(id, socket));
  app.get('/view', { websocket: true }, (socket) => bridge.attach(id, socket, 'spectator'));
  await app.listen({ host: '127.0.0.1', port: 0 });
  const address = app.server.address(); assert(address && typeof address !== 'string');
  const base = `ws://127.0.0.1:${address.port}`;
  const control = new WebSocket(base + '/control'), viewer = new WebSocket(base + '/view');
  try {
    await Promise.all([once(control, 'message'), once(viewer, 'message')]);
    const closed = once(control, 'close'); bridge.closeControls(id);
    assert.equal((await closed)[0], 4001); assert.equal(viewer.readyState, WebSocket.OPEN);
    const update = once(viewer, 'message'); viewer.send(Buffer.from('RFB 003.008\n'));
    assert.deepEqual((await update)[0], Buffer.from([1, 1]));
  } finally { control.terminate(); viewer.terminate(); bridge.close(); await app.close(); await new Promise<void>((resolve) => upstream.close(() => resolve())); }
});

await test('console bridge transports binary RFB through a private Unix socket, limits clients and closes on shutdown', async () => {
  const upstream = createServer((socket) => {
    socket.write(Buffer.from('RFB 003.008\n'));
    socket.on('data', (chunk) => socket.write(chunk));
  });
  upstream.listen(join(runtime, id, 'vnc.sock')); await once(upstream, 'listening');
  const bridge = new ConsoleBridge(), app = Fastify();
  await app.register(websocket);
  app.addHook('preClose', async () => bridge.close());
  app.get('/console', { websocket: true }, (socket) => bridge.attach(id, socket));
  await app.listen({ host: '127.0.0.1', port: 0 });
  const address = app.server.address(); assert(address && typeof address !== 'string');
  const url = `ws://127.0.0.1:${address.port}/console`;
  const sockets: WebSocket[] = [];
  try {
    const first = new WebSocket(url); sockets.push(first);
    const banner = once(first, 'message'); await once(first, 'open');
    assert.equal((await banner)[0].toString(), 'RFB 003.008\n');
    const data = Buffer.from([0, 1, 255, 42]), echoed = once(first, 'message'); first.send(data);
    assert.deepEqual((await echoed)[0], data);
    const second = new WebSocket(url); sockets.push(second); await once(second, 'open');
    // Wait for both upstream peers to be registered before probing the cap.
    const third = new WebSocket(url); sockets.push(third); const closed = once(third, 'close'); await once(third, 'open');
    assert.equal((await closed)[0], 1013);
    const disconnected = once(first, 'close'); await app.close(); await disconnected;
  } finally {
    for (const socket of sockets) socket.terminate();
    bridge.close(); await app.close(); await new Promise<void>((resolve) => upstream.close(() => resolve()));
  }
});
await test('captured mouse forwards bounded relative motion, preserves button edges and releases on disconnect', async () => {
  const commands: { type: string; data: { axis?: string; value?: number; button?: string; down?: boolean } }[][] = [];
  const monitor = createServer((socket) => {
    socket.write(JSON.stringify({ QMP: {} }) + '\n');
    let pending = '';
    socket.on('data', (chunk) => {
      pending += chunk.toString();
      while (pending.includes('\n')) {
        const end = pending.indexOf('\n'), message = JSON.parse(pending.slice(0, end)); pending = pending.slice(end + 1);
        if (message.execute === 'input-send-event') commands.push(message.arguments.events);
        socket.write(JSON.stringify({ return: {}, id: message.id }) + '\n');
      }
    });
    socket.on('error', () => {});
  });
  monitor.listen(join(runtime, id, 'qmp.sock')); await once(monitor, 'listening');
  const controllers = new PointerControllers(), app = Fastify(); await app.register(websocket);
  app.addHook('preClose', async () => controllers.close());
  app.get('/pointer', { websocket: true }, (socket) => controllers.attach(id, socket));
  await app.listen({ host: '127.0.0.1', port: 0 });
  const address = app.server.address(); assert(address && typeof address !== 'string');
  const url = `ws://127.0.0.1:${address.port}/pointer`, client = new WebSocket(url);
  try {
    assert.equal(JSON.parse((await once(client, 'message'))[0].toString()).ready, true);
    const second = new WebSocket(url), refused = once(second, 'close');
    await once(second, 'open'); assert.equal((await refused)[0], 1013);
    client.send(JSON.stringify({ dx: 17, dy: -8, buttons: 1 }));
    client.send(JSON.stringify({ dx: 9, dy: 0, buttons: 0 }));
    for (let attempt = 0; attempt < 100 && commands.flat().filter((event) => event.data.button === 'left').length < 3; attempt++) await new Promise((resolve) => setTimeout(resolve, 10));
    assert(commands.flat().some((event) => event.type === 'rel' && event.data.axis === 'x' && event.data.value === 17));
    const edges = commands.flat().filter((event) => event.data.button === 'left').map((event) => event.data.down);
    assert.deepEqual(edges.slice(0, 3), [false, true, false]);
    const before = commands.length;
    client.send(JSON.stringify({ dx: 200, dy: 130, buttons: 0 }));
    for (let attempt = 0; attempt < 100 && commands.slice(before).flat().filter((event) => event.data.axis === 'x').reduce((sum, event) => sum + (event.data.value ?? 0), 0) < 200; attempt++) await new Promise((resolve) => setTimeout(resolve, 10));
    assert(commands.slice(before).flat().every((event) => Math.abs(event.data.value ?? 0) <= 96));
    assert.equal(commands.slice(before).flat().filter((event) => event.data.axis === 'y').reduce((sum, event) => sum + (event.data.value ?? 0), 0), 130);
    client.send(JSON.stringify({ dx: 0, dy: 0, buttons: 1 }));
    for (let attempt = 0; attempt < 100 && commands.flat().filter((event) => event.data.button === 'left').at(-1)?.data.down !== true; attempt++) await new Promise((resolve) => setTimeout(resolve, 10));
    const closed = once(client, 'close'); client.send(JSON.stringify({ dx: 99999, dy: 0, buttons: 1 }));
    assert.equal((await closed)[0], 1008); await controllers.close();
    assert.deepEqual(commands.at(-1)?.map((event) => event.data.down), [false, false, false]);
    assert(!commands.flat().some((event) => event.data.value === 99999));
  } finally { client.terminate(); await controllers.close(); await app.close(); await new Promise<void>((resolve) => monitor.close(() => resolve())); }
});
await rm(runtime, { recursive: true, force: true });
