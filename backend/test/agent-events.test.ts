import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { get } from 'node:http';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createApp } from '../src/app.js';

await test('a paused event reader stays bounded and replays the next event without starting or stopping a run', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-slow-events-')), socket = join(root, 'host.sock');
  const previous = process.env.STUDIO_AGENTS_SOCKET; process.env.STUDIO_AGENTS_SOCKET = socket;
  const calls: string[] = [], project = randomUUID(), session = randomUUID();
  const server = createServer((client) => {
    let raw = ''; client.setEncoding('utf8'); client.on('data', (part) => {
      raw += part; if (!raw.includes('\n')) return;
      const input = JSON.parse(raw); calls.push(input.operation);
      client.end(JSON.stringify({ result: { session: {}, events: [7,8].filter((seq) => seq > input.after).map((seq) => ({ seq, runId: null, kind: 'item', payload: { id: String(seq), text: 'x'.repeat(196608) } })) } })+'\n');
    });
  });
  await new Promise<void>((resolve) => server.listen(socket, resolve));
  const app = createApp({ projectDirectory: join(root, 'Projects'), providers: { directory: join(root, 'Providers') } });
  try {
    const auth = await app.inject('/api/projects'), cookie = String(auth.headers['set-cookie']).split(';')[0];
    await app.listen({ host: '127.0.0.1', port: 0 }); const address = app.server.address(); assert(address && typeof address !== 'string');
    const origin = `http://127.0.0.1:${address.port}`, path = `/api/projects/${project}/sessions/${session}/events`;
    const slow = await new Promise<import('node:http').IncomingMessage>((resolve, reject) => { get(origin+path+'?after=6', { headers: { cookie } }, resolve).once('error', reject); });
    slow.pause(); let first = ''; slow.setEncoding('utf8'); slow.on('data', (part) => { first += part; });
    await new Promise((resolve) => setTimeout(resolve, 100));
    const healthy = await fetch(origin+'/api/health', { signal: AbortSignal.timeout(2000) }); assert.equal(healthy.status, 200);
    const ended = new Promise<void>((resolve,reject) => { slow.once('end',resolve); slow.once('error',reject); });
    slow.resume(); await ended;
    assert(first.includes('id: 7\n')); assert(!first.includes('id: 8\n')); assert(Buffer.byteLength(first) < 262144);
    const replay = await fetch(origin+path+'?after=7', { headers: { cookie } });
    const second = await replay.text(); assert(second.includes('id: 8\n')); assert(!second.includes('id: 7\n'));
    assert(Buffer.byteLength(second) < 262144); assert(calls.length >= 2); assert(calls.every((c) => c === 'events'));
  } finally {
    await app.close(); await new Promise<void>((resolve) => server.close(() => resolve()));
    if (previous === undefined) delete process.env.STUDIO_AGENTS_SOCKET; else process.env.STUDIO_AGENTS_SOCKET = previous;
    await rm(root, { recursive: true, force: true });
  }
});
