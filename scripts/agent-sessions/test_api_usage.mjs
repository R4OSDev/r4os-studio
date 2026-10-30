import test from 'node:test';
import assert from 'node:assert/strict';
import { reportedUsage, ResponsesUsage } from './api_usage.mjs';

test('only explicit provider counters are observed; absent fields stay absent', () => {
  assert.equal(reportedUsage(undefined), null); assert.equal(reportedUsage({}), null);
  assert.deepEqual(reportedUsage({ input_tokens: 5 }), { input_tokens: 5 });
  assert.deepEqual(reportedUsage({ input_tokens: 5, output_tokens: 2, total_tokens: 7,
    input_tokens_details: { cached_tokens: 1 }, output_tokens_details: { reasoning_tokens: 0 }, unknown: 'private' }),
  { input_tokens: 5, output_tokens: 2, total_tokens: 7, cached_input_tokens: 1, reasoning_output_tokens: 0 });
  assert.equal(reportedUsage({ total_tokens: -1 }), null);
  assert.equal(reportedUsage({ total_tokens: Number.MAX_SAFE_INTEGER + 1 }), null);
});

test('Responses usage observation tolerates split UTF8/SSE without altering the input stream', () => {
  const output = [], observer = new ResponsesUsage((responseId, usage) => output.push({ responseId, usage }));
  const bytes = Buffer.from(': owned\r\nevent: response.output_text.delta\r\ndata: {"type":"response.output_text.delta","delta":"🤖"}\r\n\r\n'
    + 'event: response.completed\r\ndata: {"type":"response.completed","response":{"id":"owned-response","usage":{"input_tokens":5}}}\r\n\r\n');
  for (let i = 0; i < bytes.length; i += 3) observer.push(bytes.subarray(i, i + 3));
  observer.push(new Uint8Array(), true);
  assert.deepEqual(output, [{ responseId: 'owned-response', usage: { input_tokens: 5 } }]);
  assert.equal(observer.failed, false);
  const missing = []; const unknown = new ResponsesUsage((id, usage) => missing.push({ id, usage }));
  unknown.push(Buffer.from('data: {"type":"response.completed","response":{"id":"owned-no-usage"}}\n\n'));
  assert.deepEqual(missing, [{ id: 'owned-no-usage', usage: null }]);
  for (const bytes of [Buffer.from('data: {bad}\n\n'), Buffer.from('data: ' + 'x'.repeat(524289)), Buffer.from([255])]) {
    const broken = new ResponsesUsage(() => assert.fail('An invalid observation must not invent usage'));
    assert.doesNotThrow(() => broken.push(bytes, true)); assert.equal(broken.failed, true);
  }
});
