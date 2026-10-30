import test from 'node:test';
import assert from 'node:assert/strict';
import { ChatFault, ChatStream, chatRequest, CHAT_NATIVE_METADATA } from './api_chat.mjs';
import { routerSettings, routerHeaders, routerRequest, routerError, RouterOrigin } from './api_openrouter.mjs';

const policy = { schema: 1, systemRole: 'system', reasoning: 'none', functionTools: true, streaming: true };
const settings = routerSettings({ order: ['owned/provider'], only: ['owned/provider'], allowFallbacks: false,
  attribution: { url: 'https://example.test/owned-app', title: 'Owned fixture' } });
const request = () => chatRequest({ model: 'owned/requested-alias', tools: [{ type: 'function', name: 'studio_owned', strict: false, parameters: { type: 'object', properties: {} } }],
  input: [{ type: 'message', role: 'user', content: [{ type: 'input_text', text: 'Owned input.' }] }],
  stream: true, store: false, tool_choice: 'auto', parallel_tool_calls: true, reasoning: { effort: 'none' },
  include: ['reasoning.encrypted_content'], service_tier: 'default', prompt_cache_key: 'owned', client_metadata: { private: 'native-envelope' } }, policy);
const frame = value => Buffer.from('data: ' + JSON.stringify(value) + '\n\n');

test('OpenRouter fixed documented wire, explicit route/attribution and preserved full original history', () => {
  const native = request(), wire = routerRequest(native, settings, policy);
  assert.equal(Object.hasOwn(wire, 'store'), false); assert.equal(Object.hasOwn(wire, 'client_metadata'), false);
  assert.equal(Object.hasOwn(wire, 'include'), false); assert.equal(Object.hasOwn(wire, 'models'), false);
  assert.equal(wire[CHAT_NATIVE_METADATA].private, 'native-envelope');
  assert.equal(wire.model, 'owned/requested-alias'); assert.equal(wire.service_tier, 'default');
  assert.equal(wire.prompt_cache_key, 'owned'); assert.deepEqual(wire.messages, native.messages);
  assert.deepEqual(wire.provider, { require_parameters: true, allow_fallbacks: false, order: ['owned/provider'], only: ['owned/provider'] });
  assert.deepEqual(routerHeaders(settings, true), { 'X-OpenRouter-Metadata': 'enabled', 'HTTP-Referer': 'https://example.test/owned-app', 'X-OpenRouter-Title': 'Owned fixture' });
  assert.deepEqual(routerHeaders(routerSettings()), {});
  for (const value of [{ headers: { Authorization: 'foreign' } }, { allowFallbacks: 'yes' }, { only: ['x', 'x'] },
    { order: ['other'], only: ['allowed'] }, { order: ['https://foreign.invalid'] }, { order: ['own/../other'] },
    { attribution: { url: 'https://user:secret@example.test', title: 'Owned' } }, { attribution: { url: 'https://example.test', title: 'Owned\r\nHeader' } }]) {
    assert.throws(() => routerSettings(value), ChatFault);
  }
  assert.throws(() => routerRequest(native, settings, { ...policy, reasoning: 'effort' }), ChatFault);
});

test('reported model/backend are separate, numeric errors and invalid routing never release tool prefixes', () => {
  const origin = new RouterOrigin('owned/requested-alias', settings, 'fixture-only-secret'), events = [];
  const parser = new ChatStream(routerRequest(request(), settings, policy), event => events.push(event), { observe: value => origin.observe(value), errorCode: routerError });
  const head = { id: 'gen-owned', model: 'owned/reported-model', provider: 'Owned backend' };
  parser.push(frame({ ...head, choices: [{ index: 0, delta: { tool_calls: [{ index: 0, id: 'owned_call', function: { name: 'studio_owned', arguments: '{}' } }] }, finish_reason: 'tool_calls' }] }));
  parser.push(frame({ ...head, choices: [], usage: { prompt_tokens: 5, completion_tokens: 2, total_tokens: 7 }, openrouter_metadata: {
    requested: 'owned/requested-alias', strategy: 'direct', attempt: 1, summary: 'private-raw-summary-must-not-survive',
    endpoints: { available: [{ provider: 'Owned endpoint name', model: 'owned/endpoint-model', selected: true }] },
  } }));
  assert.equal(events.filter(v => v.type === 'response.output_item.done').length, 0);
  parser.push(Buffer.from('data: [DONE]\n\n')); parser.push(new Uint8Array(), true);
  const report = origin.report(parser, 1);
  assert.equal(report.reportedModel, 'owned/reported-model'); assert.equal(report.endpointModel, 'owned/endpoint-model');
  assert.equal(report.reportedBackend, 'Owned backend'); assert.equal(report.endpointBackend, 'Owned endpoint name');
  assert.equal(report.providerResponseId, 'gen-owned'); assert.match(report.localResponseId, /^studio_chat_/);
  assert.equal(report.usage.total_tokens, 7); assert.equal(JSON.stringify(report).includes('private-raw-summary'), false);
  for (const [code, expected] of [[401, 'invalid_api_key'], [402, 'api_account_required'], [403, 'api_access_denied'], [429, 'rate_limit_exceeded'], [503, 'api_service_unavailable']]) {
    const values = [], current = new ChatStream(request(), event => values.push(event), { errorCode: routerError });
    assert.throws(() => current.push(frame({ error: { code, message: 'fixture-only-secret' } })), error => error.code === expected);
    assert.equal(values.filter(v => v.type === 'response.output_item.done').length, 0);
  }
  const blocked = new RouterOrigin('owned/requested-alias', settings, 'fixture-only-secret');
  assert.throws(() => blocked.observe({ openrouter_metadata: { attempt: 2 } }), ChatFault);
  const missing = new RouterOrigin('owned/requested-alias', settings, 'fixture-only-secret').report({ id: 'local', finishReason: 'stop' }, 1);
  assert.equal(missing.reportedModel, null); assert.equal(missing.reportedBackend, null); assert.equal(missing.usage, null);
});
