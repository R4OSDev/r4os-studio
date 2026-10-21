import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, rm, symlink, writeFile, readFile, rename } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { randomUUID } from 'node:crypto';
import { existsSync } from 'node:fs';
import { createApp } from '../src/app.js';
import { projectStore } from '../src/modules/projects/store.js';
import type { Project } from '../../shared/projects.js';
import { componentRoot } from '../src/modules/components/tools.js';

await test('project catalog preserves foreign folders, lists registered UUIDs and rejects invalid origins/storage', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-projects-'));
  const directory = join(root, 'Projects');
  const app = createApp({ projectDirectory: directory, providers: { directory: join(root, 'LLMProvider') } });
  try {
    const empty = (await app.inject('/api/projects')).json();
    assert.deepEqual(empty.projects, []);
    assert.match(empty.csrfToken, /^[a-f0-9]{64}$/);
    await mkdir(join(directory, 'Project 10'), { recursive: true });
    await mkdir(join(directory, 'Project 2', 'Source'), { recursive: true });
    await mkdir(join(root, 'Outside'));
    await symlink(join(root, 'Outside'), join(directory, 'Linked project'));
    await writeFile(join(directory, 'notes.txt'), 'Not a project');

    assert.deepEqual((await app.inject('/api/projects')).json().projects, []);
    await promisify(execFile)('/usr/bin/python3', ['-c', `
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
 for ident,name in [('b4f106a9-a052-4845-8942-ac79ac285659','Project 10'),('435af809-2fc1-4347-b895-af0bc16115aa','Project 2')]:
  db.execute("INSERT INTO projects VALUES (?,?, '', 'Zig','terminal',?,NULL,'{}','now','now',1,'ready')",(ident,name,ident))
`, join(directory, 'Projects.sqlite')]);
    const response = await app.inject('/api/projects');
    assert.equal(response.statusCode, 200);
    assert.equal(response.headers['cache-control'], 'no-store');
    assert.deepEqual(response.json().projects, [
      { id: '435af809-2fc1-4347-b895-af0bc16115aa', name: 'Project 2' },
      { id: 'b4f106a9-a052-4845-8942-ac79ac285659', name: 'Project 10' },
    ]);
    for (const headers of [
      { host: 'foreign.test' }, { origin: 'http://foreign.test' },
      { origin: 'https://localhost:80' }, { origin: 'invalid' }, { 'sec-fetch-site': 'cross-site' },
    ]) {
      assert.equal((await app.inject({ url: '/api/projects', headers })).statusCode, 403);
    }
    assert.equal((await app.inject({ url: '/api/projects', headers: { origin: 'http://localhost:80' } })).statusCode, 200);
    assert.equal((await app.inject({ method: 'POST', url: '/api/projects', payload: {} })).statusCode, 400);

    await rm(directory, { recursive: true });
    await writeFile(directory, 'Invalid storage');
    const failure = await app.inject('/api/projects');
    assert.equal(failure.statusCode, 503);
    assert.deepEqual(failure.json(), { message: 'Projects could not be loaded.' });
  } finally {
    await app.close();
    await rm(root, { recursive: true, force: true });
  }
});

await test('project creation is pinned and idempotent; settings preserve files and identity; prepared publication recovers safely',
  { skip: !existsSync(join(componentRoot(), 'Profiles/versions.json')) && 'Install the pinned SDK profile for the real creation integration check.' }, async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-create-'));
  const directory = join(root, 'Projects');
  const app = createApp({ projectDirectory: directory, providers: { directory: join(root, 'LLMProvider') } });
  const priorRoot = process.env.STUDIO_R4OS_DIR;
  try {
    const session = await app.inject('/api/projects');
    const cookie = String(session.headers['set-cookie']).split(';')[0];
    const headers = { cookie, 'x-csrf-token': session.json().csrfToken };
    assert.equal((await app.inject('/api/projects/options')).statusCode, 403);
    const response = await app.inject({ url: '/api/projects/options', headers });
    assert.equal(response.statusCode, 200, response.body);
    const options = response.json();
    const payload = { name: 'Sample project', description: 'A Unicode description: Grüße', language: 'Zig', template: 'terminal',
      vmId: null, optionsRevision: options.revision, requestId: randomUUID(), guestFormats: [] };
    assert.equal((await app.inject({ method: 'POST', url: '/api/projects', payload })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: '/api/projects', headers, payload: { ...payload, path: '/tmp/foreign' } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: '/api/projects', headers, payload: { ...payload, language: 'Rust' } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: '/api/projects', headers, payload: { ...payload, optionsRevision: 'a'.repeat(64) } })).statusCode, 409);
    const requests = await Promise.all([1, 2].map(() => app.inject({ method: 'POST', url: '/api/projects', headers, payload })));
    for (const value of requests) assert.equal(value.statusCode, 201, value.body);
    const project = requests[0].json().project as Project;
    assert.equal(requests[1].json().project.id, project.id);
    assert.equal((await app.inject({ url: '/api/projects', headers })).json().projects.length, 1);
    assert.equal((await app.inject({ method: 'POST', url: '/api/projects', headers, payload: { ...payload, name: 'Changed request' } })).statusCode, 409);
    const manifest = await readFile(join(directory, project.id, 'module.R4MF'), 'utf8');
    assert.match(manifest, /LANGUAGE=Zig/);
    assert.equal(project.pins.sdk.revision, '2fdc71e11d6a26fd1998dfddb43923f9d707abda');
    const updated = await app.inject({ method: 'PATCH', url: `/api/projects/${project.id}`, headers,
      payload: { revision: project.revision, name: 'Renamed project', description: 'Updated' } });
    assert.equal(updated.statusCode, 200, updated.body);
    assert.equal(updated.json().project.id, project.id);
    assert.deepEqual(updated.json().project.pins, project.pins);
    assert.equal(await readFile(join(directory, project.id, 'module.R4MF'), 'utf8'), manifest);
    assert.equal((await app.inject({ method: 'PATCH', url: `/api/projects/${project.id}`, headers,
      payload: { revision: 1, name: 'Stale' } })).statusCode, 409);
    // VM references are metadata only: no QEMU or VM manager calls.
    const vmRoot = join(root, 'R4OS'), vmId = randomUUID();
    await mkdir(join(vmRoot, 'Instances', vmId), { recursive: true });
    const vmFile = join(vmRoot, 'Instances', vmId, 'vm.json');
    await writeFile(vmFile, JSON.stringify({ id: vmId, name: 'Metadata VM' }));
    process.env.STUDIO_R4OS_DIR = vmRoot;
    const assigned = await app.inject({ method: 'PATCH', url: `/api/projects/${project.id}`, headers,
      payload: { revision: 2, vmId } });
    assert.equal(assigned.statusCode, 200, assigned.body);
    assert.equal(assigned.json().project.vmId, vmId);
    await rm(vmFile);
    const general = await app.inject({ method: 'PATCH', url: `/api/projects/${project.id}`, headers,
      payload: { revision: 3, name: 'Missing VM retained' } });
    assert.equal(general.statusCode, 200);
    assert.equal((await app.inject({ method: 'PATCH', url: `/api/projects/${project.id}`, headers,
      payload: { revision: 4, vmId: null } })).statusCode, 200);
    // An already completed retry does not replace pins with the current defaults.
    assert.equal((await app.inject({ method: 'POST', url: '/api/projects', headers, payload })).json().project.id, project.id);
    if (priorRoot === undefined) delete process.env.STUDIO_R4OS_DIR; else process.env.STUDIO_R4OS_DIR = priorRoot;
    for (const staged of [true, false]) {
      await promisify(execFile)('/usr/bin/python3', ['-c', `
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
 db.execute("UPDATE projects SET state='pending'")
 db.execute("UPDATE requests SET phase='prepared'")
`, join(directory, 'Projects.sqlite')]);
      if (staged) await rename(join(directory, project.id), join(directory, '.studio/staging', project.id));
      assert.deepEqual(await projectStore(directory, { operation: 'recover' }, 'create'), [{ id: project.id, recovered: true }]);
    assert.equal((await app.inject({ url: `/api/projects/${project.id}`, headers })).json().project.id, project.id);
    }
    // A changed target is retained, and recovery must not publish it as success.
    await writeFile(join(directory, project.id, 'src/main.zig'), '// Changed after interrupted publication');
    await promisify(execFile)('/usr/bin/python3', ['-c', `
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
 db.execute("UPDATE projects SET state='pending'")
 db.execute("UPDATE requests SET phase='prepared'")
`, join(directory, 'Projects.sqlite')]);
    assert.deepEqual(await projectStore(directory, { operation: 'recover' }, 'create'), [{ id: project.id, recovered: false }]);
    assert.equal(await readFile(join(directory, project.id, 'src/main.zig'), 'utf8'), '// Changed after interrupted publication');
  } finally {
    if (priorRoot === undefined) delete process.env.STUDIO_R4OS_DIR; else process.env.STUDIO_R4OS_DIR = priorRoot;
    await app.close();
    await rm(root, { recursive: true, force: true });
  }
});
