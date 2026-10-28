import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm, access } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { request as httpRequest } from 'node:http';
import { createApp } from '../src/app.js';
import { projectStore } from '../src/modules/projects/store.js';

await test('binary uploads preserve original receipts and enforce owner, CSRF and bounded body checks', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-own-uploads-'));
  const projects = join(root, 'Projects'), providers = join(root, 'LLMProvider');
  const app = createApp({ projectDirectory: projects, providers: { directory: providers } });
  try {
    await projectStore(projects, { operation: 'list' });
    const pid = randomUUID(), provider = randomUUID();
    await mkdir(join(projects, pid, 'Workspace'), { recursive: true });
    await writeFile(join(projects, pid, 'Workspace/module.R4MF'), 'R4OS_MODULE_MANIFEST=2\n');
    await promisify(execFile)('/usr/bin/python3', ['-c', 'import sqlite3,sys\nwith sqlite3.connect(sys.argv[1]) as db:db.execute("INSERT INTO projects VALUES (?, ?, \'\', \'Zig\', \'terminal\', ?, NULL, \'{}\', \'now\', \'now\', 1, \'ready\')",(sys.argv[2],sys.argv[2],sys.argv[2]))', join(projects, 'Projects.sqlite'), pid]);
    await mkdir(join(providers, provider), { recursive: true });
    await writeFile(join(providers, 'providers.json'), JSON.stringify([{ id: provider, name: 'Own fixture', type: 'openai', connected: true }]));
    await writeFile(join(providers, provider, 'models_cache.json'), JSON.stringify({ models: [{ slug: 'fixture', visibility: 'list', supported_reasoning_levels: [{ effort: 'low' }] }] }));
    const imagePath = join(root, 'own.png');
    await promisify(execFile)('/usr/bin/python3', ['-c', 'from PIL import Image;import sys;Image.new("RGB",(3,2),"purple").save(sys.argv[1])', imagePath]);
    const imageBytes = await readFile(imagePath);
    const pdfPath = join(root, 'own.pdf');
    await promisify(execFile)('/usr/bin/python3', ['-c', 'import sys;from pathlib import Path;sys.path.insert(0,str(Path("scripts/agent-sessions").absolute()));from test_document_inputs import pdf;Path(sys.argv[1]).write_bytes(pdf("OWN_HTTP_PDF_TEXT"))', pdfPath]);
    const pdfBytes = await readFile(pdfPath);
    for (const scope of ['projects', 'skills']) {
      const auth = await app.inject(`/api/${scope}`);
      const headers = { cookie: String(auth.headers['set-cookie']).split(';')[0], 'x-csrf-token': auth.json().csrfToken };
      const id = scope === 'projects' ? pid : randomUUID();
      if (scope === 'skills') assert.equal((await app.inject({ method: 'POST', url: '/api/skills', headers, payload: { id, name: 'Own uploads' } })).statusCode, 200);
      const create = await app.inject({ method: 'POST', url: `/api/${scope}/${id}/sessions`, headers, payload: { requestId: randomUUID(), name: 'Own upload session', providerId: provider, model: 'fixture', effort: 'low' } });
      assert.equal(create.statusCode, 201, create.body);
      const sid = create.json().session.id, base = `/api/${scope}/${id}/sessions/${sid}/attachments`;
      const rid = randomUUID(), path = base + '/uploads/' + rid + '?name=source.txt&mediaType=text%2Fplain';
      const payload = Buffer.from('own source line 😀\n'.repeat(8000)), binary = { ...headers, 'content-type': 'application/octet-stream' };
      assert(payload.length > 72 * 1024);
      assert.equal((await app.inject({ method: 'POST', url: path, payload, headers: { 'content-type': 'application/octet-stream' } })).statusCode, 403);
      for (const extra of [{ origin: 'http://foreign.test' }, { host: 'foreign.test' }])
        assert.equal((await app.inject({ method: 'POST', url: path, payload, headers: { ...binary, ...extra } })).statusCode, 403);
      assert.equal((await app.inject({ method: 'POST', url: path, payload, headers: { ...headers, 'content-type': 'text/plain' } })).statusCode, 415);
      const uploaded = await app.inject({ method: 'POST', url: path, payload, headers: binary });
      assert.equal(uploaded.statusCode, 200, uploaded.body); assert.equal(uploaded.json().state, 'ready');
      assert.equal(uploaded.json().attachment.size, payload.length); assert(!uploaded.body.includes(root));
      const again = await app.inject({ method: 'POST', url: path, payload, headers: binary });
      assert.deepEqual(again.json(), uploaded.json());
      assert.equal((await app.inject({ method: 'POST', url: path, payload: Buffer.from('different'), headers: binary })).statusCode, 409);
      const read = await app.inject({ url: base + '/uploads/' + rid, headers }); assert.deepEqual(read.json(), uploaded.json());
      const listed = await app.inject({ url: base, headers }); assert.equal(listed.json().attachments.length, 1); assert.equal(listed.json().limits.maxFiles, 8);
      const imageUpload = await app.inject({ method: 'POST', url: base + '/uploads/' + randomUUID() + '?name=own.png', payload: imageBytes, headers: binary });
      assert.equal(imageUpload.statusCode, 200, imageUpload.body);
      assert.equal(imageUpload.json().attachment.mode, 'localImage'); assert.equal(imageUpload.json().attachment.width, 3);
      const preview = await app.inject({ url: base + '/' + imageUpload.json().attachment.id + '/preview', headers });
      assert.equal(preview.statusCode, 200, preview.body); assert.deepEqual(preview.rawPayload, imageBytes);
      const download = await app.inject({ url: base + '/' + uploaded.json().attachment.id + '/download', headers });
      assert.equal(download.statusCode, 200); assert.deepEqual(download.rawPayload, payload);
      assert.equal(download.headers['content-type'], 'application/octet-stream'); assert(String(download.headers['content-disposition']).startsWith('attachment;'));
      assert.equal((await app.inject(base + '/' + uploaded.json().attachment.id + '/download')).statusCode, 403);
      assert.equal(preview.headers['content-type'], 'image/png'); assert.equal(preview.headers['x-content-type-options'], 'nosniff');
      assert.equal((await app.inject(base + '/' + imageUpload.json().attachment.id + '/preview')).statusCode, 403);
      assert.equal((await app.inject({ url: base + '/' + uploaded.json().attachment.id + '/preview', headers })).statusCode, 415);
      assert.equal((await app.inject({ url: `/api/${scope}/${randomUUID()}/sessions/${sid}/attachments/${imageUpload.json().attachment.id}/preview`, headers })).statusCode, 404);
      const pdfUpload = await app.inject({ method: 'POST', url: base + '/uploads/' + randomUUID() + '?name=own.pdf', payload: pdfBytes, headers: binary });
      assert.equal(pdfUpload.statusCode, 200, pdfUpload.body);
      assert.equal(pdfUpload.json().attachment.mode, 'pdfText'); assert.equal(pdfUpload.json().attachment.pages, 1);
      assert.equal(pdfUpload.json().attachment.readable, true); assert(pdfUpload.json().attachment.extractedBytes > 0); assert(!pdfUpload.body.includes('_text'));
      const other = `/api/${scope}/${randomUUID()}/sessions/${sid}/attachments`;
      assert.equal((await app.inject({ url: other + '/uploads/' + rid, headers })).statusCode, 404);
      assert.equal((await app.inject({ method: 'DELETE', url: other + '/' + uploaded.json().attachment.id, headers })).statusCode, 404);
      assert.equal((await app.inject({ method: 'POST', url: base + '/uploads/' + randomUUID() + '?name=..%2Fescape', payload: Buffer.from('one'), headers: binary })).statusCode, 400);
      assert.equal((await app.inject({ method: 'POST', url: base + '/uploads/' + randomUUID() + '?name=bad.png', payload: Buffer.from('bad image'), headers: binary })).statusCode, 422);
      assert.equal((await app.inject({ method: 'POST', url: base + '/uploads/' + randomUUID() + '?name=large.txt', payload: Buffer.alloc(16 * 1024 * 1024 + 1), headers: binary })).statusCode, 413);
      if (scope === 'projects') {
        const origin = await app.listen({ host: '127.0.0.1', port: 0 });
        const pending = [randomUUID(), randomUUID()]; let seen = 0;
        let arrived!: () => void;
        const received = new Promise<void>(resolve => { arrived = resolve; });
        app.server.on('request', request => { if (pending.some(id => request.url?.includes(id)) && ++seen === 2) arrived(); });
        const held = pending.map(id => {
          const request = httpRequest(origin + base + '/uploads/' + id + '?name=interrupted.txt', { method: 'POST', headers: { ...binary, 'content-length': 100000 } });
          request.on('error', () => {}); request.write(Buffer.alloc(1000, 97)); return request;
        });
        await received;
        assert.equal((await app.inject({ method: 'POST', url: base + '/uploads/' + randomUUID() + '?name=busy.txt', payload: Buffer.from('one'), headers: binary })).statusCode, 429);
        held.forEach(request => request.destroy());
        for (const id of pending) assert.equal((await app.inject({ url: base + '/uploads/' + id, headers })).statusCode, 404);
      }
      const history = await app.inject({ url: `/api/${scope}/${id}/sessions/${sid}/history`, headers }); assert.deepEqual(history.json().items, []);
      assert.equal((await app.inject({ method: 'DELETE', url: base + '/' + uploaded.json().attachment.id, headers: { cookie: headers.cookie } })).statusCode, 403);
      assert.equal((await app.inject({ method: 'DELETE', url: base + '/' + uploaded.json().attachment.id, headers })).statusCode, 200);
      assert.equal((await app.inject({ url: base, headers })).json().attachments.length, 2);
      const ownerRoot = join(root, scope === 'skills' ? 'Skills' : 'Projects', id);
      await assert.rejects(access(join(ownerRoot, 'Sessions', sid, 'Attachments', uploaded.json().attachment.id)));
      assert.equal((await app.inject({ url: base + '/uploads/' + rid, headers })).json().state, 'removed');
    }
  } finally { await app.close(); await rm(root, { recursive: true, force: true }); }
});
