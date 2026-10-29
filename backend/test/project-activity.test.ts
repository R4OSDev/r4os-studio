import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createApp } from '../src/app.js';

await test('project activity uses one protected aggregate read and preserves unavailable hosts', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-project-activity-')), socket = join(root, 'host.sock');
  const previous = process.env.STUDIO_AGENTS_SOCKET; process.env.STUDIO_AGENTS_SOCKET = socket;
  const calls: unknown[] = [], active = [randomUUID(), randomUUID()]; let available = true;
  const server = createServer(client => {
    let raw = ''; client.on('data', chunk => {
      raw += chunk; if (!raw.includes('\n')) return; calls.push(JSON.parse(raw));
      client.end(JSON.stringify(available ? { result: { schema: 1, activeProjectIds: active, checkedAt: 'now', validForMs: 10000 } }
        : { error: 'Unsupported operation.', code: 503 }) + '\n');
    });
  });
  await new Promise<void>(resolve => server.listen(socket, resolve));
  const app = createApp({ projectDirectory: join(root, 'Projects'), providers: { directory: join(root, 'LLMProvider') } });
  try {
    assert.equal((await app.inject('/api/projects/session-activity')).statusCode,403); assert.equal(calls.length,0);
    const auth = await app.inject('/api/projects/'); assert.equal(auth.statusCode,200,auth.body);
    const headers = { cookie: String(auth.headers['set-cookie']).split(';')[0] };
    for (const extra of [{origin:'http://foreign.invalid'},{host:'foreign.invalid'},{'sec-fetch-site':'cross-site'}]) {
      assert.equal((await app.inject({url:'/api/projects/session-activity',headers:{...headers,...extra}})).statusCode,403);
    }
    const result = await app.inject({url:'/api/projects/session-activity',headers});
    assert.equal(result.statusCode,200,result.body); assert.deepEqual(result.json().activeProjectIds,active);
    assert.equal(result.headers['cache-control'],'no-store'); assert.deepEqual(calls,[{operation:'project_activity'}]);
    available=false;
    assert.equal((await app.inject({url:'/api/projects/session-activity',headers})).statusCode,503);
    assert.equal((await app.inject({url:'/api/projects/',headers})).statusCode,200);
  } finally {
    await app.close();await new Promise<void>(resolve => server.close(() => resolve()));
    if(previous===undefined)delete process.env.STUDIO_AGENTS_SOCKET;else process.env.STUDIO_AGENTS_SOCKET=previous;
    await rm(root,{recursive:true,force:true});
  }
});
