import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID,createHash } from 'node:crypto';
import {createServer} from 'node:net';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import { createApp } from '../src/app.js';
import { projectStore } from '../src/modules/projects/store.js';
import { componentRoot } from '../src/modules/components/tools.js';

await test('sessions preserve idempotency, settings, tool permissions and project isolation',
  { skip: !existsSync(join(componentRoot(), 'Toolchains/Codex/0.163.0/codex')) && 'Install the qualified Codex runtime.' }, async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-sessions-'));
  const directory = join(root, 'Projects'), providers = join(root, 'LLMProvider');
  const ids = [randomUUID(), randomUUID()], provider = randomUUID();
  const app = createApp({ projectDirectory: directory, providers: { directory: providers } });
  try {
    await projectStore(directory, { operation: 'list' });
    for (const id of ids) {
      await mkdir(join(directory, id, 'Workspace'), { recursive: true });
      await writeFile(join(directory, id, 'Workspace/module.R4MF'), 'R4OS_MODULE_MANIFEST=2\n');
    }
    await promisify(execFile)('/usr/bin/python3', ['-c', `
import sqlite3,sys,json
with sqlite3.connect(sys.argv[1]) as db:
 for ident in json.loads(sys.argv[2]):
  db.execute("INSERT INTO projects VALUES (?,?, '', 'Zig','terminal',?,NULL,'{}','now','now',1,'ready')",(ident,ident,ident))
`, join(directory, 'Projects.sqlite'), JSON.stringify(ids)]);
    await mkdir(join(providers, provider), { recursive: true });
    await writeFile(join(providers, 'providers.json'), JSON.stringify([{ id: provider, name: 'Fixture provider', type: 'openai', connected: true }]));
    await writeFile(join(providers, provider, 'models_cache.json'), JSON.stringify({ models: [{ slug: 'fixture-model', display_name: 'Fixture model',
      visibility: 'list', priority: 0, default_reasoning_level: 'low', supported_reasoning_levels: [{ effort: 'low' }, { effort: 'high' }] }] }));
    const base = `/api/projects/${ids[0]}/sessions`;
    assert.equal((await app.inject(base)).statusCode, 403);
    const auth = await app.inject('/api/projects');
    const headers = { cookie: String(auth.headers['set-cookie']).split(';')[0], 'x-csrf-token': auth.json().csrfToken };
    const opts = await app.inject({ url: base + '/options', headers });
    assert.equal(opts.statusCode, 200, opts.body);
    const optionTools = opts.json().tools.map((tool: { id: string }) => tool.id);
    for (const id of ['studio.get_remote_host', 'studio.run_remote_command', 'studio.remote_files', 'studio.read_remote_job', 'studio.stop_remote_job']) assert(optionTools.includes(id));
    assert.equal(opts.json().providers[0].models[0].id, 'fixture-model');
    assert.equal(opts.json().engine.available, true);
    const payload = { name: 'First session', providerId: provider, model: 'fixture-model', effort: 'low', requestId: randomUUID() };
    assert.equal((await app.inject({ method: 'POST', url: base, payload })).statusCode, 403);
    const replies = await Promise.all([1, 2].map(() => app.inject({ method: 'POST', url: base, headers, payload })));
    for (const reply of replies) assert.equal(reply.statusCode, 201, reply.body);
    const session = replies[0].json().session;
    assert.equal(replies[1].json().session.id, session.id);
    assert.deepEqual(Object.keys(session.permissions).sort(), optionTools.sort());
    assert.equal(session.permissions['studio.commit_update'], false);
    assert.equal(session.permissions['studio.rollback_update'], false);
    assert(Object.entries(session.permissions).filter(([key]) => !['studio.commit_update', 'studio.rollback_update', 'studio.push_project'].includes(key)).every(([, value]) => value === true));
    assert.equal(session.latestRun, null);
    assert.equal(session.roadmapEnabled, true);
    assert.equal(session.imageGenerationEnabled, true);
    assert(optionTools.includes('studio.list_generated_images'));assert(optionTools.includes('studio.import_generated_image'));
    assert.equal(session.roadmapAccess.available, true);
    assert.equal(session.permissions['studio.push_project'], false);
    assert.equal((await app.inject({ url: base, headers })).json().sessions.length, 1);
    assert.equal((await app.inject({ method: 'POST', url: base, headers, payload: { ...payload, name: 'Different' } })).statusCode, 409);
    const url = base + '/' + session.id;
    assert.equal(session.context.state, 'unavailable');
    assert.equal(session.context.sessionId, session.id);
    const context = { ...session.context, revision: 7, threadId: 'owned-context-thread', runId: randomUUID(), turnId: 'owned-context-turn',
      source: 'codex-0.163.0/thread/tokenUsage/updated:last', model: 'actual-owned-model', modelProvider: 'openai',
      state: 'available', reason: 'Owned stored context fixture', reportedAt: '2026-10-30T06:00:00Z', usedTokens: 500, capacityTokens: 1000,
      usedRatio: 0.5, remainingTokens: 500, overflowTokens: 0 };
    await promisify(execFile)('/usr/bin/python3', ['-B', '-c', `
import sqlite3,sys,json
with sqlite3.connect(sys.argv[1]) as db:
 db.execute('UPDATE sessions SET thread_id=? WHERE id=?',('owned-context-thread',sys.argv[2]))
 db.execute('CREATE TABLE session_context(session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,payload TEXT NOT NULL)')
 db.execute('INSERT INTO session_context VALUES (?,?)',(sys.argv[2],sys.argv[3]))
`, join(directory, ids[0], 'Sessions/Sessions.sqlite'), session.id, JSON.stringify(context)]);
    assert.deepEqual((await app.inject({ url, headers })).json().session.context, context);
    const changed = { ...session.permissions, 'studio.write_file': false };
    const update = await app.inject({ method: 'PATCH', url: url + '/settings', headers, payload: { revision: 1, permissions: changed, roadmapEnabled: false } });
    assert.equal(update.statusCode, 200, update.body);
    assert.equal(update.json().session.permissions['studio.write_file'], false);
    assert.equal(update.json().session.roadmapEnabled, false);
    assert.equal((await app.inject({ method: 'PATCH', url: url + '/settings', headers, payload: { revision: 2, roadmapEnabled: 'false' } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'PATCH', url: url + '/settings', headers: { cookie: headers.cookie }, payload: { revision: 2, roadmapEnabled: true } })).statusCode, 403);
    assert.equal((await app.inject({ method: 'PATCH', url: url + '/settings', headers, payload: { revision: 1, name: 'Stale' } })).statusCode, 409);
    const invalid = { ...changed }; delete invalid['studio.read_file']; invalid['studio.unknown'] = true;
    assert.equal((await app.inject({ method: 'PATCH', url: url + '/settings', headers, payload: { revision: 2, permissions: invalid } })).statusCode, 400);
    assert.deepEqual((await app.inject({ url: url + '/history', headers })).json(), { items: [], before: null, cursor: 0 });
    assert.equal((await app.inject({ url: `/api/projects/${ids[1]}/sessions/${session.id}`, headers })).statusCode, 404);
    assert.equal((await app.inject({ url, headers: { ...headers, origin: 'http://foreign.test' } })).statusCode, 403);
    assert(!JSON.stringify(session).includes(directory));
    const again = createApp({ projectDirectory: directory, providers: { directory: providers } });
    try {
      const auth2 = await again.inject('/api/projects');
      const h2 = { cookie: String(auth2.headers['set-cookie']).split(';')[0] };
      const restored = (await again.inject({ url, headers: h2 })).json().session;
      assert.equal(restored.permissions['studio.write_file'], false);
      assert.equal(restored.revision, 2);
      assert.equal(restored.roadmapEnabled, false);
      assert.equal(restored.engine.profile, session.engine.profile);
      assert.deepEqual(restored.context, context);
      await writeFile(join(providers, 'providers.json'), '[]');
      assert.equal((await again.inject({ url, headers: h2 })).statusCode, 200);
    } finally { await again.close(); }
    await writeFile(join(providers, 'providers.json'), JSON.stringify([{ id: provider, name: 'Fixture provider', type: 'openai', connected: true }]));
    const disabledImages = await app.inject({ method: 'PATCH', url: url + '/settings', headers, payload: { revision: 2, imageGenerationEnabled: false } });
    assert.equal(disabledImages.statusCode, 200, disabledImages.body);assert.equal(disabledImages.json().session.imageGenerationEnabled, false);
    const imageRevision=disabledImages.json().session.revision;
    for (const value of ['true', 1, null]) assert.equal((await app.inject({ method: 'PATCH', url: url + '/settings', headers, payload: { revision: imageRevision, imageGenerationEnabled: value } })).statusCode, 400);
    const db = join(directory, ids[0], 'Sessions/Sessions.sqlite');
    const runId=randomUUID(),jobId=randomUUID(),evidenceId=randomUUID();
    const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j7wAAAABJRU5ErkJggg==','base64');
    const image={id:evidenceId,jobId,projectId:ids[0],kind:'screenshot',source:'qmp-png',scope:'assigned-vm-screen',
      observer:{sessionId:session.id,agentRunId:runId,model:'fixture-model'},width:1,height:1,bytes:png.length,sha256:createHash('sha256').update(png).digest('hex'),createdAt:'2026-10-30T06:00:00Z',bootId:null};
    await mkdir(join(directory,ids[0],'Development'),{recursive:true});
    await promisify(execFile)('/usr/bin/python3',['-B','-c',`
import sqlite3,sys,json,uuid
image=json.loads(sys.argv[2]);run=image['observer']['agentRunId'];sid=image['observer']['sessionId'];job=image['jobId']
with sqlite3.connect(sys.argv[1]+'/Sessions/Sessions.sqlite') as db:
 db.execute("INSERT INTO runs VALUES (?,?,?,'owned','completed',0,'{}',NULL,NULL,NULL,'now','now')",(run,sid,str(uuid.uuid4())))
 db.execute('INSERT INTO tools VALUES (?,?,?,?,?,?,?)',(run,'owned-capture','studio_capture_vm','own','completed',json.dumps({'jobId':job}),json.dumps({'success':True,'image':image})))
with sqlite3.connect(sys.argv[1]+'/Development/Development.sqlite') as db:
 db.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,payload TEXT NOT NULL)');db.execute('INSERT INTO jobs VALUES (?,?)',(job,json.dumps({'projectId':image['projectId'],'sessionId':sid})))
 db.execute('CREATE TABLE evidence(id TEXT PRIMARY KEY,job_id TEXT NOT NULL,payload TEXT NOT NULL)');db.execute('INSERT INTO evidence VALUES (?,?,?)',(image['id'],job,json.dumps(image)))
`,join(directory,ids[0]),JSON.stringify(image)]);
    const gallery=url+'/screenshots',socket=join(root,'gallery.sock'),originalSocket=process.env.STUDIO_DEVELOPMENT_SOCKET;
    let corrupt=false,missing=false,foreignObserver=false;const imageCalls:Record<string,unknown>[]=[];
    const host=createServer(client=>{let raw='';client.on('data',chunk=>{raw+=String(chunk);if(!raw.includes('\n'))return;imageCalls.push(JSON.parse(raw));
      client.end(JSON.stringify(missing?{error:'Original screenshot missing',code:404}:{result:{metadata:foreignObserver?{...image,observer:{...image.observer,sessionId:randomUUID()}}:image,base64:corrupt?Buffer.from('changed').toString('base64'):png.toString('base64')}})+'\n');});});
    await new Promise<void>(resolve=>host.listen(socket,resolve));process.env.STUDIO_DEVELOPMENT_SOCKET=socket;
    try {
      assert.equal((await app.inject(gallery)).statusCode,403);
      assert.equal((await app.inject({url:gallery,headers:{...headers,origin:'http://foreign.test'}})).statusCode,403);
      const list=await app.inject({url:gallery,headers});assert.equal(list.statusCode,200,list.body);
      assert.equal(list.json().items[0].id,evidenceId);assert.equal(list.json().coverage.complete,true);
      assert.equal((await app.inject({url:gallery+'?cursor=forged',headers})).statusCode,409);
      const pngUrl=gallery+'/'+jobId+'/'+evidenceId;
      assert.equal((await app.inject(pngUrl)).statusCode,403);
      assert.equal((await app.inject({url:gallery+'/'+jobId+'/'+randomUUID(),headers})).statusCode,404);
      assert.equal(imageCalls.length,0);
      const actual=await app.inject({url:pngUrl,headers});assert.equal(actual.statusCode,200,actual.body);
      assert.equal(actual.headers['content-type'],'image/png');assert.equal(actual.headers['cache-control'],'private, no-store');assert.deepEqual(actual.rawPayload,png);
      assert.deepEqual(imageCalls.at(-1),{operation:'evidence',projectId:ids[0],id:jobId,evidenceId,presentationSessionId:session.id});
      foreignObserver=true;assert.equal((await app.inject({url:pngUrl,headers})).statusCode,409);foreignObserver=false;
      corrupt=true;assert.equal((await app.inject({url:pngUrl,headers})).statusCode,409);
      missing=true;assert.equal((await app.inject({url:pngUrl,headers})).statusCode,404);
      assert.equal((await app.inject({url:`/api/projects/${ids[1]}/sessions/${session.id}/screenshots`,headers})).statusCode,404);
    } finally {
      if(originalSocket===undefined)delete process.env.STUDIO_DEVELOPMENT_SOCKET;else process.env.STUDIO_DEVELOPMENT_SOCKET=originalSocket;
      await new Promise<void>(resolve=>host.close(()=>resolve()));
    }
    await writeFile(db, 'preserve corrupt data');
    assert.equal((await app.inject({ url: base, headers })).statusCode, 503);
    assert.equal(await readFile(db, 'utf8'), 'preserve corrupt data');
  } finally { await app.close(); await rm(root, { recursive: true, force: true }); }
});
