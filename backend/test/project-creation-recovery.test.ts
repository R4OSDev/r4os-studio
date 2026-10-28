import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createApp } from '../src/app.js';

await test('creation readback distinguishes deleted, incomplete and existing originals without replay', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-create-recovery-'));
  const directory = join(root, 'Projects');
  const app = createApp({ projectDirectory: directory, providers: { directory: join(root, 'Providers') } });
  const deleted = randomUUID(), complete = randomUUID(), pending = randomUUID(), missing = randomUUID();
  const project = randomUUID(), draft = randomUUID();
  const python = promisify(execFile);
  try {
    const session = await app.inject('/api/projects');
    const headers = { cookie: String(session.headers['set-cookie']).split(';')[0] };
    await python('/usr/bin/python3', ['-c', `
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
 db.execute('INSERT INTO retired_project_requests VALUES (?,?)',(sys.argv[2],'a'*64))
 for ident,state in [(sys.argv[5],'ready'),(sys.argv[6],'ready')]:
  db.execute("INSERT INTO projects VALUES (?, 'Fixture','','Zig','terminal',?,NULL,'{}','now','now',1,?)",(ident,'FIXTURE_'+ident[:8].upper(),state))
 for request,ident,phase in [(sys.argv[3],sys.argv[5],'complete'),(sys.argv[4],sys.argv[6],'reserved')]:
  db.execute("INSERT INTO requests VALUES (?,?,?,?,'{}',NULL)",(request,'b'*64,ident,phase))
`, join(directory, 'Projects.sqlite'), deleted, complete, pending, project, draft]);
    const dump = async () => (await python('/usr/bin/python3', ['-c',
      'import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); print("\\n".join(db.iterdump())); db.close()', join(directory, 'Projects.sqlite')])).stdout;
    const before = await dump();
    for (const [id, state] of [[deleted, 'deleted'], [complete, 'complete'], [pending, 'pending'], [missing, 'missing']]) {
      const response = await app.inject({ url: '/api/projects/creation-requests/' + id, headers });
      assert.equal(response.statusCode, 200);
      assert.equal(response.headers['cache-control'], 'no-store');
      assert.equal(response.json().requestId, id);
      assert.equal(response.json().state, state);
      if (state === 'complete') assert.equal(response.json().project.id, project);
      else assert.equal(response.json().project, undefined);
      assert.equal(response.json().request_hash, undefined);
    }
    assert.equal(await dump(), before);
    await python('/usr/bin/python3', ['-c',
      "import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); db.execute(\"INSERT INTO project_deletions VALUES (?,1,'{}')\",(sys.argv[2],)); db.commit(); db.close()",
      join(directory, 'Projects.sqlite'), project]);
    const deletion = await app.inject({ url: '/api/projects/creation-requests/' + complete, headers });
    assert.equal(deletion.json().state, 'deleting');
    assert.equal(deletion.json().project, undefined);
    assert.equal((await app.inject({ url: '/api/projects/creation-requests/not-a-uuid', headers })).statusCode, 400);
    assert.equal((await app.inject({ url: '/api/projects/creation-requests/' + deleted, headers: { ...headers, origin: 'http://foreign.test' } })).statusCode, 403);
  } finally {
    await app.close();
    await rm(root, { recursive: true, force: true });
  }
});
