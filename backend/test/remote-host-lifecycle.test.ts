import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { createApp } from '../src/app.js';

await test('human-only Remote Host review is scoped, CSRF protected, exact and preserves original uncertainty', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-remote-lifecycle-api-'));
  const appRoot = fileURLToPath(new URL('../../', import.meta.url));
  const script = join(appRoot, 'scripts/remote-hosts/test_server.py');
  const broker = spawn('/usr/bin/python3', ['-B', script, root], { stdio: ['ignore', 'pipe', 'pipe'] });
  const previous = process.env.STUDIO_REMOTE_HOSTS_SOCKET; process.env.STUDIO_REMOTE_HOSTS_SOCKET = join(root, 'Runtime/host.sock');
  const app = createApp({ projectDirectory: join(root, 'Projects'), providers: { directory: join(root, 'LLMProvider') } });
  try {
    await new Promise<void>((resolve, reject) => { broker.stdout.once('data', () => resolve()); broker.once('error', reject); broker.once('exit', () => reject(new Error('Own broker exited before ready.'))); });
    const auth = await app.inject('/api/remote-hosts'); const headers = { cookie: String(auth.headers['set-cookie']).split(';')[0], 'x-csrf-token': auth.json().csrfToken };
    const host = (await app.inject({ method: 'POST', url: '/api/remote-hosts', headers, payload: { requestId: randomUUID(), name: 'Own lifecycle host', address: '127.0.0.1' } })).json();
    const projectId = randomUUID(), sessionId = randomUUID(), runId = randomUUID(), jobId = randomUUID(), requestId = randomUUID();
    execFileSync('/usr/bin/python3', ['-B', '-c', `
import sys,json,sqlite3
from pathlib import Path
from contextlib import closing
app=Path(sys.argv[1]);root=Path(sys.argv[2]);sys.path[:0]=[str(app/'scripts/remote-hosts'),str(app/'scripts/projects')]
from store import connect
from remote_binding import set_binding
from catalog import now
import job_store
project,session,run,job,request=sys.argv[3:8];host=json.loads(sys.argv[8])
with closing(connect(root/'Projects')) as db,db:
 db.execute("INSERT INTO projects VALUES (?,?,'','C','terminal',?,NULL,'{}','now','now',1,'ready')",(project,'Own review project','own_review_project'));set_binding(db,project,host['id'])
workspace=root/'Projects'/project/'Workspace';workspace.mkdir(parents=True);(workspace/'module.R4MF').write_text('R4OS_MODULE_MANIFEST=2\\n')
directory=workspace.parent/'Sessions';directory.mkdir()
with closing(sqlite3.connect(directory/'Sessions.sqlite')) as sessions:sessions.execute('CREATE TABLE runs(busy INTEGER)');sessions.commit()
(directory/'Sessions.sqlite').chmod(0o600)
stamp=now();payload={'schema':1,'operation':'command','actor':{'projectId':project},'host':host,'command':'OWN UNKNOWN FIXTURE','deadlineAt':stamp}
result={'stdout':'original bounded output','commandExitCode':None,'remoteProcessEndConfirmed':False,'message':'The original result is unconfirmed.'}
with job_store.connection(root/'Projects',project,create=True) as db,db:db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(job,request,'own-fingerprint',session,run,host['id'],'unknown','dispatch_possible',json.dumps(payload),json.dumps(result),stamp,stamp))
`, appRoot, root, projectId, sessionId, runId, jobId, requestId, JSON.stringify(host)]);
    const base = `/api/remote-hosts/${host.id}/jobs`, path = `${base}/${projectId}/${jobId}`;
    assert.equal((await app.inject(base)).statusCode, 403);
    const listed = await app.inject({ url: base, headers }); assert.equal(listed.statusCode, 200, listed.body); assert.equal(listed.json().jobs[0].id, jobId);
    const detail = (await app.inject({ url: path, headers })).json(); assert.equal(detail.state, 'unknown'); assert.equal(detail.result.stdout, 'original bounded output');
    assert.equal((await app.inject({ url: `/api/remote-hosts/${randomUUID()}/jobs/${projectId}/${jobId}`, headers })).statusCode, 403);
    const body = { requestId: randomUUID(), expectedUpdatedAt: detail.updatedAt, confirmUnknown: true };
    for (const invalid of [{}, { cookie: headers.cookie }, { ...headers, origin: 'https://foreign.invalid' }]) assert.equal((await app.inject({ method: 'POST', url: path + '/review', headers: invalid, payload: body })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: path + '/review', headers, payload: { ...body, expectedUpdatedAt: 'stale' } })).statusCode, 409);
    assert.equal((await app.inject({ method: 'PATCH', url: `/api/remote-hosts/${host.id}`, headers, payload: { requestId: randomUUID(), revision: host.revision, password: 'unapplied-own-password' } })).statusCode, 409);
    const reviewed = await app.inject({ method: 'POST', url: path + '/review', headers, payload: body }); assert.equal(reviewed.statusCode, 200, reviewed.body);
    assert.equal(reviewed.json().state, 'unknown_reviewed'); assert.equal(reviewed.json().originalOutcome, 'unknown'); assert.equal(reviewed.json().remoteProcessEndConfirmed, false);
    assert.deepEqual((await app.inject({ method: 'POST', url: path + '/review', headers, payload: body })).json(), reviewed.json());
    assert.deepEqual((await app.inject({ url: path + '/reviews/' + body.requestId, headers })).json(), reviewed.json());
    const kept = (await app.inject({ url: path, headers })).json(); assert.equal(kept.state, 'unknown_reviewed'); assert.deepEqual(kept.result, detail.result); assert.equal(kept.requestId, requestId);
    assert(!JSON.stringify(kept).includes('rosebud')); assert(!existsSync(join(root, 'Runtime/calls.json')));
  } finally {
    await app.close(); const exited = new Promise<void>((resolve) => broker.once('exit', () => resolve())); broker.kill('SIGTERM'); if (broker.exitCode === null) await exited;
    if (previous === undefined) delete process.env.STUDIO_REMOTE_HOSTS_SOCKET; else process.env.STUDIO_REMOTE_HOSTS_SOCKET = previous;
    await rm(root, { recursive: true, force: true });
  }
});
