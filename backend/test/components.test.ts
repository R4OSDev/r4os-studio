import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { once } from 'node:events';
import { mkdtemp, rm, mkdir, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createApp } from '../src/app.js';
import { activeTool } from '../src/modules/components/tools.js';

await test('component downloads/defaults require session and CSRF and accept only fixed component identities', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'studio-components-'));
  process.env.STUDIO_COMPONENT_SOCKET = join(directory, 'host.sock');
  const received: Record<string, unknown>[] = [];
  const server = createServer((socket) => {
    let pending = '';
    socket.on('data', (chunk) => {
      pending += chunk.toString();
      if (!pending.includes('\n')) return;
      received.push(JSON.parse(pending));
      socket.end(JSON.stringify({ status: { enabled: true, components: {}, job: null, message: 'Ready' } }) + '\n');
    });
  });
  server.listen(process.env.STUDIO_COMPONENT_SOCKET); await once(server, 'listening');
  const app = createApp();
  try {
    const result = await app.inject('/api/updates/components');
    const headers = { cookie: String(result.headers['set-cookie']).split(';')[0], 'x-csrf-token': result.json().csrfToken };
    assert.equal((await app.inject({ method: 'POST', url: '/api/updates/components/download', payload: { kind: 'zig', id: '0.16.0' } })).statusCode, 403);
    const before = received.length;
    for (const payload of [{ kind: 'shell', id: '0.16.0' }, { kind: 'zig', id: '../../outside' }, { kind: 'zig', id: '0.16.0', url: 'https://evil.test' }]) {
      assert.equal((await app.inject({ method: 'POST', url: '/api/updates/components/download', headers, payload })).statusCode, 400);
    }
    assert.equal(received.length, before);
    assert.equal((await app.inject({ method: 'POST', url: '/api/updates/components/default', headers: { ...headers, origin: 'https://evil.test' }, payload: { kind: 'zig', id: '0.16.0' } })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: '/api/updates/components/default', headers, payload: { kind: 'zig', id: '0.16.0' } })).statusCode, 200);
    assert.deepEqual(received.at(-1), { command: 'default', kind: 'zig', id: '0.16.0' });
  } finally {
    await app.close(); await new Promise<void>((resolve) => server.close(() => resolve()));
    delete process.env.STUDIO_COMPONENT_SOCKET; await rm(directory, { recursive: true, force: true });
  }
});

await test('active tools reject changed binaries and paths outside the versioned tool directory', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'studio-tools-'));
  const previous = process.env.STUDIO_R4OS_DIR;
  process.env.STUDIO_R4OS_DIR = directory;
  try {
    await mkdir(join(directory, 'Profiles'));
    await mkdir(join(directory, 'Toolchains/Codex/0.123.0'), { recursive: true });
    const binary = join(directory, 'Toolchains/Codex/0.123.0/codex');
    const source = '#!/bin/sh\nexit 0\n';
    await writeFile(binary, source, { mode: 0o700 });
    const record = { id: '0.123.0', version: '0.123.0', binary, binarySha256: createHash('sha256').update(source).digest('hex') };
    const profile = join(directory, 'Profiles/versions.json');
    await writeFile(profile, JSON.stringify({ schema: 1, defaults: { codex: record } }));
    assert.equal((await activeTool('codex')).binary, binary);
    await writeFile(binary, '#!/bin/sh\nexit 1\n');
    await assert.rejects(activeTool('codex'), /checksum changed/);
    await writeFile(profile, JSON.stringify({ schema: 1, defaults: { codex: { ...record, binary: '/bin/sh' } } }));
    await assert.rejects(activeTool('codex'), /Invalid active tool path/);
    // The original service template set this fallback path explicitly. It must
    // now follow the managed profile, including rejection of invalid choices.
    const originalOverride = process.env.CODEX_BINARY;
    try {
      for (const [override, available] of [['/opt/r4os-studio/bin/codex', false], ['/usr/bin/true', true]] as const) {
        process.env.CODEX_BINARY = override;
        const app = createApp({ providers: { directory: join(directory, 'providers') } });
        try { assert.equal((await app.inject('/api/providers')).json().signInAvailable, available); }
        finally { await app.close(); }
      }
    } finally {
      if (originalOverride === undefined) delete process.env.CODEX_BINARY; else process.env.CODEX_BINARY = originalOverride;
    }

  } finally {
    if (previous === undefined) delete process.env.STUDIO_R4OS_DIR; else process.env.STUDIO_R4OS_DIR = previous;
    await rm(directory, { recursive: true, force: true });
  }
});
