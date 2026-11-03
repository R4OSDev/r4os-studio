import assert from 'node:assert/strict';
import test from 'node:test';
import { modelFacts } from './api_model_metadata.mjs';

const binding = { kind: 'openrouter' };
const entry = reasoning => ({ id: 'owned/reasoner', context_length: 1048576,
  top_provider: { max_completion_tokens: 943718 }, architecture: { input_modalities: ['text'], output_modalities: ['text'] },
  supported_parameters: ['tools', 'tool_choice', 'reasoning'], reasoning });
test('imports mandatory reasoning, max and actual model defaults', () => {
  const reasoning = { mandatory: true, supported_efforts: ['max', 'xhigh', 'high', 'medium', 'low', 'minimal'], default_effort: 'max' };
  const model = modelFacts(entry(reasoning), binding);
  assert.deepEqual(model.reasoning, reasoning); assert.deepEqual(model.efforts, reasoning.supported_efforts);
  assert.equal(model.defaultEffort, 'max'); assert.equal(model.contextWindow, 1048576);
  assert.equal(model.capabilities.reasoning, 'supported'); assert.equal(model.maxOutputTokens, 943718);
});
test('omitted, null and explicit off remain distinct; defaults are not guessed', () => {
  const implicit = modelFacts(entry({ mandatory: true, default_enabled: true }), binding);
  assert.deepEqual(implicit.reasoning, { mandatory: true, default_enabled: true });
  assert.deepEqual(implicit.efforts, ['']); assert.equal(implicit.defaultEffort, '');
  const all = modelFacts(entry({ supported_efforts: null, default_enabled: false, default_effort: null }), binding);
  assert.deepEqual(all.reasoning, { supported_efforts: null, default_enabled: false, default_effort: null });
  assert.ok(all.efforts.includes('none')); assert.ok(all.efforts.includes('max')); assert.equal(all.defaultEffort, '');
  const off = modelFacts(entry({ supported_efforts: ['none', 'low'], default_effort: 'none' }), binding);
  assert.equal(off.defaultEffort, 'none');
  const optional = modelFacts(entry({ supported_efforts: ['low', 'max'], default_effort: 'max', default_enabled: false }), binding);
  assert.equal(optional.defaultEffort, ''); assert.equal(optional.efforts[0], '');
  const generic = modelFacts(entry({ mandatory: true }), { kind: 'local' });
  assert.equal(generic.capabilities.reasoning, 'unknown'); assert.equal(generic.reasoning, undefined);
});
test('invalid or contradictory facts never establish an available model', () => {
  for (const reasoning of [{ mandatory: 'true' }, { mandatory: true, default_effort: 'none' },
    { mandatory: true, default_enabled: false }, { supported_efforts: ['max', 'max'] }, { supported_efforts: ['invented'] }]) {
    assert.equal(modelFacts(entry(reasoning), binding), null);
  }
});
