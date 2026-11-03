import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, readdir, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createApp } from '../src/app.js';
import type { SkillDetail } from '../../shared/skills.js';

await test('GitHub source changes preserve published resources, enforce revision/CSRF and replay only the original metadata result', async () => {
  const root = await mkdtemp(join(tmpdir(), 'skill-source-'));
  const app = createApp({ providers: { directory: join(root, 'LLMProvider') }, projectDirectory: join(root, 'Projects') });
  try {
    const list = await app.inject('/api/skills');
    const headers = { cookie: String(list.headers['set-cookie']).split(';')[0], 'x-csrf-token': list.json().csrfToken };
    const id = randomUUID();
    const call = (suffix: string, value: unknown, method: 'POST' | 'PUT' = 'POST') =>
      app.inject({ method, url: '/api/skills/' + id + suffix, payload: value, headers });
    const created = await app.inject({ method: 'POST', url: '/api/skills', headers, payload: { id, name: 'REA source' } });
    let detail = created.json<SkillDetail>();
    assert.equal(detail.source, null);
    const original = await readFile(join(root, 'Skills', id, 'Workspace/SKILL.md'));
    const input = { revision: detail.skill.revision, requestId: randomUUID(), source: { repository: 'https://github.com/Morluto/rea.git', ref: 'main' } };
    assert.equal((await app.inject({ method: 'PUT', url: '/api/skills/' + id + '/source', payload: input })).statusCode, 403);
    const changed = await call('/source', input, 'PUT');
    assert.equal(changed.statusCode, 200, changed.body);
    detail = changed.json();
    assert.equal(detail.skill.revision, 2);
    assert.equal(detail.source?.configuration.repository, 'https://github.com/morluto/rea');
    assert.equal(detail.source?.configuration.skillPath, '.agents/skills/reverse-engineer-anything');
    assert.equal(detail.source?.status, 'configured');
    assert.equal(detail.source?.active, null);
    assert.deepEqual(await readdir(join(root, 'Skills', id, 'Sources')), []);
    assert.deepEqual(await readdir(join(root, 'Skills', id, 'Runtimes')), []);
    assert.deepEqual(await readFile(join(root, 'Skills', id, 'Workspace/SKILL.md')), original);
    assert.deepEqual((await call('/source', input, 'PUT')).json(), detail);
    assert.equal((await call('/source', { ...input, source: null }, 'PUT')).statusCode, 409);
    assert.equal((await call('/source', { ...input, requestId: randomUUID() }, 'PUT')).statusCode, 409);
    for (const source of [
      { repository: 'https://github.com/morluto/rea', skillPath: '../private' },
      { repository: 'https://github.com/morluto/rea', ref: '--upload-pack=sh' },
      { repository: 'https://github.com/morluto/rea', ref: 'main~1' },
      { repository: 'https://github.com/morluto/rea', skillPath: '/etc' },
      { repository: 'https://github.com/morluto/rea?token=secret' },
      { repository: 'https://token@github.com/morluto/rea' },
      { repository: 'http://github.com/morluto/rea' },
      { repository: 'https://github.com.evil.test/morluto/rea' },
      { repository: 'file:///tmp/repo' },
      { repository: 'https://github.com/owner/other', recipe: 'rea' },
    ]) {
      const response = await call('/source', { revision: 2, requestId: randomUUID(), source }, 'PUT');
      assert.equal(response.statusCode, 400, response.body);
    }
    const detached = await call('/source', { revision: 2, requestId: randomUUID(), source: null }, 'PUT');
    assert.equal(detached.statusCode, 200, detached.body);
    assert.equal(detached.json<SkillDetail>().source, null);
    assert.equal(detached.json<SkillDetail>().skill.revision, 3);
    assert.deepEqual(await readFile(join(root, 'Skills', id, 'Workspace/SKILL.md')), original);
    const configured = await call('/source', { revision: 3, requestId: randomUUID(), source: { repository: 'https://github.com/morluto/rea' } }, 'PUT');
    detail = configured.json();
    const activation = { revision: detail.skill.revision, sourceRevision: detail.source!.revision,
      draftHash: detail.draftHash, requestId: randomUUID() };
    const queued = await call('/source/activate', activation);
    assert.equal(queued.statusCode, 202, queued.body);
    assert.equal(queued.json().phase, 'queued');
    assert.deepEqual((await call('/source/activate', activation)).json(), queued.json());
    const receipt = await app.inject({ url: '/api/skills/' + id + '/source/requests/' + activation.requestId, headers });
    assert.deepEqual(receipt.json(), queued.json());
    assert.equal((await call('/source/activate', { ...activation, requestId: randomUUID() })).statusCode, 423);
    assert.equal((await call('/source', { revision: detail.skill.revision, requestId: randomUUID(), source: null }, 'PUT')).statusCode, 423);
    assert.deepEqual(await readdir(join(root, 'Skills', id, 'Sources')), []);
  } finally {
    await app.close();
    await rm(root, { recursive: true, force: true });
  }
});
