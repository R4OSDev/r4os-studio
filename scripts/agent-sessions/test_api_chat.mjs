import assert from 'node:assert/strict';
import test from 'node:test';
import { CHAT_NATIVE_METADATA, ChatFault, ChatStream, chatRequest } from './api_chat.mjs';

const policy = { schema: 1, systemRole: 'system', reasoning: 'none', functionTools: true, streaming: true };
const tools = ['studio_alpha', 'studio_beta'].map(name => ({ type: 'function', name,
  description: 'Owned protocol fixture', strict: false, parameters: { type: 'object', properties: {} } }));
const base = () => ({ model: 'owned', input: [{ type: 'message', role: 'developer', content: [{ type: 'input_text', text: 'Own instructions.' }] },
  { type: 'message', role: 'user', content: [{ type: 'input_text', text: 'Own request.' }] }], tools,
tool_choice: 'auto', parallel_tool_calls: true, reasoning: { effort: 'none' }, store: false, stream: true,
include: ['reasoning.encrypted_content'], prompt_cache_key: 'own-cache-key', client_metadata: { native: 'x'.repeat(900) } });
const chunk = (delta = {}, finish_reason = null) => ({ id: 'chatcmpl_fixture', choices: [{ index: 0, delta, finish_reason }] });
const frame = value => 'data: ' + JSON.stringify(value) + '\r\n\r\n';
function stream() {
  const events = [], wire = chatRequest(base(), policy);
  return { events, parser: new ChatStream(wire, event => events.push(event)) };
}
const released = events => events.filter(event => event.type === 'response.output_item.done' && event.item.type === 'function_call');

test('full instruction/text/tool history, original IDs and qualified parameters survive translation', () => {
  const request = base();
  request.input.push({ type: 'function_call', call_id: 'original_a', name: 'studio_alpha', arguments: '{"path":"owned-a"}' },
    { type: 'function_call', call_id: 'original_b', name: 'studio_beta', arguments: '{"path":"owned-b"}' },
    { type: 'function_call_output', call_id: 'original_b', output: [{ type: 'input_text', text: 'B acknowledged.' }] },
    { type: 'function_call_output', call_id: 'original_a', output: 'A acknowledged.' });
  const wire = chatRequest(request, policy);
  assert.deepEqual(wire.messages.map(message => message.role), ['system', 'user', 'assistant', 'tool', 'tool']);
  assert.deepEqual(wire.messages[2].tool_calls.map(call => call.id), ['original_a', 'original_b']);
  assert.equal(wire.messages[3].tool_call_id, 'original_b');
  assert.deepEqual(wire.messages[3].content, [{ type: 'text', text: 'B acknowledged.' }]);
  assert.equal(wire.messages[4].content, 'A acknowledged.');
  assert.equal(wire.store, false); assert.equal(wire.prompt_cache_key, 'own-cache-key');
  assert.equal(wire[CHAT_NATIVE_METADATA].native.length, 900);
  assert.equal(JSON.stringify(wire).includes('client_metadata'), false);
  request.reasoning.effort = 'low';
  assert.equal(chatRequest(request, { ...policy, reasoning: 'effort' }).reasoning_effort, 'low');
  assert.throws(() => chatRequest(request, policy), ChatFault);
  request.reasoning.effort = 'none'; request.input.push({ type: 'reasoning', encrypted_content: 'opaque' });
  assert.throws(() => chatRequest(request, policy), ChatFault);
  const image = base(); image.input[1].content.push({ type: 'input_image', image_url: 'data:owned' });
  assert.throws(() => chatRequest(image, policy), ChatFault);
});

test('fragmented UTF8/UTF16, CRLF/comments, interleaved arguments and repeated final usage choice', () => {
  const { parser, events } = stream();
  const prefix = ': owned heartbeat\r\n' + frame(chunk({ role: 'assistant', content: 'A' }))
    + frame(chunk({ content: '\ud83e' })) + frame(chunk({ content: '\udd16B' }))
    + frame(chunk({ tool_calls: [{ index: 0, id: 'original_a', type: 'function', function: { name: 'studio_al', arguments: '{"a":' } }] }))
    + frame(chunk({ tool_calls: [{ index: 1, id: 'original_b', type: 'function', function: { name: 'studio_', arguments: '{"b":"' } }] }))
    + frame(chunk({ tool_calls: [{ index: 1, function: { name: 'beta', arguments: '🤖"}' } }, { index: 0, function: { name: 'pha', arguments: '1}' } }] }))
    + frame(chunk({}, 'tool_calls'))
    + frame({ ...chunk({ role: 'assistant', content: '' }, 'tool_calls'), usage: { prompt_tokens: 12, completion_tokens: 4,
      total_tokens: 16, prompt_tokens_details: { cached_tokens: 2 }, completion_tokens_details: { reasoning_tokens: 0 } } });
  const encoded = Buffer.from(prefix);
  for (let i = 0; i < encoded.length; i += 3) parser.push(encoded.subarray(i, i + 3));
  assert.equal(released(events).length, 0);
  assert.equal(events.filter(event => event.type === 'response.output_text.delta').map(event => event.delta).join(''), 'A🤖B');
  parser.push(Buffer.from('data: [DONE]\r\n\r\n')); parser.push(new Uint8Array(), true);
  assert.deepEqual(released(events).map(event => [event.item.call_id, JSON.parse(event.item.arguments)]),
    [['original_a', { a: 1 }], ['original_b', { b: '🤖' }]]);
  const completed = events.at(-1); assert.equal(completed.type, 'response.completed');
  assert.deepEqual(completed.response.usage, { input_tokens: 12, output_tokens: 4, total_tokens: 16,
    input_tokens_details: { cached_tokens: 2 }, output_tokens_details: { reasoning_tokens: 0 } });
  assert.match(completed.response.id, /^studio_chat_/);
  assert.equal(completed.response.metadata.provider_response_id, 'chatcmpl_fixture');
  assert.equal(completed.response.metadata.provider_finish_reason, 'tool_calls');
  assert.equal(completed.response.metadata.studio_native_metadata.native.length, 900);
});

test('lost final, malformed parallel arguments/IDs and bad usage never release a tool prefix', () => {
  for (const variant of ['lost', 'arguments', 'duplicate', 'usage', 'changed-provider']) {
    const { parser, events } = stream();
    parser.push(Buffer.from(frame(chunk({ tool_calls: [
      { index: 0, id: 'original_a', type: 'function', function: { name: 'studio_alpha', arguments: '{}' } },
      { index: 1, id: variant === 'duplicate' ? 'original_a' : 'original_b', type: 'function',
        function: { name: 'studio_beta', arguments: variant === 'arguments' ? '{"incomplete":' : '{}' } },
    ] })) + frame(chunk({}, 'tool_calls'))));
    if (variant === 'lost') assert.throws(() => parser.push(new Uint8Array(), true), ChatFault);
    else if (variant === 'usage') assert.throws(() => parser.push(Buffer.from(frame({ id: 'chatcmpl_fixture', choices: [], usage: { prompt_tokens: -1 } }))), ChatFault);
    else if (variant === 'changed-provider') assert.throws(() => parser.push(Buffer.from(frame({ id: 'foreign', choices: [] }))), ChatFault);
    else assert.throws(() => parser.push(Buffer.from('data: [DONE]\n\n')), ChatFault);
    assert.equal(released(events).length, 0, variant);
  }
});

test('incomplete finish and missing usage stay explicit, oversized event/arguments are bounded', () => {
  for (const reason of ['length', 'content_filter']) {
    const { parser, events } = stream();
    parser.push(Buffer.from(frame(chunk({ content: 'Owned partial text.' }, reason)) + frame({ id: 'chatcmpl_fixture', choices: [],
      usage: { prompt_tokens: 10, completion_tokens: 2, total_tokens: 12 } }) + 'data: [DONE]\n\n'));
    parser.push(new Uint8Array(), true);
    assert.equal(events.at(-1).type, 'response.incomplete'); assert.equal(events.at(-1).response.usage.total_tokens, 12);
    assert.equal(events.at(-1).response.incomplete_details.reason, reason === 'length' ? 'max_output_tokens' : 'studio_chat_content_filter');
    assert.equal(released(events).length, 0);
  }
  const normal = stream(); normal.parser.push(Buffer.from(frame(chunk({ content: 'Owned complete.' }, 'stop')) + 'data: [DONE]\n\n'));
  assert.equal(Object.hasOwn(normal.events.at(-1).response, 'usage'), false);
  const large = stream(); assert.throws(() => large.parser.push(Buffer.from('data: ' + 'x'.repeat(524289))), ChatFault);
  const args = stream(); assert.throws(() => args.parser.push(Buffer.from(frame(chunk({ tool_calls: [{ index: 0, id: 'a',
    function: { name: 'studio_alpha', arguments: 'x'.repeat(131073) } }] })))), ChatFault);
  const quota = stream(); assert.throws(() => quota.parser.push(Buffer.from(frame({ error: { code: 'insufficient_quota',
    message: 'Private provider text must not escape.' } }))), error => error instanceof ChatFault && error.code === 'insufficient_quota');
  assert.equal(released(quota.events).length, 0);
});
