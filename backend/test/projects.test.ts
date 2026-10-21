import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createApp } from '../src/app.js';

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
    assert.equal((await app.inject({ method: 'POST', url: '/api/projects', payload: {} })).statusCode, 404);

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
