import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { once } from 'node:events';
import { mkdtemp, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { randomUUID } from 'node:crypto';
import { createApp } from '../src/app.js';

await test('update plans require session and CSRF, bind artifact IDs and reject arbitrary paths', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'studio-update-plan-'));
  process.env.STUDIO_DEVELOPMENT_SOCKET = join(directory, 'host.sock');
  const received: Record<string, unknown>[] = [];
  const server = createServer(socket => {
    let pending = '';
    socket.on('data', chunk => {
      pending += chunk.toString();
      if (!pending.includes('\n')) return;
      received.push(JSON.parse(pending));
      socket.end(JSON.stringify({ result: { plan: { id: randomUUID() } } }) + '\n');
    });
  });
  server.listen(process.env.STUDIO_DEVELOPMENT_SOCKET); await once(server, 'listening');
  const app = createApp({ projectDirectory: join(directory, 'Projects'), providers: { directory: join(directory, 'LLMProvider') } });
  try {
    const auth = await app.inject('/api/projects');
    const headers = { cookie: String(auth.headers['set-cookie']).split(';')[0], 'x-csrf-token': auth.json().csrfToken };
    const project = randomUUID(), url = '/api/projects/' + project + '/update-packages/plans';
    const body = { requestId: randomUUID(), projectRevision: 1, configurationRevision: 1,
      metadata: { packageId: 'DEMO', packageVersion: '0.1.1', targetRelease: '0.87.14', title: 'Demo', description: 'Bound update' },
      artifactIds: [randomUUID()], requirements: [] };
    assert.equal((await app.inject({ method: 'POST', url, payload: body })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url, headers: { ...headers, origin: 'https://outside.test' }, payload: body })).statusCode, 403);
    const before = received.length;
    for (const payload of [{ ...body, binary: '/bin/sh' }, { ...body, source: '/etc/passwd' },
      { ...body, metadata: { ...body.metadata, binary: '/bin/sh' } }, { ...body, artifactIds: ['../../outside'] },
      { ...body, requirements: [{ kind: 'R4L', name: 'LIB', target: '/R4OS/LIBS/LIB.R4L', minVersion: '1.0.0', state: 'installed', extra: 'active' }] }]) {
      assert.equal((await app.inject({ method: 'POST', url, headers, payload })).statusCode, 400);
    }
    assert.equal(received.length, before);
    assert.equal((await app.inject({ method: 'POST', url, headers, payload: body })).statusCode, 201);
    assert.deepEqual(received.at(-1), { operation: 'update_plan', projectId: project, input: body });
    assert.equal((await app.inject({ method: 'GET', url: '/api/projects/' + project + '/update-packages', headers })).statusCode, 200);
    assert.deepEqual(received.at(-1), { operation: 'update_options', projectId: project });
    const buildUrl = '/api/projects/' + project + '/update-packages/builds';
    const build = { requestId: randomUUID(), projectRevision: 1, planId: randomUUID(), planSha256: 'a'.repeat(64) };
    assert.equal((await app.inject({ method: 'POST', url: buildUrl, payload: build })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: buildUrl, headers, payload: { ...build, binary: '/bin/sh' } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: buildUrl, headers, payload: { ...build, planId: '../outside' } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: buildUrl, headers, payload: build })).statusCode, 202);
    assert.deepEqual(received.at(-1), { operation: 'package', projectId: project, input: build });
    const packageId = randomUUID();
    assert.equal((await app.inject({ method: 'GET', url: '/api/projects/' + project + '/update-packages/artifacts/' + packageId, headers })).statusCode, 200);
    assert.deepEqual(received.at(-1), { operation: 'package_artifact', projectId: project, id: packageId });
    const probeUrl = '/api/projects/' + project + '/update-packages/probes';
    const probe = { requestId: randomUUID(), projectRevision: 2, packageArtifactId: packageId };
    assert.equal((await app.inject({ method: 'POST', url: probeUrl, payload: probe })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: probeUrl, headers, payload: { ...probe, command: 'SYSUPD COMMIT' } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: probeUrl, headers, payload: { ...probe, vmId: randomUUID() } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: probeUrl, headers, payload: probe })).statusCode, 202);
    assert.deepEqual(received.at(-1), { operation: 'update_probe', projectId: project, input: probe });
    const transferUrl = '/api/projects/' + project + '/update-packages/transfers';
    assert.equal((await app.inject({ method: 'POST', url: transferUrl, payload: probe })).statusCode, 403);
    for (const extra of [{ path: 'C:\\R4OS' }, { command: 'SYSUPD APPLY' }, { vmId: randomUUID() }]) {
      assert.equal((await app.inject({ method: 'POST', url: transferUrl, headers, payload: { ...probe, ...extra } })).statusCode, 400);
    }
    assert.equal((await app.inject({ method: 'POST', url: transferUrl, headers, payload: probe })).statusCode, 202);
    assert.deepEqual(received.at(-1), { operation: 'update_transfer', projectId: project, input: probe });

    const install = { requestId: randomUUID(), projectRevision: 2, transferJobIds: [randomUUID()] };
    const installUrl = '/api/projects/' + project + '/update-packages/installs';
    assert.equal((await app.inject({ method: 'POST', url: installUrl, payload: install })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: installUrl, headers, payload: { ...install, command: 'SYSUPD APPLY' } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: installUrl, headers, payload: install })).statusCode, 202);
    assert.deepEqual(received.at(-1), { operation: 'update_install', projectId: project, input: install });
    const commit = { requestId: randomUUID(), projectRevision: 2, updateId: randomUUID(), updateRevision: 1,
      batchId: '9007199254740993', targetRelease: '0.87.14', vmRevision: randomUUID(), confirmReboot: true };
    const commitUrl = '/api/projects/' + project + '/update-packages/commits';
    assert.equal((await app.inject({ method: 'POST', url: commitUrl, headers, payload: { ...commit, confirmReboot: false } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: commitUrl, headers, payload: commit })).statusCode, 202);
    assert.deepEqual(received.at(-1), { operation: 'update_commit', projectId: project, input: commit });
  } finally {
    await app.close(); await new Promise<void>(resolve => server.close(() => resolve()));
    delete process.env.STUDIO_DEVELOPMENT_SOCKET; await rm(directory, { recursive: true, force: true });
  }
});
