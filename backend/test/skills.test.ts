import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, writeFile, symlink, stat, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { randomUUID } from 'node:crypto';
import { createApp } from '../src/app.js';
import type { SkillDetail } from '../../shared/skills.js';

await test('global skill drafts validate and atomically publish complete pinned revisions without executing scripts', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-skills-'));
  const options = { providers: { directory: join(root, 'LLMProvider') }, projectDirectory: join(root, 'Projects') };
  let app = createApp(options);
  try {
    const first = await app.inject('/api/skills'); assert.equal(first.statusCode, 200); assert.deepEqual(first.json().skills, []);
    assert.equal(first.headers['cache-control'], 'no-store');
    let headers = { cookie: String(first.headers['set-cookie']).split(';')[0], 'x-csrf-token': first.json().csrfToken };
    assert(String(first.headers['set-cookie']).includes('Path=/api/skills; HttpOnly; SameSite=Strict'));
    const id = randomUUID();
    assert.equal((await app.inject({ method: 'POST', url: '/api/skills', payload: { id, name: 'Reports' } })).statusCode, 403);
    for (const extra of [{ host: 'foreign.test' }, { origin: 'http://foreign.test' }, { 'sec-fetch-site': 'cross-site' }]) {
      assert.equal((await app.inject({ method: 'POST', url: '/api/skills', payload: { id, name: 'Reports' }, headers: { ...headers, ...extra } })).statusCode, 403);
    }
    const send = (suffix: string, payload: unknown, method: 'POST' | 'PUT' | 'PATCH' | 'DELETE' = 'POST') => app.inject({ method, url: '/api/skills' + suffix, payload, headers });
    let current = (await send('', { id, name: 'Reports' })).json<SkillDetail>();
    assert.equal(current.skill.id, id); assert.equal(current.skill.activeRevision, 0);
    assert.equal((await send('', { id, name: 'Reports' })).json<SkillDetail>().skill.id, id);
    assert.equal((await send('/' + id + '/validate', {})).json().valid, false);
    async function put(path: string, content: string, executable = false) {
      const expected = current.files.find(f => f.path === path)?.sha256 ?? null;
      const response = await send('/' + id + '/file', { path, content, encoding: 'utf8', sha256: expected, executable }, 'PUT');
      assert.equal(response.statusCode, 200, response.body); current = response.json<SkillDetail>();
    }
    const skill = '---\nname: report-helper\ndescription: >-\n  Generate concise project\n  reports from supplied data.\nmetadata:\n  short-description: Reports\nallowed-tools: [exec_command]\n---\n\n# Reports\nUse [the schema](references/schema.md) for requested reports.\n';
    await put('SKILL.md', skill);
    await put('references/schema.md', '# Schema\nUse the user-provided fields.\n');
    await put('scripts/report.py', 'raise RuntimeError("This fixture must never execute during save")\n', true);
    const validation = await send('/' + id + '/validate', {}); assert.equal(validation.json().valid, true, validation.body);
    assert.equal(validation.json().metadata.description, 'Generate concise project reports from supplied data.');
    const save = { revision: current.skill.revision, draftHash: current.draftHash, requestId: randomUUID() };
    const published = await send('/' + id + '/save', save); assert.equal(published.statusCode, 200, published.body);
    assert.equal(published.json().saved, true); current = published.json();
    assert.equal(current.skill.activeRevision, 1); assert.equal(current.skill.formatName, 'report-helper');
    const immutable = join(root, 'Skills', id, 'Revisions', current.skill.activeHash!, 'Workspace/SKILL.md');
    assert.equal(await readFile(immutable, 'utf8'), skill);
    assert.equal((await send('/' + id + '/save', save)).json().skill.activeRevision, 1);
    const staleHash = current.files.find(f => f.path === 'SKILL.md')!.sha256;
    await put('SKILL.md', 'incomplete draft');
    const invalid = await send('/' + id + '/save', { revision: current.skill.revision, draftHash: current.draftHash, requestId: randomUUID() });
    assert.equal(invalid.json().saved, false); assert.equal(invalid.json().skill.activeRevision, 1);
    assert.equal(await readFile(immutable, 'utf8'), skill);
    assert.equal((await send('/' + id + '/file', { path: 'SKILL.md', content: skill, encoding: 'utf8', sha256: staleHash, executable: false }, 'PUT')).statusCode, 409);
    assert.equal((await send('/' + id + '/save', { revision: current.skill.revision, draftHash: save.draftHash, requestId: randomUUID() })).statusCode, 409);
    await put('SKILL.md', skill.replace('report-helper', 'report-assistant'));
    const renamed = await send('/' + id, { revision: current.skill.revision, name: 'New display name' }, 'PATCH');
    assert.equal(renamed.statusCode, 200); current = renamed.json(); assert.equal(current.skill.id, id);
    const second = await send('/' + id + '/save', { revision: current.skill.revision, draftHash: current.draftHash, requestId: randomUUID() });
    assert.equal(second.json().skill.activeRevision, 2); assert.equal(second.json().skill.id, id);
    assert.equal(await readFile(immutable, 'utf8'), skill);
    assert.equal((await stat(join(root, 'Skills/Skills.sqlite'))).mode & 0o777, 0o600);
    await app.close(); app = createApp(options);
    const restored = await app.inject('/api/skills'); assert.equal(restored.json().skills[0].activeRevision, 2);
    headers = { cookie: String(restored.headers['set-cookie']).split(';')[0], 'x-csrf-token': restored.json().csrfToken };
    const state = await app.inject({ url: '/api/skills/' + id, headers }); assert.equal(state.json().skill.name, 'New display name');
    assert(!Object.hasOwn(state.json().skill, 'allowedTools'));
    await writeFile(join(root, 'Skills/Skills.sqlite'), 'corrupt catalog');
    assert.equal((await app.inject('/api/skills')).statusCode, 503);
    assert.equal(await readFile(join(root, 'Skills/Skills.sqlite'), 'utf8'), 'corrupt catalog');
  } finally { await app.close(); await rm(root, { recursive: true, force: true }); }
});

await test('skill file boundary rejects traversal, links, oversized files and stale concurrent writes', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-skill-boundary-'));
  const app = createApp({ providers: { directory: join(root, 'LLMProvider') }, projectDirectory: join(root, 'Projects') });
  try {
    const first = await app.inject('/api/skills');
    const headers = { cookie: String(first.headers['set-cookie']).split(';')[0], 'x-csrf-token': first.json().csrfToken };
    const id = randomUUID();
    const created = await app.inject({ method: 'POST', url: '/api/skills', payload: { id, name: 'Boundary' }, headers });
    assert.equal(created.statusCode, 200, created.body);
    const hash = created.json<SkillDetail>().files[0].sha256;
    const put = (path: string, content: string, sha256: string | null = null) => app.inject({ method: 'PUT', url: '/api/skills/' + id + '/file', headers, payload: { path, content, sha256, encoding: 'utf8', executable: false } });
    for (const path of ['../secret', '/etc/passwd', 'scripts/../../secret', '.codex/config.toml', 'scripts//bad.py', 'scripts/../SKILL.md', 'scripts/\\bad']) assert.equal((await put(path, 'bad')).statusCode, 400);
    assert.equal((await put('scripts/large.py', 'x'.repeat(1024 * 1024 + 1))).statusCode, 400);
    const changed = await Promise.all([put('SKILL.md', 'draft A', hash), put('SKILL.md', 'draft B', hash)]);
    assert.deepEqual(changed.map(v => v.statusCode).sort(), [200, 409]);
    const secret = join(root, 'outside.txt'); await writeFile(secret, 'outside preserved');
    await mkdir(join(root, 'Skills', id, 'Workspace/scripts'));
    await symlink(secret, join(root, 'Skills', id, 'Workspace/scripts/escape.py'));
    assert.equal((await app.inject({ url: '/api/skills/' + id, headers })).statusCode, 400);
    assert.equal(await readFile(secret, 'utf8'), 'outside preserved');
  } finally { await app.close(); await rm(root, { recursive: true, force: true }); }
});
