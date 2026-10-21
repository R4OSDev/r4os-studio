import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';
import type { FastifyInstance } from 'fastify';
import { createApp } from '../src/app.js';
import type { AuthClient, AuthClientFactory, AuthNotification } from '../src/modules/llm-providers/openai/codex-client.js';
import type { Provider, ProviderLogin, ResetOutcome } from '../../shared/llm-providers.js';
import { normalizeUsage } from '../src/modules/llm-providers/openai/usage.js';
import { ProviderError } from '../src/modules/llm-providers/errors.js';

const secret = 'test-token-must-never-reach-the-browser';
class FakeClient implements AuthClient {
  closed = false;
  cancelled = false;
  loginId = 'mock-login';
  badUrl = false;
  fail = false;
  usageReads = 0;
  redemptions = 0;
  failUsage = false;
  loseResetResponse = false;
  resetOutcome: ResetOutcome = 'reset';
  attempts = new Map<string, ResetOutcome>();
  usage: unknown = { rateLimits: { limitId: 'codex', primary: { usedPercent: 40, windowDurationMins: 300, resetsAt: 1800000000 } },
    rateLimitResetCredits: { availableCount: 2, credits: null } };
  account: { type: string; email: string; planType: string } | null = null;
  constructor(readonly home: string, readonly notify: AuthNotification) {}
  async request<T>(method: string, params?: unknown): Promise<T> {
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
    if (method === 'account/rateLimits/read') {
      this.usageReads++;
      if (this.failUsage) throw new Error(secret);
      return structuredClone(this.usage) as T;
    }
    if (method === 'account/rateLimitResetCredit/consume') {
      const { idempotencyKey } = params as { idempotencyKey: string };
      if (this.attempts.has(idempotencyKey)) return { outcome: 'alreadyRedeemed' } as T;
      this.redemptions++;
      this.attempts.set(idempotencyKey, this.resetOutcome);
      if (this.loseResetResponse) { this.loseResetResponse = false; throw new Error(secret); }
      return { outcome: this.resetOutcome } as T;
    }
    throw new Error('Unexpected RPC');
  }
  async complete(email = 'person@example.invalid') {
    this.account = { type: 'chatgpt', email, planType: 'plus' };
    await writeFile(join(this.home, 'auth.json'), JSON.stringify({ account: this.account, accessToken: secret, refreshToken: secret }), { mode: 0o600 });
    this.notify('account/login/completed', { loginId: this.loginId, success: true });
  }
  async close() { this.closed = true; }
}

async function setup(loginTimeoutMs?: number, beforeDisconnect?: (id: string) => Promise<void>) {
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
  const makeApp = () => createApp({ projectDirectory: join(directory, 'Projects'), providers: { directory, binary: '/unused', clientFactory, loginTimeoutMs, ...(beforeDisconnect ? { beforeDisconnect } : {}) } });
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

test('usage reads are account-isolated, cached, refreshed and filtered without consuming resets', async (context) => {
  const result = await setup(); context.after(result.cleanup);
  const b = await browser(result.app);
  const first = await b.create(); const second = await b.create('Second account');
  for (const provider of [first, second]) {
    await b.start(provider.id); await result.clients.get(provider.id)!.complete();
    await waitForConnected(result.app, provider.id, b.headers);
  }
  const client = result.clients.get(first.id)!;
  client.usage = {
    accountId: secret, accessToken: secret, rateLimitUpsell: { secret }, ordinaryUsageAllowed: false,
    rateLimits: { limitId: 'codex', primary: { usedPercent: 99 } },
    rateLimitsByLimitId: {
      codex: { primary: { usedPercent: 105, windowDurationMins: 300, resetsAt: 1800000000 }, secondary: null },
      weekly: { limitName: 'Other quota', primary: null, secondary: { usedPercent: 25.5, windowDurationMins: 10080, resetsAt: null } },
    },
    rateLimitResetCredits: { availableCount: 5, accessToken: secret, credits: [
      { id: 'credit-1', resetType: 'codexRateLimits', status: 'available', grantedAt: 1790000000, expiresAt: 1810000000, title: 'Earned reset', accessToken: secret },
    ] },
  };
  const read = (suffix = '') => result.app.inject({ method: 'GET', url: `/api/providers/${first.id}/usage${suffix}`, headers: b.headers });
  assert.equal((await result.app.inject({ method: 'GET', url: `/api/providers/${first.id}/usage` })).statusCode, 403);
  const response = await read(); const usage = response.json().usage;
  assert.equal(response.statusCode, 200); assert.ok(!response.body.includes(secret));
  assert.equal(usage.limits.length, 2); assert.equal(usage.limits[0].primary.usedPercent, 105);
  assert.equal(usage.limits[0].primary.remainingPercent, 0);
  assert.equal(usage.limits[0].primary.resetsAt, new Date(1800000000000).toISOString());
  assert.equal(usage.limits[1].secondary.remainingPercent, 74.5);
  assert.equal(usage.limits[1].secondary.resetsAt, null);
  assert.equal(usage.resetCredits.availableCount, 5); assert.equal(usage.resetCredits.credits.length, 1);
  assert.equal(usage.ordinaryUsageAllowed, false);
  await read(); assert.equal(client.usageReads, 1);
  await read('?refresh=true'); assert.equal(client.usageReads, 2);
  client.notify('account/rateLimits/updated', { rateLimits: {} });
  await read(); assert.equal(client.usageReads, 3);
  const other = await result.app.inject({ method: 'GET', url: `/api/providers/${second.id}/usage`, headers: b.headers });
  assert.equal(other.json().usage.limits[0].primary.usedPercent, 40);
  assert.equal(client.redemptions, 0); assert.equal(result.clients.get(second.id)!.redemptions, 0);
});

test('unknown usage and reset availability are preserved instead of fabricated', () => {
  const value = normalizeUsage({ rateLimits: { primary: { usedPercent: -1, resetsAt: '1800000000', windowDurationMins: null } },
    rateLimitResetCredits: null });
  assert.equal(value.limits[0].primary!.usedPercent, null);
  assert.equal(value.limits[0].primary!.remainingPercent, null);
  assert.equal(value.limits[0].primary!.resetsAt, null);
  assert.equal(value.resetCredits, null);
  assert.equal(value.ordinaryUsageAllowed, null);
  assert.equal(normalizeUsage({ rateLimits: {}, rateLimitResetCredits: { availableCount: 3, credits: null } }).resetCredits!.credits, null);
  assert.deepEqual(normalizeUsage({ rateLimits: {}, rateLimitResetCredits: { availableCount: 0, credits: [] } }).resetCredits!.credits, []);
  assert.throws(() => normalizeUsage({ accessToken: secret }));
});

test('reset redemption requires a connected account, CSRF, explicit confirmation and a valid retry key', async (context) => {
  const result = await setup(); context.after(result.cleanup);
  const b = await browser(result.app); const provider = await b.create();
  const url = `/api/providers/${provider.id}/usage/resets`;
  const payload = { confirm: true, idempotencyKey: '00000000-0000-4000-8000-000000000001' };
  assert.equal((await result.app.inject({ method: 'POST', url, headers: b.headers, payload })).statusCode, 409);
  await b.start(provider.id); const client = result.clients.get(provider.id)!;
  await client.complete(); await waitForConnected(result.app, provider.id, b.headers);
  assert.equal((await result.app.inject({ method: 'POST', url, payload })).statusCode, 403);
  assert.equal((await result.app.inject({ method: 'POST', url, headers: { ...b.headers, origin: 'https://evil.invalid' }, payload })).statusCode, 403);
  for (const invalid of [{ ...payload, confirm: false }, { idempotencyKey: payload.idempotencyKey }, { ...payload, idempotencyKey: 'bad' }, { ...payload, creditId: '' }]) {
    assert.equal((await result.app.inject({ method: 'POST', url, headers: b.headers, payload: invalid })).statusCode, 400);
  }
  assert.equal((await result.app.inject({ method: 'GET', url, headers: b.headers })).statusCode, 404);
  assert.equal(client.redemptions, 0);
});

test('reset retries retain idempotency and successful outcomes survive a subsequent usage-read failure', async (context) => {
  const result = await setup(); context.after(result.cleanup);
  const b = await browser(result.app); const provider = await b.create();
  await b.start(provider.id); const client = result.clients.get(provider.id)!;
  await client.complete(); await waitForConnected(result.app, provider.id, b.headers);
  const payload = { confirm: true, idempotencyKey: '00000000-0000-4000-8000-000000000001', creditId: 'credit-1' };
  const post = (body = payload) => result.app.inject({ method: 'POST', url: `/api/providers/${provider.id}/usage/resets`, headers: b.headers, payload: body });
  client.loseResetResponse = true;
  const uncertain = await post(); assert.equal(uncertain.statusCode, 502); assert.ok(!uncertain.body.includes(secret));
  const retry = await post(); assert.equal(retry.json().outcome, 'alreadyRedeemed'); assert.equal(client.redemptions, 1);
  assert.equal(retry.json().usage.limits[0].primary.usedPercent, 40);
  client.failUsage = true;
  const confirmed = await post({ ...payload, idempotencyKey: '00000000-0000-4000-8000-000000000002' });
  assert.equal(confirmed.statusCode, 200); assert.equal(confirmed.json().outcome, 'reset'); assert.equal(confirmed.json().usage, null);
  assert.equal(client.redemptions, 2); assert.ok(!confirmed.body.includes(secret));
  const unavailable = await result.app.inject({ method: 'GET', url: `/api/providers/${provider.id}/usage?refresh=true`, headers: b.headers });
  assert.equal(unavailable.statusCode, 502); assert.ok(!unavailable.body.includes(secret));
  assert.equal(client.redemptions, 2);
  client.failUsage = false;
  for (const [index, outcome] of ['nothingToReset', 'noCredit'].entries()) {
    client.resetOutcome = outcome as ResetOutcome;
    const response = await post({ ...payload, idempotencyKey: `00000000-0000-4000-8000-00000000000${index + 3}` });
    assert.equal(response.json().outcome, outcome);
  }
});


test('provider disconnect closes admission before stopping workers and preserves credentials if stop fails', async (context) => {
  let allow = true, observed = 0;
  const result = await setup(undefined, async (id) => {
    const records = JSON.parse(await readFile(join(result.directory, 'providers.json'), 'utf8'));
    assert.equal(records.find((r: { id: string }) => r.id === id).connected, false);
    observed++;
    if (!allow) throw new ProviderError('Agent stop is unavailable.', 503);
  });
  context.after(result.cleanup);
  const b = await browser(result.app), provider = await b.create();
  await b.start(provider.id); const client = result.clients.get(provider.id)!;
  await client.complete(); await waitForConnected(result.app, provider.id, b.headers);
  allow = false; observed = 0;
  const file = join(client.home, 'auth.json'), original = await readFile(file, 'utf8');
  const disconnect = () => result.app.inject({ method: 'POST', url: `/api/providers/${provider.id}/disconnect`, headers: b.headers });
  assert.equal((await disconnect()).statusCode, 503);
  assert.equal(await readFile(file, 'utf8'), original); assert.equal(client.closed, false);
  assert.equal(JSON.parse(await readFile(join(result.directory, 'providers.json'), 'utf8'))[0].connected, true);
  allow = true;
  assert.equal((await disconnect()).statusCode, 200); assert.equal(client.closed, true);
  await assert.rejects(readFile(file, 'utf8')); assert.equal(observed, 2);
});
