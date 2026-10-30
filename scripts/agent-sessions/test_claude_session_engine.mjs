import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { ClaudeSessionEngine } from './claude_session_engine.mjs';
import { publicFrame } from './claude_session_io.mjs';

class Feed {
  constructor() { this.values = []; this.waiter = null; this.closed = false; }
  emit(value) { this.values.push(value); this.waiter?.(); this.waiter = null; }
  close() { this.closed = true; this.waiter?.(); this.waiter = null; }
  async *[Symbol.asyncIterator]() {
    while (!this.closed) {
      if (!this.values.length) await new Promise(resolve => { this.waiter = resolve; });
      if (this.closed) return;
      if (this.values.length) yield this.values.shift();
    }
  }
}
function fixture(changes = {}, engineOptions = {}) {
  const frozen = { providerId: randomUUID(), studioSessionId: randomUUID(), nativeSessionId: randomUUID(), runId: randomUUID(),
    requestId: randomUUID(), ownerId: randomUUID(), ownerType: 'project', toolProfile: 'studio-tools-v14', model: 'owned-model' };
  const feed = new Feed(), sent = [], received = [], grants = [];
  let options, interrupts = 0;
  const sdk = { BUILTIN_TOOL_NAMES: ['Read', 'Bash', 'Agent', 'CronCreate'], query: value => {
    options = value.options;
    void (async () => { for await (const input of value.prompt) sent.push(input); })();
    return Object.assign(feed, { initializationResult: async () => ({ claude_code_version: '2.1.312', hooks_applied: true }),
      mcpServerStatus: async () => [{ name: 'studio', status: 'connected', source: 'dynamic', tools: [{ name: 'read_file' }] }],
      accountInfo: async () => ({ tokenSource: 'claude.ai', apiProvider: 'firstParty', subscriptionType: 'pro' }),
      interrupt: async () => { interrupts++; if (sent.length) feed.emit({ type: 'result', subtype: 'error_during_execution',
        uuid: randomUUID(), session_id: frozen.nativeSessionId, is_error: true }); } });
  } };
  const host = { authorize: async value => { grants.push(value); return true; }, receive: async value => received.push(value),
    admit: async () => ({ allowed: false }), closeAdmission: async () => {}, ...changes };
  const engine = new ClaudeSessionEngine(sdk, { mode: 'new', cwd: '/inference', home: '/home/studio', config: '/config',
    executable: '/pinned/claude', tools: ['read_file'], systemPrompt: 'Owned Studio instructions.', ...engineOptions }, frozen, host);
  return { frozen, feed, sent, received, grants, engine, options, interrupts: () => interrupts };
}
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
await test('canonical native model and selected effort cannot silently change', async () => {
  const f = fixture({ admit: async ({ binding }) => admission(binding) }, { resolvedModel: 'owned-model', effort: 'high' });
  try {
    await f.engine.initialize(); await f.engine.send('Own explicit input'); await tick();
    assert.equal(f.options.effort, 'high'); assert.equal(f.options.env.CLAUDE_CODE_DISABLE_LEGACY_MODEL_REMAP, '1');
    const tool = { hook_event_name: 'PreToolUse', session_id: f.frozen.nativeSessionId, tool_name: 'mcp__studio__read_file',
      tool_use_id: 'own-model-bound-tool', tool_input: { path: 'own.c' }, mcp_server: { name: 'studio', source: 'dynamic' } };
    assert.equal((await f.engine.beforeTool(tool)).hookSpecificOutput.permissionDecision, 'deny');
    f.feed.emit({ type: 'stream_event', session_id: f.frozen.nativeSessionId, event: { type: 'message_start', message: { id: 'own-provider-message', model: 'unrequested-model' } } });
    await tick(); assert.equal(f.engine.state, 'unconfirmed'); assert.equal(f.grants.length, 0);
  } finally { await f.engine.close(); }
});
await test('display projection excludes raw thinking, signatures, images and private provider errors', () => {
  const native = { type: 'assistant', uuid: randomUUID(), session_id: randomUUID(), message: { id: 'owned-message',
    content: [{ type: 'thinking', thinking: 'private reasoning', signature: 'private signature' },
      { type: 'text', text: 'Visible original text.' }, { type: 'image', source: { data: 'private image bytes' } }] } };
  assert.deepEqual(publicFrame(native).message.content, [{ type: 'text', text: 'Visible original text.' }]);
  assert.equal(publicFrame({ type: 'user', message: { content: [{ type: 'image', source: { data: 'private image bytes' } }] } }), null);
  const result = publicFrame({ type: 'result', subtype: 'error_during_execution', errors: ['private provider response'], usage: { input_tokens: 7 } });
  assert.equal(result.errors, undefined); assert.deepEqual(result.usage, { input_tokens: 7 });
});
function admission(binding) { return { allowed: true, extraUsageDisabled: true, providerId: binding.providerId,
  nativeSessionId: binding.nativeSessionId, model: binding.model, admissionId: randomUUID(), expiresAt: Date.now() + 10000,
  authMethod: 'claude.ai', apiProvider: 'firstParty', subscriptionType: 'pro' }; }

await test('idle initialization submits no model message and cannot bypass the subscription/overage gate', async () => {
  const f = fixture();
  try {
    await f.engine.initialize(); await tick(); assert.equal(f.sent.length, 0);
    assert.deepEqual(f.options.tools, []); assert.deepEqual(f.options.settingSources, []);
    assert.equal(f.options.settings.precomputeCompactionEnabled, false);
    assert.deepEqual(f.options.disallowedTools, ['Read', 'Bash', 'Agent', 'CronCreate']);
    assert.equal(f.options.env.ANTHROPIC_API_KEY, undefined); assert.equal(f.options.env.ANTHROPIC_AUTH_TOKEN, undefined);
    assert.equal(f.options.env.CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC, undefined);
    assert.equal(f.options.env.CLAUDE_CODE_DISABLE_AUTO_MEMORY, '1'); assert.equal(f.options.env.CLAUDE_CODE_DISABLE_BACKGROUND_TASKS, '1');
    assert.equal(f.options.env.CLAUDE_CODE_DISABLE_CRON, '1'); assert.equal(f.options.sessionId, f.frozen.nativeSessionId);
    assert.equal(f.options.persistSession, true); assert.equal(f.options.mcpServers.studio.command, '/usr/bin/python3');
    await assert.rejects(f.engine.send('Explicit own input'), /No model prompt/); assert.equal(f.sent.length, 0);
  } finally { await f.engine.close(); }
});

await test('native session/tool IDs, exact grants, original text and one explicit send stay bound', async () => {
  const f = fixture({ admit: async ({ binding }) => admission(binding) });
  try {
    await f.engine.initialize(); await f.engine.send('Own literal /command @file'); await tick();
    assert.equal(f.sent.length, 1); assert.equal(f.sent[0].uuid, f.frozen.requestId);
    assert.equal(f.sent[0].session_id, f.frozen.nativeSessionId); assert.equal(f.sent[0].client_composed, true);
    assert.deepEqual(f.sent[0].origin, { kind: 'human' }); assert.equal(f.sent[0].message.content, 'Own literal /command @file');
    await assert.rejects(f.engine.send('Second send'), /one explicit/);
    const input = { hook_event_name: 'PreToolUse', session_id: f.frozen.nativeSessionId, tool_name: 'mcp__studio__read_file',
      tool_use_id: 'native-tool-001', tool_input: { path: 'own.c' }, mcp_server: { name: 'studio', source: 'dynamic' } };
    assert.equal((await f.options.hooks.PreToolUse[0].hooks[0](input)).hookSpecificOutput.permissionDecision, 'allow');
    assert.equal(f.grants[0].nativeToolUseId, 'native-tool-001'); assert.equal(f.grants[0].binding.runId, f.frozen.runId);
    const details = { toolUseID: 'native-tool-001', mcpServer: { name: 'studio', source: 'dynamic' } };
    assert.equal((await f.options.canUseTool(input.tool_name, input.tool_input, details)).behavior, 'allow');
    for (const change of [{ session_id: randomUUID() }, { tool_name: 'Bash' }, { mcp_server: { name: 'studio', source: 'plugin' } }, { agent_id: 'foreign-child' }]) {
      assert.equal((await f.engine.beforeTool({ ...input, ...change })).hookSpecificOutput.permissionDecision, 'deny');
    }
    assert.equal((await f.options.canUseTool('mcp__studio__read_file', { path: 'different.c' }, details)).behavior, 'deny');
    f.feed.emit({ type: 'assistant', session_id: f.frozen.nativeSessionId, uuid: randomUUID(), parent_tool_use_id: null,
      message: { id: 'provider-msg-001', content: [{ type: 'text', text: 'Own answer' }] } });
    await tick(); assert.equal(f.received[0].identity.providerMessageId, 'provider-msg-001'); assert.equal(f.received[0].identity.nativeTurnId, null);
    await f.engine.interrupt();
    assert.equal((await f.engine.beforeTool(input)).hookSpecificOutput.permissionDecision, 'deny');
    assert.equal(f.interrupts(), 1);
  } finally { await f.engine.close(); }
});

await test('Stop wins against pending admission; foreign/rescue turns fail without replay', async () => {
  let release;
  const f = fixture({ admit: ({ binding }) => new Promise(resolve => { release = () => resolve(admission(binding)); }) });
  try {
    await f.engine.initialize(); const sending = f.engine.send('Must stay unsent'); await tick();
    await f.engine.interrupt(); release(); await assert.rejects(sending); await tick(); assert.equal(f.sent.length, 0);
  } finally { await f.engine.close(); }
  const g = fixture();
  try {
    await g.engine.initialize();
    g.feed.emit({ type: 'assistant', session_id: randomUUID(), uuid: randomUUID(), message: { id: 'unbound', content: [] }, resume_reason: 'rescue' });
    await tick(); assert.equal(g.engine.state, 'unconfirmed'); assert.equal(g.sent.length, 0); assert.equal(g.received.length, 0);
  } finally { await g.engine.close(); }
});
