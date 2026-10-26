import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeUsage, readUsage } from '../src/modules/llm-providers/openai/usage.js';
import type { AuthClient } from '../src/modules/llm-providers/openai/codex-client.js';
import { creditAvailability, creditGroups } from '../../frontend/src/features/llm-providers/components/ProviderCredits.js';

test('native credit variants preserve exact numeric text, unknown, zero, unlimited and allowlisted fields', () => {
  const read = (credits?: unknown) => normalizeUsage({ rateLimits: { credits } }).limits[0].credits;
  assert.equal(read(), null); assert.equal(read(null), null); assert.equal(read([]), null);
  const amount = '900719925474099312345678901234567890.000000000000000001';
  const credit = read({ hasCredits: true, unlimited: false, balance: amount, accountId: 'private', accessToken: 'private' })!;
  assert.deepEqual(credit, { hasCredits: true, unlimited: false, balance: amount });
  assert.deepEqual(read({ hasCredits: false, unlimited: false, balance: '0' }), { hasCredits: false, unlimited: false, balance: '0' });
  assert.equal(creditAvailability(read({ hasCredits: false, unlimited: true, balance: null })!), 'Unlimited');
  assert.equal(creditAvailability(credit), 'Available'); assert.equal(creditAvailability(read({ hasCredits: false })!), 'Unavailable');
  assert.equal(creditAvailability(read({ hasCredits: 'true', unlimited: 0, balance: 'NaN' })!), 'Not reported');
  for (const invalid of [0, null, '', ' ', 'NaN', 'Infinity', '<script>alert(1)</script>', '1,234.0', '1e', '1\n2', '9'.repeat(257), {}, true]) assert.equal(read({ balance: invalid })?.balance, null);
  for (const exact of ['0.000', '-0.05', '1.23000000000000000001', '1e1000']) assert.equal(read({ balance: exact })?.balance, exact);
});

test('multiple bucket credits are never summed and full snapshots can remove stale credits', () => {
  const credits = { hasCredits: true, unlimited: false, balance: '12345678901234567890.12345' };
  const usage = normalizeUsage({ rateLimits: { credits: { ...credits, balance: 'foreign' } }, rateLimitsByLimitId: {
    codex: { limitName: 'Codex', credits }, model: { limitName: 'Model quota', credits }, other: { credits: { ...credits, balance: '0' } }, missing: {},
  }, rateLimitResetCredits: { availableCount: 7, credits: [] } });
  const groups = creditGroups(usage.limits); assert.equal(groups.length, 2); assert.deepEqual(groups[0].names, ['Codex', 'Model quota']);
  assert.equal(groups[0].credits.balance, credits.balance); assert.equal(usage.resetCredits?.availableCount, 7);
  assert.equal(creditGroups(normalizeUsage({ rateLimits: {} }).limits).length, 0);
});

test('credit refresh uses only the existing read RPC without a spend, reset or inference call', async () => {
  const calls: unknown[] = [];
  const client = { async request(method: string, params?: unknown) { calls.push([method, params]); return { rateLimits: { credits: { hasCredits: true, unlimited: false, balance: '10.5' } } }; } } as unknown as AuthClient;
  assert.equal((await readUsage(client)).limits[0].credits?.balance, '10.5');
  assert.deepEqual(calls, [['account/rateLimits/read', undefined]]);
});
