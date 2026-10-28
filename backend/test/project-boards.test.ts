import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, writeFile, readFile, access } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createApp } from '../src/app.js';

await test('Boards browser API keeps project scope, original receipts, revisions and private data', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-own-boards-'));
  const directory = join(root, 'Projects'), id = randomUUID(), other = randomUUID();
  const app = createApp({ projectDirectory: directory, providers: { directory: join(root, 'LLMProvider') } });
  try {
    const session = await app.inject('/api/projects');
    const headers = { cookie: String(session.headers['set-cookie']).split(';')[0], 'x-csrf-token': session.json().csrfToken };
    for (const ident of [id, other]) {
      await mkdir(join(directory, ident, 'Workspace'), { recursive: true });
      await writeFile(join(directory, ident, 'Workspace/module.R4MF'), 'Own Board fixture');
    }
    await promisify(execFile)('/usr/bin/python3', ['-B', '-c', `import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
 for i,ident in enumerate(sys.argv[2:]):
  db.execute("INSERT INTO projects(id,name,description,language,template,module_name,pins,created_at,updated_at,state) VALUES(?,?,'','C','terminal',?,'{}','now','now','ready')",(ident,'Own Board fixture '+str(i),'own_'+str(i)))`, join(directory, 'Projects.sqlite'), id, other]);
    const base = `/api/projects/${id}/boards`;
    assert.equal((await app.inject(base)).statusCode, 403);
    assert.deepEqual((await app.inject({ url: base, headers })).json(), { projectId: id, revision: 0, boards: [] });
    await assert.rejects(access(join(directory, id, 'Boards')));
    const body = { requestId: randomUUID(), expectedRevision: 0, name: 'Own work', description: 'Human notes only.' };
    for (const bad of [{}, { cookie: headers.cookie }, { ...headers, origin: 'http://foreign.test' }, { ...headers, host: 'foreign.test' }, { ...headers, 'sec-fetch-site': 'cross-site' }])
      assert.equal((await app.inject({ method: 'POST', url: base, headers: bad, payload: body })).statusCode, 403);
    for (const payload of [{ ...body, path: '/' }, { ...body, expectedRevision: '0' }, { ...body, name: ['bad'] }, { ...body, description: 123 }])
      assert.equal((await app.inject({ method: 'POST', url: base, headers, payload })).statusCode, 400);
    const results = await Promise.all([0, 1].map(() => app.inject({ method: 'POST', url: base, headers, payload: body })));
    for (const result of results) assert.equal(result.statusCode, 200, result.body);
    assert.deepEqual(results[0].json(), results[1].json());
    const created = results[0].json();
    const snapshot = await app.inject({ url: base + '/' + created.boardId, headers });
    assert.equal(snapshot.statusCode, 200, snapshot.body);
    assert.deepEqual(snapshot.json().columns.map((column: { title: string }) => column.title), ['To do', 'In progress', 'Done']);
    assert.deepEqual(snapshot.json().cards, []);
    assert.equal((await app.inject({ method: 'POST', url: base, headers, payload: { ...body, name: 'Changed same ID' } })).statusCode, 409);
    assert.equal((await app.inject({ method: 'POST', url: base, headers, payload: { ...body, requestId: randomUUID(), expectedRevision: 1, name: 'OWN WORK' } })).statusCode, 409);
    const patch = { requestId: randomUUID(), expectedRevision: 1, name: 'Renamed' };
    assert.equal((await app.inject({ method: 'PATCH', url: base + '/' + created.boardId, headers, payload: patch })).statusCode, 200);
    assert.equal((await app.inject({ method: 'PATCH', url: base + '/' + created.boardId, headers, payload: { ...patch, requestId: randomUUID(), name: 'Stale' } })).statusCode, 409);
    assert.deepEqual((await app.inject({ url: base + '/receipts/' + body.requestId, headers })).json(), created);
    const second = await app.inject({ method: 'POST', url: base, headers, payload: { ...body, requestId: randomUUID(), expectedRevision: 2, name: 'Second' } });
    assert.equal(second.statusCode, 200, second.body);
    const order = { requestId: randomUUID(), expectedRevision: 3, ids: [second.json().boardId, created.boardId] };
    assert.equal((await app.inject({ method: 'POST', url: base + '/order', headers, payload: order })).statusCode, 200);
    assert.deepEqual((await app.inject({ url: base, headers })).json().boards.map((value: { id: string }) => value.id), order.ids);
    const foreignBase = `/api/projects/${other}/boards`;
    assert.equal((await app.inject({ url: foreignBase + '/' + created.boardId, headers })).statusCode, 404);
    assert.equal((await app.inject({ url: foreignBase + '/receipts/' + body.requestId, headers })).statusCode, 404);
    assert.equal((await app.inject({ method: 'PATCH', url: foreignBase + '/' + created.boardId, headers, payload: patch })).statusCode, 404);
    assert.equal((await app.inject({ url: `/api/projects/${randomUUID()}/boards`, headers })).statusCode, 404);
    assert.equal(await readFile(join(directory, id, 'Workspace/module.R4MF'), 'utf8'), 'Own Board fixture');
    await assert.rejects(access(join(directory, id, 'Workspace/Boards')));
    const bid = created.boardId, columnId = snapshot.json().columns[0].id;
    const mutationUrl = base + '/' + bid + '/mutations?clientLevel=2';
    const cardInput = { requestId: randomUUID(), expectedRevision: 2, action: 'create_card', input: { columnId, title: 'Own HTTP card' } };
    assert.equal((await app.inject({ method: 'POST', url: mutationUrl, payload: cardInput })).statusCode, 403);
    assert.equal((await app.inject({ method: 'POST', url: mutationUrl, headers, payload: { ...cardInput, input: { ...cardInput.input, path: '/' } } })).statusCode, 400);
    const cardCreated = await app.inject({ method: 'POST', url: mutationUrl, headers, payload: cardInput });
    assert.equal(cardCreated.statusCode, 200, cardCreated.body);
    assert.deepEqual((await app.inject({ method: 'POST', url: mutationUrl, headers, payload: cardInput })).json(), cardCreated.json());
    assert.equal((await app.inject({ url: base, headers })).statusCode, 409);
    const cardId = cardCreated.json().cardId;
    const detail = await app.inject({ url: base + '/' + bid + '/cards/' + cardId + '?clientLevel=2', headers });
    assert.equal(detail.statusCode, 200, detail.body); assert.equal(detail.json().card.title, 'Own HTTP card'); assert.equal(detail.json().boardRevision, 3);
    const foreignColumn = (await app.inject({ url: base + '/' + second.json().boardId + '?clientLevel=2', headers })).json().columns[0].id;
    for (const input of [{ columnId: foreignColumn, title: 'Wrong parent' }, { columnId, title: '\ud800' }]) {
      const denied = await app.inject({ method: 'POST', url: mutationUrl, headers, payload: { ...cardInput, requestId: randomUUID(), expectedRevision: 3, input } });
      assert([400, 404].includes(denied.statusCode), denied.body);
    }
    const moved = await app.inject({ method: 'POST', url: mutationUrl, headers, payload: { requestId: randomUUID(), expectedRevision: 3, action: 'delete_column', input: { columnId, expectedColumnRevision: 1, targetColumnId: snapshot.json().columns[1].id, confirm: true } } });
    assert.equal(moved.statusCode, 200, moved.body); assert.equal(moved.json().movedCards, 1);
    const afterMove = await app.inject({ url: base + '/' + bid + '/cards/' + cardId + '?clientLevel=2', headers });
    assert.equal(afterMove.json().card.columnId, snapshot.json().columns[1].id);
    const database = join(directory, id, 'Boards/Boards.sqlite');
    await writeFile(database, 'Owned unknown data; must never be reinitialized');
    const bytes = await readFile(database);
    assert.equal((await app.inject({ url: base, headers })).statusCode, 503);
    assert.deepEqual(await readFile(database), bytes);
  } finally { await app.close(); await rm(root, { recursive: true, force: true }); }
});
