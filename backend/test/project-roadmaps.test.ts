import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createApp } from '../src/app.js';

await test('project roadmap API uses project sessions, strict mutations, receipts and parent-scoped reads', async () => {
  const temporary = await mkdtemp(join(tmpdir(), 'studio-roadmap-api-'));
  const directory = join(temporary, 'Projects'), id = randomUUID(), other = randomUUID();
  const app = createApp({ projectDirectory: directory, providers: { directory: join(temporary, 'LLMProvider') } });
  try {
    const session = await app.inject('/api/projects');
    const headers = { cookie: String(session.headers['set-cookie']).split(';')[0], 'x-csrf-token': session.json().csrfToken };
    for (const identity of [id, other]) {
      await mkdir(join(directory, identity, 'Workspace'), { recursive: true });
      await writeFile(join(directory, identity, 'Workspace/module.R4MF'), 'Own isolated roadmap fixture\n');
    }
    await promisify(execFile)('/usr/bin/python3', ['-B', '-c', `
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
 for i,identity in enumerate(sys.argv[2:]):
  db.execute("INSERT INTO projects(id,name,description,language,template,module_name,pins,created_at,updated_at,state) VALUES(?,?,'','Zig','desktop',?,'{}','now','now','ready')",(identity,'Fixture '+str(i),'FIXTURE'+str(i)))
`, join(directory, 'Projects.sqlite'), id, other]);
    const url = `/api/projects/${id}/roadmap`;
    assert.equal((await app.inject(url)).statusCode, 403);
    const missing = await app.inject({ url, headers });
    assert.equal(missing.statusCode, 200, missing.body);
    assert.equal(missing.json().exists, false);
    const input = { requestId: randomUUID() };
    for (const invalidHeaders of [{}, { cookie: headers.cookie }, { ...headers, origin: 'http://foreign.test' },
      { ...headers, host: 'foreign.test' }, { ...headers, 'sec-fetch-site': 'cross-site' }]) {
      assert.equal((await app.inject({ method: 'POST', url: url + '/initialize', headers: invalidHeaders, payload: input })).statusCode, 403);
    }
    assert.equal((await app.inject({ method: 'POST', url: url + '/initialize', headers, payload: { ...input, path: '/' } })).statusCode, 400);
    const initialized = await app.inject({ method: 'POST', url: url + '/initialize', headers, payload: input });
    assert.equal(initialized.statusCode, 200, initialized.body);
    const root = initialized.json();
    assert.deepEqual((await app.inject({ url: url + '/revision', headers })).json(), { revision: root.revision, currentVersionId: root.currentVersionId });
    assert.equal((await app.inject(url + '/revision')).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: url + '/initialize', headers, payload: input })).body, initialized.body);
    const body = { requestId: randomUUID(), expectedRevision: root.revision, currentVersionId: root.currentVersionId,
      target: { kind: 'version', id: root.currentVersionId }, action: 'append_notes', input: { notes: 'Retained' } };
    for (const invalid of [{ ...body, path: '/' }, { ...body, expectedRevision: '1' }, { ...body, input: { notes: 42 } },
      { ...body, target: { ...body.target, projectId: other } }]) {
      assert.equal((await app.inject({ method: 'POST', url: url + '/mutations', headers, payload: invalid })).statusCode, 400);
    }
    const updated = await app.inject({ method: 'POST', url: url + '/mutations', headers, payload: body });
    assert.equal(updated.statusCode, 200, updated.body);
    assert.equal(updated.json().entity.notes, 'Retained');
    assert.equal((await app.inject({ method: 'POST', url: url + '/mutations', headers, payload: body })).body, updated.body);
    assert.equal((await app.inject({ method: 'POST', url: url + '/mutations', headers, payload: { ...body, requestId: randomUUID() } })).statusCode, 409);
    const current = await app.inject({ url: url + '/current', headers });
    assert.equal(current.json().entity.id, root.currentVersionId);
    assert.equal((await app.inject({ url: url + '/versions/' + root.currentVersionId + '/notes', headers })).json().notes, 'Retained');
    const firstPage = await app.inject({ url: url + '/versions?limit=1', headers });
    assert.equal(firstPage.json().items.length, 1);
    assert.equal((await app.inject({ url: url + '/versions?limit=21', headers })).statusCode, 400);
    const own = await app.inject({ method: 'POST', url: `/api/projects/${other}/roadmap/initialize`, headers, payload: { requestId: randomUUID() } });
    assert.equal(own.statusCode, 200, own.body);
    assert.equal((await app.inject({ url: `/api/projects/${other}/roadmap/versions/${root.currentVersionId}`, headers })).statusCode, 404);
    assert.equal((await app.inject({ url, headers: { ...headers, origin: 'http://foreign.test' } })).statusCode, 403);
    const unicode = 'é🙂'.repeat(5401);
    const large = await app.inject({ method: 'POST', url: url + '/mutations', headers, payload: {
      ...body, requestId: randomUUID(), expectedRevision: updated.json().revision, action: 'update',
      input: { notes: unicode, vision: unicode },
    } });
    assert.equal(large.statusCode, 200, large.body);
    assert.equal(large.json().entity.notes, unicode);
    assert.equal(large.json().entity.vision, unicode);
    const binding = (await app.inject({ url: url + '/revision', headers })).json();
    const archiveInput = { requestId: randomUUID(), versionId: root.currentVersionId,
      expectedRevision: binding.revision, currentVersionId: binding.currentVersionId };
    assert.equal((await app.inject({ method: 'POST', url: url + '/exports', payload: archiveInput })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: url + '/exports', headers, payload: { ...archiveInput, path: '/' } })).statusCode, 400);
    const exported = await app.inject({ method: 'POST', url: url + '/exports', headers, payload: archiveInput });
    assert.equal(exported.statusCode, 200, exported.body);
    assert.equal(exported.json().filename, '0.1.X.txt');
    assert.equal((await app.inject({ method: 'POST', url: url + '/exports', headers, payload: archiveInput })).body, exported.body);
    const downloadPath = url + '/exports/' + exported.json().id + '/content';
    assert.equal((await app.inject(downloadPath)).statusCode, 403);
    const downloaded = await app.inject({ url: downloadPath, headers });
    assert.equal(downloaded.statusCode, 200, downloaded.body);
    assert.equal(downloaded.headers['content-disposition'], 'attachment; filename="0.1.X.txt"');
    assert.equal(downloaded.headers['x-content-sha256'], exported.json().sha256);
    assert.equal(Buffer.byteLength(downloaded.body), exported.json().byteLength);
    assert.equal(createHash('sha256').update(downloaded.rawPayload).digest('hex'), exported.json().sha256);
    assert(downloaded.body.includes(unicode));
    assert.deepEqual((await app.inject({ url: url + '/revision', headers })).json(), binding);
  } finally {
    await app.close();
    await rm(temporary, { recursive: true, force: true });
  }
});
