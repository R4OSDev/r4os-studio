import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { zaiHeaders, zaiRequest, zaiFailure } from './api_zai.mjs';

test('native limit classes preserve reset evidence and never infer a window', () => {
  assert.equal(zaiFailure({ error: { code: '1308' } }, 429).safeCode, 'zai_subscription_exhausted');
  assert.equal(zaiFailure({ error: { code: 1302 } }, 429).safeCode, 'rate_limit_exceeded');
  assert.equal(zaiFailure({ error: { code: '1305' } }, 429).safeCode, 'api_service_unavailable');
  assert.equal(zaiFailure({ error: { code: '1311' } }).safeCode, 'zai_model_unavailable');
  assert.equal(zaiFailure({ error: { code: '1310' } }).resetAt, null);
  assert.equal(zaiFailure({ error: { code: 'unknown' } }), null);
  assert.equal(zaiFailure({ error: { code: '1308', nextResetTime: 1793830124999 } }).resetAt, new Date(1793830124999).toISOString());
  assert.equal(zaiFailure({ error: { code: '1310', next_flush_time: '2026-11-04T00:00:00' } }).resetAt, null);
  assert.equal(zaiFailure({ error: { code: '1302' } }, 429, '30', 100000).resetAt, new Date(130000).toISOString());
});
import { chatRequest } from './api_chat.mjs';

test('the verified stable OpenCode branch sets only its actual Z.AI identity and affinity headers', () => {
  const profile = JSON.parse(readFileSync(new URL('../../shared/zai-client.json', import.meta.url)));
  const sessionId = 'ses_' + 'a'.repeat(64), headers = zaiHeaders({ ...profile, sessionId });
  assert.deepEqual(headers, { 'User-Agent': 'opencode/1.19.5', 'x-opencode-session-id': sessionId,
    'x-session-affinity': sessionId, 'X-Session-Id': sessionId });
  assert.equal(JSON.stringify(headers).includes('Studio'), false);
  assert.equal(headers['x-opencode-client'], undefined);
  assert.throws(() => zaiHeaders({ ...profile, sessionId, userAgent: 'opencode/1.19.5\r\nX-Key: value' }));
  assert.throws(() => zaiHeaders({ ...profile, sessionId: '../foreign' }));
  assert.throws(() => zaiHeaders({ ...profile, sessionId, referenceCommit: 'not verified' }));
});

test('GLM thinking, tool streaming and native-only fields follow the subscription contract', () => {
  const policy = { reasoning: 'effort', reasoningFacts: { mandatory: true }, selectedEffort: 'low' };
  const wire = zaiRequest({ model: 'glm-5.3', tools: [{ type: 'function', function: { name: 'own', strict: true, parameters: { type: 'object' } } }],
    parallel_tool_calls: true, service_tier: 'default', store: false, prompt_cache_key: 'local', reasoning_effort: 'low' }, policy);
  assert.deepEqual(wire.thinking, { type: 'enabled', clear_thinking: false });
  assert.equal(wire.reasoning_effort, 'low'); assert.equal(wire.tool_stream, true);
  assert.equal(wire.store, undefined); assert.equal(wire.tools[0].function.strict, undefined);
  assert.equal(wire.prompt_cache_key, undefined); assert.equal(wire.parallel_tool_calls, undefined);
  assert.throws(() => zaiRequest({ ...wire, parallel_tool_calls: false }, policy));
  assert.throws(() => zaiRequest({ ...wire, parallel_tool_calls: true }, { ...policy, selectedEffort: 'none' }));
  assert.doesNotThrow(() => zaiRequest({ ...wire, tools: [], parallel_tool_calls: false }, policy));
});

test('only explicitly image-capable user input accepts bounded embedded images', () => {
  const policy = { schema: 1, systemRole: 'system', reasoning: 'none', functionTools: true, streaming: true, imageInput: true };
  const input = { model: 'owned', tools: [], input: [{ type: 'message', role: 'user', content: [
    { type: 'input_text', text: 'Own image' }, { type: 'input_image', image_url: 'data:image/png;base64,aGVsbG8=' }]}],
    tool_choice: 'auto', parallel_tool_calls: true, stream: true, store: false };
  assert.equal(chatRequest(input, policy).messages[0].content[1].type, 'image_url');
  assert.throws(() => chatRequest(input, { ...policy, imageInput: false }));
  assert.throws(() => chatRequest({ ...input, input: [{ ...input.input[0], content: [{ type: 'input_image', image_url: 'https://foreign.invalid/image' }] }] }, policy));
});
