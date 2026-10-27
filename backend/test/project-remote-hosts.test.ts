import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createApp } from '../src/app.js';

await test('local project Remote Host assignment is additive, revisioned and independent of VM and pins', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-project-remotes-')); const ids = [randomUUID(), randomUUID()], vm = randomUUID();
  const app = createApp({ projectDirectory: join(root, 'Projects'), providers: { directory: join(root, 'LLMProvider') } });
  try {
    const first = await app.inject('/api/projects');
    const headers = { cookie: String(first.headers['set-cookie']).split(';')[0], 'x-csrf-token': first.json().csrfToken };
    for (const id of ids) { await mkdir(join(root, 'Projects', id, 'Workspace'), { recursive: true }); await writeFile(join(root, 'Projects', id, 'Workspace/module.R4MF'), 'own fixture source'); }
    await promisify(execFile)('/usr/bin/python3', ['-B', '-c', `
import sqlite3,sys,json
with sqlite3.connect(sys.argv[1]) as db:
 for i,identity in enumerate(sys.argv[2:4]):db.execute("INSERT INTO projects VALUES (?,?,'','Zig','terminal',?,?,?,'now','now',1,'ready')",(identity,'Own '+str(i),'MODULE'+str(i),sys.argv[4],json.dumps({'retained':'pins'})))
`, join(root, 'Projects/Projects.sqlite'), ...ids, vm]);
    const before = await readFile(join(root, 'Projects/Projects.sqlite'));
    const legacy = await app.inject({ url: '/api/projects/' + ids[0], headers }); assert.equal(legacy.statusCode, 200, legacy.body);
    assert.equal(legacy.json().project.remoteHostId, null); assert.deepEqual(await readFile(join(root, 'Projects/Projects.sqlite')), before);
    const remote = await app.inject('/api/remote-hosts'); const remoteHeaders = { cookie: String(remote.headers['set-cookie']).split(';')[0], 'x-csrf-token': remote.json().csrfToken };
    const added = await app.inject({ method: 'POST', url: '/api/remote-hosts', headers: remoteHeaders, payload: { requestId: randomUUID(), name: 'Own shared target', address: '127.0.0.1' } }); assert.equal(added.statusCode, 200, added.body); const host = added.json();
    const change = (id: string, revision: number, remoteHostId: string | null) => app.inject({ method: 'PATCH', url: '/api/projects/' + id, headers, payload: { revision, remoteHostId } });
    const missing = await change(ids[0], 1, randomUUID()); assert.equal(missing.statusCode, 409, missing.body);
    const saved = await change(ids[0], 1, host.id); assert.equal(saved.statusCode, 200, saved.body);
    assert.equal(saved.json().project.remoteHostId, host.id); assert.equal(saved.json().project.vmId, vm); assert.deepEqual(saved.json().project.pins, { retained: 'pins' });
    assert.equal((await change(ids[0], 1, null)).statusCode, 409); assert.equal((await change(ids[1], 1, host.id)).statusCode, 200);
    const remove = () => app.inject({ method: 'DELETE', url: '/api/remote-hosts/' + host.id, headers: remoteHeaders, payload: { requestId: randomUUID(), revision: host.revision, confirm: true } });
    assert.equal((await remove()).statusCode, 409); assert.equal((await change(ids[0], 2, null)).statusCode, 200); assert.equal((await remove()).statusCode, 409);
    assert.equal((await change(ids[1], 2, null)).statusCode, 200); assert.equal((await remove()).statusCode, 200);
    for (const id of ids) assert.equal(await readFile(join(root, 'Projects', id, 'Workspace/module.R4MF'), 'utf8'), 'own fixture source');
  } finally { await app.close(); await rm(root, { recursive: true, force: true }); }
});
