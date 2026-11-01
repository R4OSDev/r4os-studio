import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:net';
import { once } from 'node:events';
import Fastify from 'fastify';
import { ProjectSessions } from '../src/modules/projects/sessions.js';
import { projectPinRoutes } from '../src/modules/projects/pin-routes.js';

await test('pin changes require session, origin, CSRF and an exact installed selection; coordinator receives no paths or arbitrary pins', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-project-pins-'));
  const socket = join(root, 'host.sock');
  const previous = [process.env.STUDIO_AGENTS_SOCKET, process.env.STUDIO_DEVELOPMENT_SOCKET];
  process.env.STUDIO_AGENTS_SOCKET = socket; process.env.STUDIO_DEVELOPMENT_SOCKET = socket;
  const seen: Record<string, unknown>[] = [];
  const server = createServer(client => {
    let raw = '';
    client.on('data', part => { raw += part; });
    client.on('end', () => {
      const request = JSON.parse(raw); seen.push(request);
      client.end(JSON.stringify({ result: request.operation === 'capabilities'
        ? { enabled: true, projectDeletionLocks: 1, projectPinLocks: 1, features: { projectPins: 1 } }
        : { requestId: request.input.requestId, state: 'complete' } }) + '\n');
    });
  });
  server.listen(socket); await once(server, 'listening');
  const app = Fastify();
  const sessions = new ProjectSessions();
  app.addHook('onRequest', async (request, reply) => sessions.validate(request, reply));
  app.get('/auth', async (request, reply) => ({ csrfToken: sessions.session(request, reply, true).token }));
  projectPinRoutes(app, join(root, 'Projects'), sessions);
  const id = '51f78562-3b45-4b4e-b7e1-9d6c95f33fba';
  const input = { requestId: '06a73641-7130-433d-9697-4e944007c1a6', revision: 3, sdkId: 'a'.repeat(40), selectionId: 'b'.repeat(64) };
  try {
    const auth = await app.inject('/auth');
    const cookie = String(auth.headers['set-cookie']).split(';')[0], token = auth.json().csrfToken;
    const headers = { cookie, 'x-csrf-token': token, origin: 'http://localhost:80' };
    for (const invalid of [{}, { cookie }, { ...headers, origin: 'http://foreign.test' }]) {
      assert.equal((await app.inject({ method: 'POST', url: `/${id}/pins`, payload: input, headers: invalid })).statusCode, 403);
    }
    for (const payload of [{ ...input, pins: {} }, { ...input, path: '/etc' }, { ...input, revision: -1 }, { ...input, sdkId: '../other' }]) {
      assert.equal((await app.inject({ method: 'POST', url: `/${id}/pins`, payload, headers })).statusCode, 400);
    }
    assert.equal(seen.length, 0);
    const result = await app.inject({ method: 'POST', url: `/${id}/pins`, payload: input, headers });
    assert.equal(result.statusCode, 200, result.body);
    assert.deepEqual(result.json(), { requestId: input.requestId, state: 'complete' });
    assert.deepEqual(seen.find(value => value.operation === 'project_pins_apply'), {
      operation: 'project_pins_apply', projectId: id, input, hosts: { agents: true, development: true, unsafe: false },
    });
  } finally {
    await app.close(); await new Promise<void>(resolve => server.close(() => resolve()));
    [process.env.STUDIO_AGENTS_SOCKET, process.env.STUDIO_DEVELOPMENT_SOCKET] = previous;
    if (previous[0] === undefined) delete process.env.STUDIO_AGENTS_SOCKET;
    if (previous[1] === undefined) delete process.env.STUDIO_DEVELOPMENT_SOCKET;
    await rm(root, { recursive: true, force: true });
  }
});
