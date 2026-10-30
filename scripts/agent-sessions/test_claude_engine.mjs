import test from 'node:test';
import assert from 'node:assert/strict';
import { ClaudeControl, messageIdentity } from './claude_engine.mjs';

const request = '2bb35fc7-5779-4148-a276-4f07df4978ea', session = '527d8438-8df3-4664-8057-6fbac8b79bc9';
test('native SDK/session/provider/tool identities remain distinct, with no invented turn ID', () => {
  const message = { type: 'assistant', uuid: 'native-sdk-message', session_id: session, parent_tool_use_id: null,
    message: { id: 'msg_owned_provider', content: [{ type: 'tool_use', id: 'toolu_owned', name: 'mcp__studio__write_file', input: { path: 'own' } }] } };
  const value = messageIdentity(message, request);
  assert.equal(value.studioRequestId, request); assert.equal(value.nativeSessionId, session);
  assert.equal(value.nativeMessageId, 'native-sdk-message'); assert.equal(value.providerMessageId, 'msg_owned_provider');
  assert.equal(value.nativeTurnId, null); assert.deepEqual(value.toolUses, [{ id: 'toolu_owned', name: 'mcp__studio__write_file' }]);
  assert.equal(messageIdentity({ type: 'user', session_id: session, message: { content: 'Owned text' } }, request).supportedType, true);
  assert.equal(messageIdentity({ type: 'future-event', own: true }, request).supportedType, false);
  assert.throws(() => messageIdentity({ ...message, session_id: 'foreign-invalid-session' }, request));
  assert.throws(() => messageIdentity({ type: 'assistant', text: 'x'.repeat(524289) }, request));
});

test('metadata control has empty input, isolated environment, no tools or model-turn command', async () => {
  let configured, finish; const closed = new Promise(resolve => { finish = resolve; });
  const fake = { BUILTIN_TOOL_NAMES: ['Bash', 'Read'], query: values => {
    configured = values;
    // eslint-disable-next-line require-yield -- the metadata fixture emits no model messages.
    return { async *[Symbol.asyncIterator]() { await closed; }, initializationResult: async () => ({ claude_code_version: '2.1.312' }),
      supportedModels: async () => [], accountInfo: async () => ({ tokenSource: 'none' }), interrupt: async () => ({ interrupted: false }),
      usage_EXPERIMENTAL_MAY_CHANGE_DO_NOT_RELY_ON_THIS_API_YET: async options => { assert.deepEqual(options, { skipBehaviors: true }); return { rate_limits_available: false, rate_limits: null }; }, close: () => finish() };
  } };
  const control = new ClaudeControl(fake, { executable: '/own/claude', cwd: '/own/empty', home: '/own/home', config: '/own/config' }, request);
  try {
    assert.equal((await control.control('initialize')).value.claude_code_version, '2.1.312');
    assert.deepEqual(configured.options.tools, []); assert.deepEqual(configured.options.settingSources, []);
    assert.deepEqual(configured.options.skills, []); assert.deepEqual(configured.options.plugins, []);
    assert.equal(configured.options.env.ANTHROPIC_API_KEY, undefined); assert.equal(configured.options.env.CLAUDE_CODE_OAUTH_TOKEN, undefined);
    assert.equal(configured.options.env.HTTPS_PROXY, undefined); assert.equal(configured.options.env.DISABLE_AUTOUPDATER, '1'); assert.equal(configured.options.env.HOME, '/own/home');
    assert.equal(configured.options.env.CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC, undefined);
    assert.equal((await control.control('usage')).value.rate_limits, null);
    assert.equal((await configured.options.canUseTool()).behavior, 'deny');
    await assert.rejects(control.control('turn/start')); await assert.rejects(control.control('thread/resume'));
    assert.equal((await control.control('account')).value.tokenSource, 'none');
  } finally { await control.close(); }
  assert.equal((await configured.prompt[Symbol.asyncIterator]().next()).done, true);
  await assert.rejects(control.control('models'));
});

test('native stream binding failure closes the original query instead of inventing a replacement', async () => {
  let closes = 0;
  const fake = { BUILTIN_TOOL_NAMES: [], query: () => ({ async *[Symbol.asyncIterator]() {
    yield { type: 'system', subtype: 'init', session_id: session };
    yield { type: 'system', subtype: 'init', session_id: '4ec7298c-4656-4c6e-8eb4-dc6255d8ce48' };
  }, close() { closes++; } }) };
  const events = [], control = new ClaudeControl(fake, {}, request, event => events.push(event));
  await control.pump; assert.equal(events.length, 1); assert.equal(control.failed, true); assert.equal(closes, 1);
  await assert.rejects(control.control('models')); await control.close();
});
