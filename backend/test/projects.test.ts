import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, rm, symlink, writeFile, readFile, rename } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { randomUUID } from 'node:crypto';
import { existsSync } from 'node:fs';
import { createServer } from 'node:net';
import { once } from 'node:events';
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

await test('permanent project deletion requires confirmation, current revision and CSRF; removes only the selected project', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-delete-'));
  const directory = join(root, 'Projects'), id = randomUUID(), foreignId = randomUUID(), vmId = randomUUID();
  const priorAgentSocket = process.env.STUDIO_AGENTS_SOCKET, priorDevelopmentSocket = process.env.STUDIO_DEVELOPMENT_SOCKET;
  const socket = join(root, 'host.sock');
  let deletionLocks = 0;
  const host = createServer((connection) => {
    let pending = '';
    connection.on('data', (chunk) => {
      pending += chunk;
      if (!pending.includes('\n')) return;
      assert.equal(JSON.parse(pending.split('\n')[0]).operation, 'capabilities');
      connection.end(JSON.stringify({ result: { enabled: true, projectDeletionLocks: deletionLocks } }) + '\n');
    });
  });
  host.listen(socket); await once(host, 'listening');
  process.env.STUDIO_AGENTS_SOCKET = socket; process.env.STUDIO_DEVELOPMENT_SOCKET = socket;
  const app = createApp({ projectDirectory: directory, providers: { directory: join(root, 'Providers') } });
  try {
    const session = await app.inject('/api/projects');
    const headers = { cookie: String(session.headers['set-cookie']).split(';')[0], 'x-csrf-token': session.json().csrfToken };
    await mkdir(join(directory, id, 'Workspace', 'nested'), { recursive: true });
    await writeFile(join(directory, id, 'Workspace', 'nested', 'source.c'), 'project source');
    await mkdir(join(directory, foreignId));
    await writeFile(join(directory, foreignId, 'keep'), 'foreign project');
    await symlink(join(directory, foreignId), join(directory, id, 'Workspace', 'external'));
    const vmFile = join(root, 'R4OS', 'Instances', vmId, 'vm.json');
    await mkdir(join(root, 'R4OS', 'Instances', vmId), { recursive: true });
    await writeFile(vmFile, JSON.stringify({ id: vmId, name: 'Keep this VM' }));
    await promisify(execFile)('/usr/bin/python3', ['-c', `
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
 db.execute("INSERT INTO projects VALUES (?,?, '', 'C','terminal','delete_fixture',?,'{}','now','now',2,'ready')",(sys.argv[2],'Delete fixture',sys.argv[3]))
 db.execute("INSERT INTO requests VALUES ('fixture-request','fixture-hash',?,'complete','{}',NULL)",(sys.argv[2],))
`, join(directory, 'Projects.sqlite'), id, vmId]);
    const url = `/api/projects/${id}`, payload = { revision: 2, confirm: true };
    for (const invalidHeaders of [
      {}, { cookie: headers.cookie }, { ...headers, origin: 'http://foreign.test' },
      { ...headers, host: 'foreign.test' }, { ...headers, 'sec-fetch-site': 'cross-site' },
    ]) assert.equal((await app.inject({ method: 'DELETE', url, headers: invalidHeaders, payload })).statusCode, 403);
    for (const invalid of [{ revision: 2 }, { ...payload, confirm: false }, { ...payload, revision: '2' },
      { ...payload, path: '/' }, { ...payload, hosts: { agents: true } }]) {
      assert.equal((await app.inject({ method: 'DELETE', url, headers, payload: invalid })).statusCode, 400);
    }
    assert.equal((await app.inject({ method: 'DELETE', url, headers, payload: { ...payload, revision: 1 } })).statusCode, 409);
    assert(existsSync(join(directory, id, 'Workspace', 'nested', 'source.c')));
    assert.equal((await app.inject({ method: 'DELETE', url, headers, payload })).statusCode, 503);
    assert(existsSync(join(directory, id, 'Workspace', 'nested', 'source.c')));
    deletionLocks = 1;
    const deleted = await app.inject({ method: 'DELETE', url, headers, payload });
    assert.equal(deleted.statusCode, 200, deleted.body);
    assert.deepEqual(deleted.json(), { id, deleted: true });
    assert(!existsSync(join(directory, id)));
    assert.equal((await app.inject('/api/projects')).json().projects.length, 0);
    assert.equal((await app.inject({ url, headers })).statusCode, 404);
    assert.equal((await app.inject({ method: 'DELETE', url, headers, payload })).statusCode, 200);
    assert.equal((await app.inject({ method: 'DELETE', url: `/api/projects/${foreignId}`, headers, payload })).statusCode, 409);
    assert.equal(await readFile(join(directory, foreignId, 'keep'), 'utf8'), 'foreign project');
    assert.equal(JSON.parse(await readFile(vmFile, 'utf8')).name, 'Keep this VM');
  } finally {
    await app.close(); await new Promise<void>((resolve) => host.close(() => resolve()));
    if (priorAgentSocket === undefined) delete process.env.STUDIO_AGENTS_SOCKET; else process.env.STUDIO_AGENTS_SOCKET = priorAgentSocket;
    if (priorDevelopmentSocket === undefined) delete process.env.STUDIO_DEVELOPMENT_SOCKET; else process.env.STUDIO_DEVELOPMENT_SOCKET = priorDevelopmentSocket;
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
    assert.equal((await app.inject({ method: 'POST', url: '/api/projects', headers, payload: { ...payload, language: 'Rust', template: 'driver' } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: '/api/projects', headers, payload: { ...payload, optionsRevision: 'a'.repeat(64) } })).statusCode, 409);
    const requests = await Promise.all([1, 2].map(() => app.inject({ method: 'POST', url: '/api/projects', headers, payload })));
    for (const value of requests) assert.equal(value.statusCode, 201, value.body);
    const project = requests[0].json().project as Project;
    assert.equal(requests[1].json().project.id, project.id);
    assert.equal((await app.inject({ url: '/api/projects', headers })).json().projects.length, 1);
    assert.equal((await app.inject({ method: 'POST', url: '/api/projects', headers, payload: { ...payload, name: 'Changed request' } })).statusCode, 409);
    const manifest = await readFile(join(directory, project.id, 'Workspace', 'module.R4MF'), 'utf8');
    assert.match(manifest, /LANGUAGE=Zig/);
    assert.equal(project.pins.sdk.revision, options.profile.sdk.revision);
    const updated = await app.inject({ method: 'PATCH', url: `/api/projects/${project.id}`, headers,
      payload: { revision: project.revision, name: 'Renamed project', description: 'Updated' } });
    assert.equal(updated.statusCode, 200, updated.body);
    assert.equal(updated.json().project.id, project.id);
    assert.deepEqual(updated.json().project.pins, project.pins);
    assert.equal(await readFile(join(directory, project.id, 'Workspace', 'module.R4MF'), 'utf8'), manifest);
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
    await writeFile(join(directory, project.id, 'Workspace', 'src/main.zig'), '// Changed after interrupted publication');
    await promisify(execFile)('/usr/bin/python3', ['-c', `
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
 db.execute("UPDATE projects SET state='pending'")
 db.execute("UPDATE requests SET phase='prepared'")
`, join(directory, 'Projects.sqlite')]);
    assert.deepEqual(await projectStore(directory, { operation: 'recover' }, 'create'), [{ id: project.id, recovered: false }]);
    assert.equal(await readFile(join(directory, project.id, 'Workspace', 'src/main.zig'), 'utf8'), '// Changed after interrupted publication');
  } finally {
    if (priorRoot === undefined) delete process.env.STUDIO_R4OS_DIR; else process.env.STUDIO_R4OS_DIR = priorRoot;
    await app.close();
    await rm(root, { recursive: true, force: true });
  }
});

await test('Rust creation uses SDK capabilities and official templates; pins and Cargo lock survive retry and Settings',
  { skip: (!existsSync(join(componentRoot(), 'Toolchains/Rust/sdk-0.64.66/.studio-component.json'))
      || JSON.parse(await readFile(join(componentRoot(), 'Profiles/versions.json'), 'utf8')).defaults?.rust?.id !== 'sdk-0.64.66')
      && 'Select the matched SDK Rust profile for this integration check.' }, async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-rust-create-'));
  const directory = join(root, 'Projects');
  const app = createApp({ projectDirectory: directory, providers: { directory: join(root, 'Providers') } });
  try {
    const session = await app.inject('/api/projects');
    const headers = { cookie: String(session.headers['set-cookie']).split(';')[0], 'x-csrf-token': session.json().csrfToken };
    const response = await app.inject({ url: '/api/projects/options', headers });
    assert.equal(response.statusCode, 200, response.body);
    const options = response.json();
    assert.equal(options.languages.find((value: { id: string }) => value.id === 'Rust').available, true);
    for (const type of ['terminal', 'desktop', 'service']) assert(options.moduleTypes.find((v: { id: string }) => v.id === type).languages.includes('Rust'));
    for (const type of ['driver', 'protocol', 'library', 'subsystem']) assert(!options.moduleTypes.find((v: { id: string }) => v.id === type).languages.includes('Rust'));
    const input = { name: 'Rust integration', description: 'Official SDK creator', language: 'Rust', template: 'terminal',
      vmId: null, guestFormats: [], optionsRevision: options.revision, requestId: randomUUID() };
    const created = await app.inject({ method: 'POST', url: '/api/projects', headers, payload: input });
    assert.equal(created.statusCode, 201, created.body);
    const project = created.json().project as Project;
    assert.equal(project.pins.rust?.id, 'sdk-0.64.66');
    assert.equal(project.pins.contract.revision, '50a38becae5765e0f85f6af6713fc72e00583952');
    const manifest = await readFile(join(directory, project.id, 'Workspace', 'module.R4MF'), 'utf8');
    assert.match(manifest, /LANGUAGE=Rust/);
    const lock = await readFile(join(directory, project.id, 'Workspace', 'Cargo.lock'), 'utf8');
    assert.match(lock, /r4os-sdk/);
    assert.doesNotMatch(await readFile(join(directory, project.id, 'Workspace', 'Build.ps1'), 'utf8'), /-ProjectPin/);
    assert(!existsSync(join(directory, project.id, 'r4os-project.json')));
    const retry = await app.inject({ method: 'POST', url: '/api/projects', headers, payload: input });
    assert.equal(retry.json().project.id, project.id);
    const saved = await app.inject({ method: 'PATCH', url: `/api/projects/${project.id}`, headers,
      payload: { revision: project.revision, name: 'Rust renamed' } });
    assert.equal(saved.statusCode, 200, saved.body);
    assert.deepEqual(saved.json().project.pins, project.pins);
    assert.equal(await readFile(join(directory, project.id, 'Workspace', 'module.R4MF'), 'utf8'), manifest);
    assert.equal(await readFile(join(directory, project.id, 'Workspace', 'Cargo.lock'), 'utf8'), lock);
  } finally { await app.close(); await rm(root, { recursive: true, force: true }); }
});
