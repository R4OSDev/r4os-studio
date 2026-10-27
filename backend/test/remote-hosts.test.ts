import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createApp } from '../src/app.js';

await test('private Remote Host catalog defaults, exact receipts, revisions, restart and corruption', async () => {
  const root = await mkdtemp(join(tmpdir(), 'studio-remote-catalog-'));
  const options = { providers: { directory: join(root, 'LLMProvider') }, projectDirectory: join(root, 'Projects') };
  let app = createApp(options); const url = '/api/remote-hosts';
  try {
    let response = await app.inject(url); assert.equal(response.statusCode, 200, response.body);
    assert.deepEqual(response.json().hosts, []); assert.equal(response.headers['cache-control'], 'no-store');
    assert(String(response.headers['set-cookie']).includes('Path=/api/remote-hosts; HttpOnly; SameSite=Strict'));
    let headers = { cookie: String(response.headers['set-cookie']).split(';')[0], 'x-csrf-token': response.json().csrfToken };
    const input = { requestId: randomUUID(), name: 'R4 Desktop', address: 'R4Desktop.EXAMPLE.' };
    for (const extra of [null, { cookie: headers.cookie }, { ...headers, origin: 'https://foreign.example' }, { ...headers, host: 'foreign.example' }, { ...headers, 'sec-fetch-site': 'cross-site' }, { ...headers, 'x-csrf-token': 'invalid' }]) {
      assert.equal((await app.inject({ method: 'POST', url, payload: input, ...(extra ? { headers: extra } : {}) })).statusCode, 403);
    }
    for (const patch of [{ name: '' }, { name: '\u0000' }, { address: '-oProxyCommand=x' }, { address: 'user@host' }, { address: 'https://host' }, { address: '127.900.0.1' }, { address: 'fe80::1%eth0' }, { port: 0 }, { port: true }, { port: 65536 }, { user: 'a b' }, { password: 'private\nvalue' }, { command: 'VER' }]) {
      const result = await app.inject({ method: 'POST', url, headers, payload: { ...input, ...patch } });
      assert.equal(result.statusCode, 400, result.body);
    }
    response = await app.inject({ method: 'POST', url, headers, payload: input }); assert.equal(response.statusCode, 200, response.body);
    const created = response.json(); assert.equal(created.user, 'r4os'); assert.equal(created.port, 22); assert.equal(created.address, 'r4desktop.example');
    assert.equal(created.passwordConfigured, true); assert.equal(created.hostKey.state, 'unbound'); assert.equal(created.lastTest, null);
    assert(!response.body.includes('rosebud')); assert(!Object.hasOwn(created, 'password'));
    assert.deepEqual((await app.inject({ method: 'POST', url, headers, payload: input })).json(), created);
    assert.equal((await app.inject({ method: 'POST', url, headers, payload: { ...input, name: 'Different request contents' } })).statusCode, 409);
    assert.equal((await app.inject({ method: 'POST', url, headers, payload: { ...input, requestId: randomUUID(), name: 'r4 desktop' } })).statusCode, 409);
    const path = url + '/' + created.id;
    assert.equal((await app.inject(path)).statusCode, 403);
    const ownPassword = 'own-isolated-password-4321';
    const update = { requestId: randomUUID(), revision: 1, user: 'custom_user', password: ownPassword, port: 2222 };
    response = await app.inject({ method: 'PATCH', url: path, headers, payload: update }); assert.equal(response.statusCode, 200, response.body);
    assert(!response.body.includes(ownPassword)); assert.equal(response.json().credentialRevision, 2); assert.equal(response.json().endpointRevision, 2);
    response = await app.inject({ method: 'PATCH', url: path, headers, payload: { requestId: randomUUID(), revision: 2, description: 'Saved without another password change' } }); assert.equal(response.statusCode, 200, response.body);
    assert.equal(response.json().credentialRevision, 2); assert.equal(response.json().user, 'custom_user');
    assert.equal((await app.inject({ method: 'PATCH', url: path, headers, payload: { requestId: randomUUID(), revision: 1, name: 'Stale' } })).statusCode, 409);
    const database = join(root, 'RemoteHosts/RemoteHosts.sqlite');
    const secret = await promisify(execFile)('/usr/bin/python3', ['-B', '-c', 'import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); assert db.execute("SELECT password FROM secrets").fetchone()[0]==sys.argv[2]; assert db.execute("PRAGMA foreign_key_check").fetchone() is None; print("private saved login preserved")', database, ownPassword]);
    assert.match(secret.stdout, /preserved/);
    assert.equal((await stat(join(root, 'RemoteHosts'))).mode & 0o777, 0o700); assert.equal((await stat(database)).mode & 0o777, 0o600);
    const second = await app.inject({ method: 'POST', url, headers, payload: { requestId: randomUUID(), name: 'IPv6 host', address: '2001:db8::1' } }); assert.equal(second.statusCode, 200, second.body);
    await app.close(); app = createApp(options); response = await app.inject(url);
    headers = { cookie: String(response.headers['set-cookie']).split(';')[0], 'x-csrf-token': response.json().csrfToken };
    assert.equal(response.json().hosts.length, 2); assert(!response.body.includes(ownPassword));
    const removal = { requestId: randomUUID(), revision: 3, confirm: true };
    assert.equal((await app.inject({ method: 'DELETE', url: path, headers, payload: { ...removal, confirm: false } })).statusCode, 400);
    response = await app.inject({ method: 'DELETE', url: path, headers, payload: removal }); assert.equal(response.statusCode, 200, response.body);
    assert.deepEqual((await app.inject({ method: 'DELETE', url: path, headers, payload: removal })).json(), response.json());
    assert.equal((await app.inject({ url: path, headers })).statusCode, 404);
    assert.equal((await app.inject(url)).json().hosts.length, 1);
    await writeFile(database, 'Own corrupt fixture; preserve these bytes', { mode: 0o600 }); const corrupt = await readFile(database);
    response = await app.inject(url); assert.equal(response.statusCode, 503); assert.deepEqual(await readFile(database), corrupt);
    assert(!response.body.includes('rosebud')); assert(!response.body.includes(ownPassword));
  } finally { await app.close(); await rm(root, { recursive: true, force: true }); }
});
