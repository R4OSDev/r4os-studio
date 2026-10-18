import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';
import type { FastifyInstance } from 'fastify';
import { createApp } from '../src/app.js';
import type { AuthClient, AuthClientFactory, AuthNotification } from '../src/codex-client.js';
import type { Provider, ProviderLogin } from '../../shared/providers.js';

const secret = 'test-token-must-never-reach-the-browser';
class FakeClient implements AuthClient {
  closed = false;
  cancelled = false;
  loginId = 'mock-login';
  badUrl = false;
  fail = false;
  account: { type: string; email: string; planType: string } | null = null;
  constructor(readonly home: string, readonly notify: AuthNotification) {}
  async request<T>(method: string): Promise<T> {
    if (this.closed) throw new Error(secret);
    if (method === 'account/read') {
      try { this.account = JSON.parse(await readFile(join(this.home, 'auth.json'), 'utf8')).account; } catch { /* Signed out. */ }
      return { account: this.account, accessToken: secret, refreshToken: secret } as T;
    }
    if (method === 'account/login/start') {
      if (this.fail) throw new Error(secret);
      return { type: 'chatgptDeviceCode', loginId: this.loginId,
        verificationUrl: this.badUrl ? 'https://example.invalid/phishing' : 'https://auth.openai.com/codex/device', userCode: 'TEST-1234' } as T;
    }
    if (method === 'account/login/cancel') { this.cancelled = true; return {} as T; }
    throw new Error('Unexpected RPC');
  }
  async complete(email = 'person@example.invalid') {
    this.account = { type: 'chatgpt', email, planType: 'plus' };
    await writeFile(join(this.home, 'auth.json'), JSON.stringify({ account: this.account, accessToken: secret, refreshToken: secret }), { mode: 0o600 });
    this.notify('account/login/completed', { loginId: this.loginId, success: true });
  }
  async close() { this.closed = true; }
}

async function setup(loginTimeoutMs?: number) {
  const directory = await mkdtemp(join(tmpdir(), 'r4os-provider-test-'));
  const clients = new Map<string, FakeClient>();
  let nextBadUrl = false;
  let nextFailure = false;
  const clientFactory: AuthClientFactory = (home, notify) => {
    const client = new FakeClient(home, notify);
    client.badUrl = nextBadUrl; client.fail = nextFailure;
    clients.set(basename(home), client);
    return client;
  };
  const makeApp = () => createApp({ providers: { directory, binary: '/unused', clientFactory, loginTimeoutMs } });
  const app = makeApp();
  await app.ready();
  return { app, directory, clients, makeApp,
    badUrl: () => { nextBadUrl = true; }, fail: () => { nextFailure = true; },
    cleanup: async () => { await app.close(); await rm(directory, { recursive: true, force: true }); } };
}

async function browser(app: FastifyInstance) {
  const response = await app.inject({ method: 'GET', url: '/api/providers' });
  assert.equal(response.statusCode, 200, response.body);
  const cookie = String(response.headers['set-cookie']).split(';')[0];
  const token = response.json().csrfToken as string;
  const headers = { cookie, 'x-csrf-token': token };
  return {
    headers,
    create: async (name = 'My OpenAI') => {
      const response = await app.inject({ method: 'POST', url: '/api/providers', headers, payload: { name, type: 'openai' } });
      assert.equal(response.statusCode, 201, response.body);
      return response.json().provider as Provider;
    },
    start: async (id: string) => {
      const response = await app.inject({ method: 'POST', url: `/api/providers/${id}/login`, headers });
      assert.equal(response.statusCode, 200, response.body);
      return response.json().login as ProviderLogin;
    },
  };
}

async function waitForConnected(app: FastifyInstance, id: string, headers: Record<string, string>) {
  for (let attempt = 0; attempt < 30; attempt++) {
    const response = await app.inject({ method: 'GET', url: `/api/providers/${id}/login`, headers });
    if (response.json().login?.status === 'connected') return;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  assert.fail('Login completion was not observed');
}

test('browser-owned sign-in, redaction, persistence and provider isolation', async (context) => {
  const setupResult = await setup();
  const { app, directory, clients, makeApp } = setupResult;
  context.after(setupResult.cleanup);
  const first = await browser(app);
  const other = await browser(app);
  const provider = await first.create();
  const secondProvider = await first.create('Another OpenAI');
  const login = await first.start(provider.id);
  assert.equal(login.status, 'pending');
  assert.equal(login.userCode, 'TEST-1234');
  assert.equal(login.verificationUrl, 'https://auth.openai.com/codex/device');
  assert.equal((await app.inject({ method: 'GET', url: `/api/providers/${provider.id}/login`, headers: other.headers })).statusCode, 403);
  assert.equal((await app.inject({ method: 'DELETE', url: `/api/providers/${provider.id}/login`, headers: other.headers })).statusCode, 403);
  assert.equal((await app.inject({ method: 'POST', url: `/api/providers/${provider.id}/login`, headers: first.headers })).statusCode, 409);
  await clients.get(provider.id)!.complete();
  await waitForConnected(app, provider.id, first.headers);
  const response = await app.inject({ method: 'GET', url: `/api/providers/${provider.id}`, headers: first.headers });
  assert.equal(response.json().provider.status, 'connected');
  assert.equal(response.json().provider.account.email, 'person@example.invalid');
  assert.ok(!response.body.includes(secret));
  const list = await app.inject({ method: 'GET', url: '/api/providers', headers: first.headers });
  assert.ok(!list.body.includes(secret));
  assert.equal(list.json().providers.find((item: Provider) => item.id === secondProvider.id).status, 'disconnected');
  assert.equal((await stat(directory)).mode & 0o777, 0o700);
  assert.equal((await stat(join(directory, 'providers.json'))).mode & 0o777, 0o600);
  await app.close();
  const restored = makeApp();
  context.after(() => restored.close());
  const restoredBrowser = await browser(restored);
  const restoredResponse = await restored.inject({ method: 'GET', url: `/api/providers/${provider.id}`, headers: restoredBrowser.headers });
  assert.equal(restoredResponse.json().provider.status, 'connected');
  assert.ok(!restoredResponse.body.includes(secret));
  assert.equal((await restored.inject({ method: 'POST', url: `/api/providers/${provider.id}/disconnect`, headers: restoredBrowser.headers })).statusCode, 200);
  await assert.rejects(readFile(join(directory, provider.id, 'auth.json')), { code: 'ENOENT' });
  assert.equal((await restored.inject({ method: 'GET', url: `/api/providers/${secondProvider.id}`, headers: restoredBrowser.headers })).statusCode, 200);
});

test('CSRF, cross-origin, host and OpenAI-only validation', async (context) => {
  const result = await setup(); context.after(result.cleanup);
  const b = await browser(result.app);
  const payload = { name: 'OpenAI', type: 'openai' };
  for (const headers of [{}, { cookie: b.headers.cookie }, { ...b.headers, 'x-csrf-token': 'é'.repeat(64) },
    { ...b.headers, origin: 'https://example.invalid' }]) {
    assert.equal((await result.app.inject({ method: 'POST', url: '/api/providers', headers, payload })).statusCode, 403);
  }
  assert.equal((await result.app.inject({ method: 'GET', url: '/api/providers', headers: { host: 'evil.example' } })).statusCode, 403);
  for (const invalid of [{ name: 'Other', type: 'anthropic' }, { name: '  ', type: 'openai' }, { name: '\u0001', type: 'openai' }]) {
    assert.equal((await result.app.inject({ method: 'POST', url: '/api/providers', headers: b.headers, payload: invalid })).statusCode, 400);
  }
  assert.equal((await result.app.inject({ method: 'GET', url: '/api/providers/not-a-uuid', headers: b.headers })).statusCode, 404);
});

test('cancellation discards codes and ignores late completion; removal cleans storage', async (context) => {
  const result = await setup(); context.after(result.cleanup);
  const b = await browser(result.app);
  const provider = await b.create();
  await b.start(provider.id);
  const client = result.clients.get(provider.id)!;
  // Simulate a token file written just before the completion notification arrives.
  await writeFile(join(client.home, 'auth.json'), JSON.stringify({ accessToken: secret }), { mode: 0o600 });
  const cancel = await result.app.inject({ method: 'DELETE', url: `/api/providers/${provider.id}/login`, headers: b.headers });
  assert.equal(cancel.statusCode, 204);
  assert.ok(client.cancelled && client.closed);
  await assert.rejects(stat(client.home), { code: 'ENOENT' });
  client.notify('account/login/completed', { loginId: client.loginId, success: true });
  assert.equal((await result.app.inject({ method: 'GET', url: `/api/providers/${provider.id}/login`, headers: b.headers })).json().login, null);
  assert.equal((await result.app.inject({ method: 'DELETE', url: `/api/providers/${provider.id}`, headers: b.headers })).statusCode, 204);
  assert.equal((await result.app.inject({ method: 'GET', url: '/api/providers', headers: b.headers })).json().providers.length, 0);
  await assert.rejects(stat(join(result.directory, provider.id)), { code: 'ENOENT' });
});

test('expired codes are cleared and cancelled upstream', async (context) => {
  const result = await setup(30); context.after(result.cleanup);
  const b = await browser(result.app);
  const provider = await b.create();
  await b.start(provider.id);
  await new Promise((resolve) => setTimeout(resolve, 70));
  const response = await result.app.inject({ method: 'GET', url: `/api/providers/${provider.id}/login`, headers: b.headers });
  assert.equal(response.json().login.status, 'expired');
  assert.equal(response.json().login.userCode, undefined);
  assert.ok(result.clients.get(provider.id)!.cancelled);
  assert.ok(result.clients.get(provider.id)!.closed);
  await assert.rejects(stat(join(result.directory, provider.id)), { code: 'ENOENT' });
});

test('unsafe verification URLs and upstream errors are not exposed', async (context) => {
  for (const failure of ['badUrl', 'fail'] as const) {
    const result = await setup(); context.after(result.cleanup);
    result[failure]();
    const b = await browser(result.app);
    const provider = await b.create();
    const login = await b.start(provider.id);
    assert.equal(login.status, 'failed');
    assert.equal(login.verificationUrl, undefined);
    assert.equal(login.userCode, undefined);
    assert.ok(!JSON.stringify(login).includes(secret));
    assert.ok(result.clients.get(provider.id)!.closed);
  }
});
