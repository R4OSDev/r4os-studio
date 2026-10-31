import test from 'node:test';
import assert from 'node:assert/strict';
import Fastify from 'fastify';
import { createServer, type Socket } from 'node:net';
import { get, type IncomingMessage, type ServerResponse } from 'node:http';
import { mkdir, mkdtemp, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { once } from 'node:events';
import { runRoutes } from '../src/modules/agent-sessions/run-routes.js';
import { ProjectSessions } from '../src/modules/projects/sessions.js';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

const turn = () => new Promise<void>((resolve) => setImmediate(resolve));
const event = (seq: number, text = 'Original event') => ({ seq, kind: 'notice', runId: 'original-run', payload: { text } });

async function fixture(owner: 'project' | 'skill', read: (after: number, count: number) => Promise<ReturnType<typeof event>[]>) {
  const directory = fileURLToPath(new URL('../../../Temp/session-streams/', import.meta.url));
  await mkdir(directory, { recursive: true });
  const root = await mkdtemp(join(directory, 'http-'));
  const socketPath = join(root, 'host.sock'), previous = process.env.STUDIO_AGENTS_SOCKET;
  const peers = new Set<Socket>();
  let polls = 0;
  const calls: Record<string, unknown>[] = [];
  const server = createServer({ allowHalfOpen: true }, (socket) => {
    peers.add(socket); socket.on('close', () => peers.delete(socket)); socket.on('error', () => {});
    let raw = '';
    socket.on('data', (chunk) => { raw += chunk.toString(); });
    socket.on('end', () => {
      const call = JSON.parse(raw); calls.push(call);
      void read(call.after, ++polls).then((events) => {
        socket.end(JSON.stringify({ result: { events, session: {} } }) + '\n');
      });
    });
  });
  await new Promise<void>((resolve) => server.listen(socketPath, resolve));
  process.env.STUDIO_AGENTS_SOCKET = socketPath;
  const app = Fastify();
  const security = new ProjectSessions(owner === 'project' ? 'projects' : 'skills');
  const id = randomUUID(), sessionId = randomUUID(), path = `/${id}/sessions/${sessionId}/events`;
  const responses: ServerResponse[] = [];
  let writesAfterClose = 0, ends = 0;
  app.addHook('onRequest', async (request, reply) => {
    security.validate(request, reply);
    if (!request.url.startsWith(path)) return;
    const response = reply.raw;
    responses.push(response);
    const write = response.write.bind(response), end = response.end.bind(response);
    response.write = ((...args: Parameters<ServerResponse['write']>) => {
      if (response.writableEnded || response.destroyed) writesAfterClose++;
      return write(...args);
    }) as ServerResponse['write'];
    response.end = ((...args: Parameters<ServerResponse['end']>) => { ends++; return end(...args); }) as ServerResponse['end'];
  });
  app.get('/session', async (request, reply) => { security.session(request, reply, true); return { ready: true }; });
  app.get('/health', async () => ({ ready: true }));
  runRoutes(app, security, owner);
  await app.listen({ host: '127.0.0.1', port: 0 });
  const address = app.server.address(); assert(address && typeof address !== 'string');
  const base = `http://127.0.0.1:${address.port}`;
  const auth = await fetch(base + '/session');
  const cookie = auth.headers.get('set-cookie')!.split(';')[0];
  await auth.json();
  const clients = new Set<IncomingMessage>();
  let cleanup: Promise<void> | undefined;
  return {
    app, base, path, cookie, calls, responses,
    get polls() { return polls; },
    get writesAfterClose() { return writesAfterClose; },
    get ends() { return ends; },
    async connect(after = 0, last = '') {
      const response = await new Promise<IncomingMessage>((resolve, reject) => {
        get(base + path + `?after=${after}`, { headers: { cookie, ...(last ? { 'last-event-id': last } : {}) } }, resolve).on('error', reject);
      });
      clients.add(response); response.on('error', () => {});
      assert.equal(response.statusCode, 200);
      return response;
    },
    close(): Promise<void> {
      return cleanup ??= (async () => {
        for (const client of clients) client.destroy();
        await app.close();
        for (const peer of peers) peer.destroy();
        await new Promise<void>((resolve) => server.close(() => resolve()));
        if (previous === undefined) delete process.env.STUDIO_AGENTS_SOCKET; else process.env.STUDIO_AGENTS_SOCKET = previous;
        await rm(root, { recursive: true, force: true });
      })();
    },
  };
}

await test('SSE backpressure on the heartbeat poll keeps the HTTP process alive', { timeout: 20_000 }, async (t) => {
  const f = await fixture('project', async (_after, count) => count === 41 ? [event(1, 'x'.repeat(128 * 1024))] : []);
  t.after(() => f.close());
  try {
    const response = await f.connect();
    let body = '';
    response.setEncoding('utf8'); response.on('data', (part) => { body += part; });
    await once(response, 'end');
    await turn();
    assert.equal(f.polls, 41); // Initial read plus forty polls: backpressure and heartbeat coincide.
    assert.equal(f.writesAfterClose, 0);
    assert.equal(f.ends, 1);
    assert.match(body, /id: 1\ndata:/);
    assert(!body.includes(': heartbeat'));
    assert.deepEqual(await (await fetch(f.base + '/health')).json(), { ready: true });
  } finally { await f.close(); }
});

for (const owner of ['project', 'skill'] as const) {
  await test(`${owner} SSE disconnect during a read preserves cursor replay and releases the stream`, { timeout: 5_000 }, async (t) => {
    const pending = deferred<void>(), result = deferred<ReturnType<typeof event>[]>(), replied = deferred<void>();
    let replay = false;
    const f = await fixture(owner, async (after, count) => {
      if (count === 2) {
        pending.resolve();
        const events = await result.promise; replied.resolve(); return events;
      }
      if (!replay) return [];
      if (after < 9) return [event(8), event(9)];
      if (count === 4) return [];
      return [event(10)];
    });
    t.after(() => f.close());
    try {
      assert.equal((await fetch(f.base + f.path)).status, 403);
      assert.equal((await fetch(f.base + f.path, { headers: { cookie: f.cookie, origin: 'http://foreign.test' } })).status, 403);
      assert.equal((await f.app.inject({ url: f.path, headers: { cookie: f.cookie, host: 'foreign.test' } })).statusCode, 403);
      const response = await f.connect();
      await pending.promise;
      const closed = once(f.responses.at(-1)!, 'close'); response.destroy(); await closed;
      result.resolve([event(9)]); await replied.promise;
      // Allow the host reply to traverse both local Unix-socket endpoints.
      for (let i = 0; i < 8; i++) await turn();
      assert.equal(f.writesAfterClose, 0);
      const stoppedAt = f.polls;
      await new Promise((resolve) => setTimeout(resolve, 350));
      assert.equal(f.polls, stoppedAt);
      replay = true;
      const next = await f.connect(4, '8');
      let body = '';
      next.setEncoding('utf8');
      const live = new Promise<void>((resolve) => next.on('data', (part) => { body += part; if (body.includes('id: 10')) resolve(); }));
      await live;
      assert(!body.includes('id: 8\n'));
      assert.match(body, /id: 9\ndata:.*"delivery":"replay"/);
      assert.match(body, /id: 10\ndata:.*"delivery":"live"/);
      assert.equal(f.calls[2].after, 8);
      assert(f.calls.every((call) => call.sessionId && (owner === 'project'
        ? call.projectId && !call.ownerId
        : call.ownerType === 'skill' && call.ownerId && !call.projectId)));
    } finally { result.resolve([]); await f.close(); }
  });
}

await test('SSE response errors and shutdown close once while a poll is pending', { timeout: 5_000 }, async (t) => {
  for (const reason of ['error', 'shutdown'] as const) {
    const pending = deferred<void>(), result = deferred<ReturnType<typeof event>[]>();
    const f = await fixture('project', async (_after, count) => {
      if (count === 1) return [];
      pending.resolve(); return result.promise;
    });
    t.after(() => f.close());
    try {
      const response = await f.connect(); response.resume();
      await pending.promise;
      if (reason === 'error') {
        f.responses[0].emit('error', new Error('Isolated response failure'));
        f.responses[0].emit('error', new Error('Repeated response failure'));
      } else await f.app.close();
      result.resolve([event(1)]);
      for (let i = 0; i < 8; i++) await turn();
      assert.equal(f.ends, 1);
      assert.equal(f.writesAfterClose, 0);
      const stoppedAt = f.polls;
      await new Promise((resolve) => setTimeout(resolve, 350));
      assert.equal(f.polls, stoppedAt);
      if (reason === 'error') assert.deepEqual(await (await fetch(f.base + '/health')).json(), { ready: true });
    } finally { result.resolve([]); await f.close(); }
  }
});
