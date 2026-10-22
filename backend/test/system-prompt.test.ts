import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createApp } from '../src/app.js';

await test('global system prompt persists, protects writes, detects conflicts and restores the shipped default', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-prompt-'));
  const options = { projectDirectory: join(root, 'Projects'), providers: { directory: join(root, 'Providers') } };
  let app = createApp(options);
  const url = '/api/settings/system-prompt';
  try {
    const first = await app.inject(url);
    assert.equal(first.statusCode, 200); assert.equal(first.headers['cache-control'], 'no-store');
    const initial = first.json();
    assert(initial.text.includes('R4OS Studio')); assert.equal(initial.text, initial.defaultText);
    assert.equal(initial.revision, 0); assert.equal(initial.isDefault, true);
    const headers = { cookie: String(first.headers['set-cookie']).split(';')[0], 'x-csrf-token': initial.csrfToken };
    assert(String(first.headers['set-cookie']).includes('Path=/api/settings; HttpOnly; SameSite=Strict'));
    const payload = { revision: 0, text: 'Global instructions\nGrüße 🦀' };
    assert.equal((await app.inject({ method: 'PATCH', url, payload })).statusCode, 403);
    assert.equal((await app.inject({ method: 'PATCH', url, payload, headers: { ...headers, origin: 'http://foreign.test' } })).statusCode, 403);
    assert.equal((await app.inject({ method: 'PATCH', url, payload, headers: { ...headers, host: 'foreign.test' } })).statusCode, 403);
    assert.equal((await app.inject({ method: 'PATCH', url, payload: { ...payload, projectId: 'ignored' }, headers })).statusCode, 400);
    for (const text of ['', '  ', '\u0000', '\ud800', '🦀'.repeat(9000)]) {
      assert.equal((await app.inject({ method: 'PATCH', url, payload: { revision: 0, text }, headers })).statusCode, 400);
    }
    const saved = await app.inject({ method: 'PATCH', url, payload, headers });
    assert.equal(saved.statusCode, 200); assert.equal(saved.json().text, payload.text);
    assert.equal(saved.json().revision, 1); assert.equal(saved.json().isDefault, false);
    assert.equal((await app.inject({ method: 'PATCH', url, payload, headers })).json().revision, 1);
    assert.equal((await app.inject({ method: 'PATCH', url, payload: { ...payload, text: 'Stale overwrite' }, headers })).statusCode, 409);
    await app.close(); app = createApp(options);
    const restored = await app.inject(url); assert.equal(restored.json().text, payload.text);
    const nextHeaders = { cookie: String(restored.headers['set-cookie']).split(';')[0], 'x-csrf-token': restored.json().csrfToken };
    assert.equal((await app.inject({ method: 'POST', url: url + '/reset', payload: { revision: 0 }, headers: nextHeaders })).statusCode, 409);
    const reset = await app.inject({ method: 'POST', url: url + '/reset', payload: { revision: 1 }, headers: nextHeaders });
    assert.equal(reset.statusCode, 200); assert.equal(reset.json().text, initial.text);
    assert.equal(reset.json().isDefault, true); assert.equal(reset.json().revision, 2);
    assert.equal((await app.inject({ method: 'POST', url: url + '/reset', payload: { revision: 1 }, headers: nextHeaders })).json().revision, 2);
    const storage = join(root, 'Projects/.studio/Settings.sqlite');
    await writeFile(storage, 'corrupt prompt data');
    assert.equal((await app.inject(url)).statusCode, 503);
    assert.equal(await readFile(storage, 'utf8'), 'corrupt prompt data');
  } finally { await app.close(); await rm(root, { recursive: true, force: true }); }
});
