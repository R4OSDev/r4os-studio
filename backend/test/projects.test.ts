import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createApp } from '../src/app.js';

await test('projects list only direct local folders and reject foreign origins without exposing filesystem errors', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-projects-'));
  const directory = join(root, 'Projects');
  const app = createApp({ projectDirectory: directory, providers: { directory: join(root, 'LLMProvider') } });
  try {
    assert.deepEqual((await app.inject('/api/projects')).json(), { projects: [] });
    await mkdir(join(directory, 'Project 10'), { recursive: true });
    await mkdir(join(directory, 'Project 2', 'Source'), { recursive: true });
    await mkdir(join(root, 'Outside'));
    await symlink(join(root, 'Outside'), join(directory, 'Linked project'));
    await writeFile(join(directory, 'notes.txt'), 'Not a project');

    const response = await app.inject('/api/projects');
    assert.equal(response.statusCode, 200);
    assert.equal(response.headers['cache-control'], 'no-store');
    assert.deepEqual(response.json(), { projects: [
      { id: 'Project 2', name: 'Project 2' }, { id: 'Project 10', name: 'Project 10' },
    ] });
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
