import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createServer } from 'node:net';
import { createApp } from '../src/app.js';
import { componentRoot } from '../src/modules/components/tools.js';
import { projectStore } from '../src/modules/projects/store.js';

await test('skill sessions have independent owners, native profiles, HTTP security and run bindings',
  { skip: !existsSync(join(componentRoot(), 'Toolchains/Codex/0.163.0/codex')) && 'Install the qualified Codex runtime.' }, async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-skill-sessions-'));
  const providers = join(root, 'LLMProvider'), provider = randomUUID(), id = randomUUID(), other = randomUUID();
  const previousSocket = process.env.STUDIO_AGENTS_SOCKET;
  const socketPath = join(root, 'agents.sock'); process.env.STUDIO_AGENTS_SOCKET = socketPath;
  const messages: Record<string, unknown>[] = [];
  let events = 0;
  const server = createServer((socket) => {
    let raw = ''; socket.setEncoding('utf8'); socket.on('data', (chunk) => { raw += chunk; });
    socket.on('end', () => {
      const request = JSON.parse(raw) as Record<string, unknown>; messages.push(request);
      const run = { id: randomUUID(), sessionId: request.sessionId, owner: { type: 'skill', id }, state: 'queued', error: null, createdAt: 'now', completedAt: null };
      const result = request.operation === 'capabilities' ? { enabled: true, protocol: 1, skillSessions: 1, skillAuthorTools: 1, globalSkills: 1, skillScripts: 1 }
        : request.operation === 'events' ? { events: [{ seq: 7, runId: run.id, kind: 'run', payload: run }], session: {} }
          : { ...run, ...(request.operation === 'stop_run' ? { state: 'interrupted', id: request.runId } : {}) };
      socket.end(JSON.stringify(request.operation === 'events' && events++ > 0 ? { error: 'Fixture stream ended.', code: 503 } : { result }) + '\n');
    });
  });
  await new Promise<void>((resolve) => server.listen(socketPath, resolve));
  const app = createApp({ projectDirectory: join(root, 'Projects'), providers: { directory: providers } });
  try {
    await mkdir(join(providers, provider), { recursive: true });
    await writeFile(join(providers, 'providers.json'), JSON.stringify([{ id: provider, name: 'Fixture', type: 'openai', connected: true }]));
    await writeFile(join(providers, provider, 'models_cache.json'), JSON.stringify({ models: [{ slug: 'fixture', visibility: 'list', supported_reasoning_levels: [{ effort: 'low' }] }] }));
    const auth = await app.inject('/api/skills');
    const headers = { cookie: String(auth.headers['set-cookie']).split(';')[0], 'x-csrf-token': auth.json().csrfToken };
    for (const skill of [id, other]) assert.equal((await app.inject({ method: 'POST', url: '/api/skills', headers, payload: { id: skill, name: 'Fixture' } })).statusCode, 200);
    const base = `/api/skills/${id}/sessions`;
    assert.equal((await app.inject(base)).statusCode, 403);
    const opts = await app.inject({ url: base + '/options', headers });
    assert.equal(opts.statusCode, 200, opts.body); assert.equal(opts.json().tools.length, 11);
    assert.equal(opts.json().engine.profile, 'studio-skill-tools-v2'); assert.equal(opts.json().engine.available, true);
    assert.equal(opts.json().skills.length, 2); assert(opts.json().skills.every((skill: { available: boolean }) => !skill.available));
    assert.equal(opts.json().development, undefined);
    const payload = { name: 'Author', providerId: provider, model: 'fixture', effort: 'low', requestId: randomUUID() };
    assert.equal((await app.inject({ method: 'POST', url: base, headers: { cookie: headers.cookie }, payload })).statusCode, 403);
    const created = await app.inject({ method: 'POST', url: base, headers, payload });
    assert.equal(created.statusCode, 201, created.body);
    const session = created.json().session;
    assert.deepEqual(session.owner, { type: 'skill', id }); assert.equal(session.projectId, undefined);
    assert.deepEqual(session.skillOverrides, {});
    assert.equal(Object.keys(session.permissions).length, 11);
    assert.equal((await app.inject({ method: 'POST', url: base, headers, payload })).json().session.id, session.id);
    assert.equal((await app.inject({ url: `/api/skills/${other}/sessions/${session.id}`, headers })).statusCode, 404);
    assert.equal((await app.inject({ url: base, headers: { ...headers, origin: 'http://foreign.test' } })).statusCode, 403);
    const url = base + '/' + session.id;
    assert.deepEqual((await app.inject({ url: url + '/history', headers })).json(), { items: [], before: null, cursor: 0 });
    const changed = await app.inject({ method: 'PATCH', url: url + '/settings', headers, payload: { revision: 1, name: 'Saved name', skillOverrides: { [other]: false } } });
    assert.equal(changed.statusCode, 200, changed.body); assert.deepEqual(changed.json().session.skillOverrides, { [other]: false });
    assert.equal((await app.inject({ method: 'PATCH', url: url + '/settings', headers, payload: { revision: 2, skillOverrides: { invalid: false } } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'PATCH', url: url + '/settings', headers, payload: { revision: 2, skillOverrides: { [randomUUID()]: false } } })).statusCode, 409);
    assert.equal((await app.inject({ method: 'PATCH', url: url + '/settings', headers, payload: { revision: 1, name: 'Stale' } })).statusCode, 409);
    const start = await app.inject({ method: 'POST', url: url + '/runs', headers, payload: { requestId: randomUUID(), revision: 2, text: 'Draft a skill' } });
    assert.equal(start.statusCode, 202, start.body);
    const sent = messages.find((v) => v.operation === 'start_run')!;
    assert.equal(sent.ownerType, 'skill'); assert.equal(sent.ownerId, id); assert.equal(sent.projectId, undefined);
    assert.equal((sent.input as Record<string, unknown>).projectInstructions, undefined);
    assert.equal((sent.input as Record<string, unknown>).skillSelection, 1);
    assert.equal((sent.input as Record<string, unknown>).skillScripts, 1);
    assert.equal((await app.inject({ method: 'POST', url: url + '/runs/' + start.json().run.id + '/stop', headers })).statusCode, 200);
    const stream = await app.inject({ url: url + '/events', headers });
    assert.equal(stream.statusCode, 200); assert.match(stream.body, /id: 7\ndata:/);
    assert(messages.filter((v) => ['start_run', 'stop_run', 'events'].includes(String(v.operation))).every((v) => v.ownerType === 'skill' && v.ownerId === id));
    // The full app initializes its existing empty project catalog on startup.
    // Skill sessions must not add a placeholder project to it.
    assert.deepEqual(await projectStore(join(root, 'Projects'), { operation: 'list' }), []);
    assert(existsSync(join(root, 'Skills', id, 'Sessions/Sessions.sqlite')));
    assert(!existsSync(join(root, 'Skills', id, 'Workspace/module.R4MF')));
  } finally {
    await app.close(); await new Promise<void>((resolve) => server.close(() => resolve()));
    if (previousSocket === undefined) delete process.env.STUDIO_AGENTS_SOCKET; else process.env.STUDIO_AGENTS_SOCKET = previousSocket;
    await rm(root, { recursive: true, force: true });
  }
});
