import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import { createApp } from '../src/app.js';
import { projectStore } from '../src/modules/projects/store.js';
import { componentRoot } from '../src/modules/components/tools.js';

await test('sessions preserve idempotency, settings, tool permissions and project isolation',
  { skip: !existsSync(join(componentRoot(), 'Toolchains/Codex/0.163.0/codex')) && 'Install the qualified Codex runtime.' }, async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-sessions-'));
  const directory = join(root, 'Projects'), providers = join(root, 'LLMProvider');
  const ids = [randomUUID(), randomUUID()], provider = randomUUID();
  const app = createApp({ projectDirectory: directory, providers: { directory: providers } });
  try {
    await projectStore(directory, { operation: 'list' });
    for (const id of ids) {
      await mkdir(join(directory, id, 'Workspace'), { recursive: true });
      await writeFile(join(directory, id, 'Workspace/module.R4MF'), 'R4OS_MODULE_MANIFEST=2\n');
    }
    await promisify(execFile)('/usr/bin/python3', ['-c', `
import sqlite3,sys,json
with sqlite3.connect(sys.argv[1]) as db:
 for ident in json.loads(sys.argv[2]):
  db.execute("INSERT INTO projects VALUES (?,?, '', 'Zig','terminal',?,NULL,'{}','now','now',1,'ready')",(ident,ident,ident))
`, join(directory, 'Projects.sqlite'), JSON.stringify(ids)]);
    await mkdir(join(providers, provider), { recursive: true });
    await writeFile(join(providers, 'providers.json'), JSON.stringify([{ id: provider, name: 'Fixture provider', type: 'openai', connected: true }]));
    await writeFile(join(providers, provider, 'models_cache.json'), JSON.stringify({ models: [{ slug: 'fixture-model', display_name: 'Fixture model',
      visibility: 'list', priority: 0, default_reasoning_level: 'low', supported_reasoning_levels: [{ effort: 'low' }, { effort: 'high' }] }] }));
    const base = `/api/projects/${ids[0]}/sessions`;
    assert.equal((await app.inject(base)).statusCode, 403);
    const auth = await app.inject('/api/projects');
    const headers = { cookie: String(auth.headers['set-cookie']).split(';')[0], 'x-csrf-token': auth.json().csrfToken };
    const opts = await app.inject({ url: base + '/options', headers });
    assert.equal(opts.statusCode, 200, opts.body);
    assert.equal(opts.json().tools.length, 9);
    assert.equal(opts.json().providers[0].models[0].id, 'fixture-model');
    assert.equal(opts.json().engine.available, true);
    const payload = { name: 'First session', providerId: provider, model: 'fixture-model', effort: 'low', requestId: randomUUID() };
    assert.equal((await app.inject({ method: 'POST', url: base, payload })).statusCode, 403);
    const replies = await Promise.all([1, 2].map(() => app.inject({ method: 'POST', url: base, headers, payload })));
    for (const reply of replies) assert.equal(reply.statusCode, 201, reply.body);
    const session = replies[0].json().session;
    assert.equal(replies[1].json().session.id, session.id);
    assert.equal(Object.keys(session.permissions).length, 9);
    assert(Object.values(session.permissions).every((value) => value === true));
    assert.equal(session.latestRun, null);
    assert.equal((await app.inject({ url: base, headers })).json().sessions.length, 1);
    assert.equal((await app.inject({ method: 'POST', url: base, headers, payload: { ...payload, name: 'Different' } })).statusCode, 409);
    const url = base + '/' + session.id;
    const changed = { ...session.permissions, 'studio.write_file': false };
    const update = await app.inject({ method: 'PATCH', url: url + '/settings', headers, payload: { revision: 1, permissions: changed } });
    assert.equal(update.statusCode, 200, update.body);
    assert.equal(update.json().session.permissions['studio.write_file'], false);
    assert.equal((await app.inject({ method: 'PATCH', url: url + '/settings', headers, payload: { revision: 1, name: 'Stale' } })).statusCode, 409);
    const invalid = { ...changed }; delete invalid['studio.read_file']; invalid['studio.unknown'] = true;
    assert.equal((await app.inject({ method: 'PATCH', url: url + '/settings', headers, payload: { revision: 2, permissions: invalid } })).statusCode, 400);
    assert.deepEqual((await app.inject({ url: url + '/history', headers })).json(), { items: [], before: null, cursor: 0 });
    assert.equal((await app.inject({ url: `/api/projects/${ids[1]}/sessions/${session.id}`, headers })).statusCode, 404);
    assert.equal((await app.inject({ url, headers: { ...headers, origin: 'http://foreign.test' } })).statusCode, 403);
    assert(!JSON.stringify(session).includes(directory));
    const again = createApp({ projectDirectory: directory, providers: { directory: providers } });
    try {
      const auth2 = await again.inject('/api/projects');
      const h2 = { cookie: String(auth2.headers['set-cookie']).split(';')[0] };
      const restored = (await again.inject({ url, headers: h2 })).json().session;
      assert.equal(restored.permissions['studio.write_file'], false);
      assert.equal(restored.revision, 2);
      await writeFile(join(providers, 'providers.json'), '[]');
      assert.equal((await again.inject({ url, headers: h2 })).statusCode, 200);
    } finally { await again.close(); }
    const db = join(directory, ids[0], 'Sessions/Sessions.sqlite');
    await writeFile(db, 'preserve corrupt data');
    assert.equal((await app.inject({ url: base, headers })).statusCode, 503);
    assert.equal(await readFile(db, 'utf8'), 'preserve corrupt data');
  } finally { await app.close(); await rm(root, { recursive: true, force: true }); }
});
