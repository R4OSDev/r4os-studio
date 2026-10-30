import test from 'node:test';
import assert from 'node:assert/strict';
import { localRequest, serverProfile } from './api_local.mjs';

const original = () => ({ model: 'exact:owned-model', stream: true, store: false,
  tool_choice: 'auto', parallel_tool_calls: true, reasoning: { effort: 'none' },
  include: ['reasoning.encrypted_content'], service_tier: 'default', prompt_cache_key: 'owned-cache',
  client_metadata: { private: 'native-local-only' },
  tools: [{ type: 'function', name: 'own_write', description: 'Own fixture', parameters: { type: 'object' }, strict: false }],
  input: [{ type: 'message', role: 'developer', content: [{ type: 'input_text', text: 'Owned instructions' }] },
    { type: 'message', role: 'user', content: [{ type: 'input_text', text: 'Owned request' }] },
    { type: 'function_call', call_id: 'original_call', name: 'own_write', arguments: '{"x":1}' },
    { type: 'function_call_output', call_id: 'original_call', output: 'Original acknowledged result' }] });

test('named server wire scope preserves exact complete history and tool receipts without native telemetry', () => {
  for (const server of ['ollama', 'lm-studio']) for (const protocol of ['responses', 'chat-completions']) {
    const value = original(), before = JSON.stringify(value), request = localRequest(value, server, protocol);
    assert.equal(JSON.stringify(value), before);
    assert.ok(!JSON.stringify(request).includes('native-local-only'));
    assert.equal(request.model, value.model); assert.equal(request.stream, true);
    if (protocol === 'responses') {
      assert.deepEqual(request.input.slice(1), value.input.slice(1));
      assert.equal(request.input[0].role, 'system'); assert.deepEqual(request.tools, value.tools);
      assert.equal(request.store, server === 'lm-studio' ? false : undefined);
    } else {
      assert.equal(request.messages[0].role, 'system');
      assert.equal(request.messages[2].tool_calls[0].id, 'original_call');
      assert.equal(request.messages[3].tool_call_id, 'original_call');
      assert.equal(request.messages[3].content, 'Original acknowledged result');
      assert.equal(request.store, undefined); assert.deepEqual(request.stream_options, { include_usage: true });
    }
    assert.equal(request.previous_response_id, undefined); assert.equal(request.conversation, undefined);
    assert.equal(request.reasoning, undefined); assert.equal(request.client_metadata, undefined);
  }
});

test('unknown profiles, forced controls, opaque history, missing receipts and unsupported tools are refused', () => {
  for (const value of [null, {}, 'Ollama', '', 'other']) assert.throws(() => serverProfile(value));
  for (const server of ['ollama', 'lm-studio']) for (const protocol of ['responses', 'chat-completions']) {
    for (const patch of [{ tool_choice: 'required' }, { parallel_tool_calls: false }, { reasoning: { effort: 'low' } },
      { previous_response_id: 'remote-state' }, { truncation: 'auto' }, { temperature: .2 },
      { tools: [{ type: 'web_search' }] }, { input: [{ type: 'reasoning', encrypted_content: 'opaque' }] },
      { input: [{ type: 'function_call_output', call_id: 'missing', output: 'unbound' }] }]) {
      assert.throws(() => localRequest({ ...original(), ...patch }, server, protocol));
    }
    const dual = original(); dual.input.unshift({ type: 'message', role: 'system', content: 'Different priority' });
    assert.throws(() => localRequest(dual, server, protocol));
  }
});
