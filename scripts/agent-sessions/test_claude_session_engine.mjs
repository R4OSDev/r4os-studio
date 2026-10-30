import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { ClaudeSessionEngine, GOAL_CONTINUE_TEXT } from './claude_session_engine.mjs';
import { publicFrame } from './claude_session_io.mjs';
import { createHash } from 'node:crypto';
import { contentDigest, INPUT_PROFILE } from './claude_content.mjs';

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
  if (typeof engineOptions.frozenInput === 'function') engineOptions = { ...engineOptions, frozenInput: engineOptions.frozenInput(frozen.requestId) };
  if (engineOptions.goal === true) engineOptions = { ...engineOptions,
    goal: { executionId: frozen.requestId, maxSteps: 8, maxActiveSeconds: 900 },
    requireInputReceipt: true, tools: ['read_file', 'report_goal'] };
  const feed = new Feed(), sent = [], received = [], grants = [];
  let options, interrupts = 0;
  const sdk = { BUILTIN_TOOL_NAMES: ['Read', 'Bash', 'Agent', 'CronCreate'], query: value => {
    options = value.options;
    void (async () => { for await (const input of value.prompt) sent.push(input); })();
    return Object.assign(feed, { initializationResult: async () => ({ claude_code_version: '2.1.312', hooks_applied: true }),
      mcpServerStatus: async () => [{ name: 'studio', status: 'connected', source: 'dynamic', tools: (engineOptions.tools ?? ['read_file']).map(name => ({ name })) }],
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
function echo(f, input) {
  f.feed.emit({ type: 'user', isReplay: true, uuid: input.uuid, session_id: f.frozen.nativeSessionId,
    message: { role: 'user', content: input.message.content } });
}
const liveOptions = { requireInputReceipt: true, resolvedModel: 'owned-model', liveGoalPreparation: true, tools: ['read_file','report_goal'] };
await test('live Goal arms without input and begins after the original result in the same query', async () => {
  let admissions = 0;
  const f = fixture({ admit: async ({ binding }) => { admissions++; return admission(binding); } }, liveOptions);
  try {
    const contract = { executionId: randomUUID(), objective: 'Original separately accepted live objective', maxSteps: 8, maxActiveSeconds: 900 };
    await f.engine.initialize(); assert.throws(() => f.engine.armGoal(contract)); // No original submitted input.
    await f.engine.send('Original ordinary source'); await tick();
    const report = { hook_event_name: 'PreToolUse', session_id: f.frozen.nativeSessionId, tool_name: 'mcp__studio__report_goal',
      tool_use_id: 'own-live-goal-report', tool_input: { status: 'complete', reason: 'Original check complete.' }, mcp_server: { name: 'studio', source: 'dynamic' } };
    assert.equal((await f.engine.beforeTool(report)).hookSpecificOutput.permissionDecision, 'deny');
    const armed = f.engine.armGoal(contract); assert.equal(armed.state, 'waiting');
    assert.equal(f.engine.inputAccepted, false); // Arming is intent, never input acceptance.
    assert.deepEqual(f.engine.armGoal(contract), armed); assert.throws(() => f.engine.armGoal({ ...contract, objective: 'Changed goal' }));
    await assert.rejects(f.engine.beginGoal(contract.executionId)); assert.equal(f.sent.length, 1); assert.equal(admissions, 1);
    echo(f, f.sent[0]); await tick();
    const sourceResult = randomUUID(); f.feed.emit({ type: 'result', uuid: sourceResult, session_id: f.frozen.nativeSessionId, subtype: 'success', is_error: false }); await tick();
    assert.equal(f.engine.state, 'between'); assert.equal(f.sent.length, 1); assert.equal(f.engine.goalStartedAt, null);
    await f.engine.beginGoal(contract.executionId); await tick();
    assert.equal(admissions, 2); assert.equal(f.sent.length, 2);
    assert.ok(f.sent[1].message.content.startsWith('STUDIO GOAL ACTIVATION\nPlay execution: ' + contract.executionId + '\n'));
    assert.ok(f.sent[1].message.content.endsWith('Saved objective:\n' + contract.objective));
    assert.equal(f.sent[1].uuid, contract.executionId); assert.equal(f.sent[1].origin.kind, 'human');
    assert.equal(f.sent[1].session_id, f.sent[0].session_id); assert.equal(f.engine.binding.requestId, f.frozen.requestId);
    assert.equal(f.engine.stepCount, 1); assert.equal(f.engine.modelObserved, false); assert.equal(f.engine.goalStartedAt, null);
    echo(f, f.sent[1]); await tick(); assert.notEqual(f.engine.goalStartedAt, null);
    assert.equal((await f.engine.beforeTool(report)).hookSpecificOutput.permissionDecision, 'deny');
    f.feed.emit({ type: 'stream_event', session_id: f.frozen.nativeSessionId, event: { type: 'message_start', message: { id: 'own-live-goal-response', model: 'owned-model' } } }); await tick();
    assert.equal((await f.engine.beforeTool(report)).hookSpecificOutput.permissionDecision, 'allow');
    f.feed.emit({ type: 'result', uuid: randomUUID(), session_id: f.frozen.nativeSessionId, subtype: 'success', is_error: false }); await tick();
    assert.equal(f.engine.liveSourceResult.uuid, sourceResult); assert.equal(f.sent.length, 2);
    await assert.rejects(f.engine.beginGoal(contract.executionId));
  } finally { await f.engine.close(); }
});
await test('denied live admission or Stop preserves the completed ordinary result without another input', async () => {
  for (const stop of [false, true]) {
    let calls = 0, release;
    const f = fixture({ admit: async ({ binding }) => ++calls === 1 ? admission(binding) : stop
      ? await new Promise(resolve => { release = () => resolve(admission(binding)); }) : { allowed: false } }, liveOptions);
    try {
      await f.engine.initialize(); await f.engine.send('Own ordinary source'); await tick(); echo(f, f.sent[0]); await tick();
      const executionId = randomUUID(); f.engine.armGoal({ executionId, objective: 'Own accepted objective', maxSteps: 8, maxActiveSeconds: 900 });
      const sourceResult = randomUUID(); f.feed.emit({ type: 'result', uuid: sourceResult, session_id: f.frozen.nativeSessionId, subtype: 'success', is_error: false }); await tick();
      const pending = f.engine.beginGoal(executionId); const rejected = assert.rejects(pending);
      if (stop) { await tick(); await f.engine.interrupt(); release(); }
      await rejected; await f.engine.close();
      assert.equal(f.sent.length, 1); assert.equal(f.interrupts(), 0); assert.equal(f.engine.liveGoalInputSubmitted, false);
      assert.equal(f.engine.result.uuid, sourceResult); assert.equal(f.engine.goalStartedAt, null); assert.equal(f.engine.error, null);
    } finally { await f.engine.close(); }
  }
});
await test('unarmed preparation and cancelled or failed source boundaries never start a Goal', async () => {
  for (const mode of ['unarmed','cancel','failed']) {
    const f = fixture({ admit: async ({ binding }) => admission(binding) }, liveOptions);
    try {
      await f.engine.initialize(); await f.engine.send('Original ordinary source'); await tick(); echo(f, f.sent[0]); await tick();
      const executionId = randomUUID();
      if (mode !== 'unarmed') f.engine.armGoal({ executionId, objective: 'Own saved objective', maxSteps: 8, maxActiveSeconds: 900 });
      const sourceResult = randomUUID(); f.feed.emit({ type: 'result', uuid: sourceResult, session_id: f.frozen.nativeSessionId,
        subtype: 'success', is_error: mode === 'failed' }); await tick();
      if (mode === 'failed') { assert.equal(f.engine.activationReceipt().state, 'refused'); await assert.rejects(f.engine.beginGoal(executionId)); }
      await f.engine.close(); assert.equal(f.sent.length, 1); assert.equal(f.interrupts(), 0);
      assert.equal(f.engine.liveGoalInputSubmitted, false); assert.equal(f.engine.result.uuid, sourceResult); assert.equal(f.engine.goalStartedAt, null);
    } finally { await f.engine.close(); }
  }
});
await test('native image content is acknowledged before tools; changed image echo closes admission', async () => {
  const text = 'Own image user λ input', parts = [{ type: 'text', text }, { type: 'image', source: { type: 'base64', media_type: 'image/png', data: 'YWJj' } }];
  for (const changed of [false, true]) {
    const f = fixture({ admit: async ({ binding }) => admission(binding) }, { requireInputReceipt: true, resolvedModel: 'owned-model',
      frozenInput: requestId => ({ profileId: INPUT_PROFILE, requestId, textSha256: createHash('sha256').update(text).digest('hex'),
        contentSha256: contentDigest(parts), content: parts }) });
    try {
      await f.engine.initialize(); await f.engine.send(text); await tick(); assert.deepEqual(f.sent[0].message.content, parts);
      const tool = { hook_event_name: 'PreToolUse', session_id: f.frozen.nativeSessionId, tool_name: 'mcp__studio__read_file',
        tool_use_id: 'own-image-bound-call', tool_input: { path: 'own.c' }, mcp_server: { name: 'studio', source: 'dynamic' } };
      assert.equal((await f.engine.beforeTool(tool)).hookSpecificOutput.permissionDecision, 'deny');
      const echo = structuredClone(parts); if (changed) echo[1].source.data = 'eHl6';
      f.feed.emit({ type: 'user', isReplay: true, uuid: f.frozen.requestId, session_id: f.frozen.nativeSessionId,
        message: { role: 'user', content: echo } }); await tick();
      if (changed) { assert.equal(f.engine.state, 'unconfirmed'); assert.equal(f.grants.length, 0); }
      else {
        assert.equal(f.received.at(-1).identity.nativeInputContentSha256, contentDigest(parts));
        f.feed.emit({ type: 'stream_event', session_id: f.frozen.nativeSessionId,
          event: { type: 'message_start', message: { id: 'own-image-response', model: 'owned-model' } } }); await tick();
        assert.equal((await f.engine.beforeTool(tool)).hookSpecificOutput.permissionDecision, 'allow');
        assert.equal(publicFrame({ type: 'user', isReplay: true, message: { role: 'user', content: parts } }).message, undefined);
      }
    } finally { await f.engine.close(); }
  }
});
await test('attachment-only native content needs no invented user text', async () => {
  const content = [{ type: 'text', text: '{"kind":"studio_attachment_metadata"}' },
    { type: 'image', source: { type: 'base64', media_type: 'image/png', data: 'YWJj' } }];
  const f = fixture({ admit: async ({ binding }) => admission(binding) }, { requireInputReceipt: true,
    frozenInput: requestId => ({ profileId: INPUT_PROFILE, requestId, textSha256: createHash('sha256').update('').digest('hex'),
      contentSha256: contentDigest(content), content }) });
  try { await f.engine.initialize(); await f.engine.send(''); await tick(); assert.deepEqual(f.sent[0].message.content, content); }
  finally { await f.engine.close(); }
});
await test('canonical native model and selected effort cannot silently change', async () => {
  const f = fixture({ admit: async ({ binding }) => admission(binding) }, { resolvedModel: 'owned-model', effort: 'high' });
  try {
    await f.engine.initialize(); await f.engine.send('Own explicit input'); await tick();
    assert.equal(f.options.effort, 'high'); assert.equal(f.options.env.CLAUDE_CODE_DISABLE_LEGACY_MODEL_REMAP, '1');
    assert.equal(f.options.env.CLAUDE_CODE_MAX_RETRIES, '0'); assert.equal(f.options.env.CLAUDE_CODE_RETRY_WATCHDOG, '0');
    assert.deepEqual(f.options.settings.fallbackModel, []); assert.deepEqual(f.options.settings.availableModels, ['owned-model']);
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
  const echo = publicFrame({ type:'user',isReplay:true,uuid:randomUUID(),message:{role:'user',content:'private queued text'} });
  assert.equal(echo.isReplay,true);assert.equal(echo.message,undefined);
  const result = publicFrame({ type: 'result', subtype: 'error_during_execution', errors: ['private provider response'], usage: { input_tokens: 7 } });
  assert.equal(result.errors, undefined); assert.deepEqual(result.usage, { input_tokens: 7 });
  const scoped = publicFrame({ ...native, error: 'private provider failure', message: { ...native.message,
    usage: { input_tokens: 12, cache_creation_input_tokens: 0, cache_read_input_tokens: 5, output_tokens: 999999, privateDetail: 'secret' } } });
  assert.deepEqual(scoped.message.usage, { input_tokens: 12, cache_creation_input_tokens: 0, cache_read_input_tokens: 5 });
  assert.equal(scoped.error, 'nativeError'); assert.equal(JSON.stringify(scoped).includes('private provider failure'), false);
  const missing = publicFrame({ ...native, message: { ...native.message, usage: { input_tokens: true, cache_read_input_tokens: -1 } } });
  assert.deepEqual(missing.message.usage, { input_tokens: null, cache_creation_input_tokens: null, cache_read_input_tokens: null });
  const tail = publicFrame({ type:'stream_event', event:{ type:'message_delta', delta:{stop_reason:'end_turn',stop_sequence:'private'}, usage:{output_tokens:13,input_tokens:999,privateDetail:'secret'} } });
  assert.deepEqual(tail.event.usage,{output_tokens:13});
  assert.deepEqual(tail.event.delta,{stop_reason:'end_turn'});
  assert.deepEqual(publicFrame({type:'stream_event',event:{type:'message_delta',usage:{output_tokens:true}}}).event.usage,{output_tokens:null});
});
function admission(binding) { return { allowed: true, extraUsageDisabled: true, providerId: binding.providerId,
  nativeSessionId: binding.nativeSessionId, model: binding.model, admissionId: randomUUID(), expiresAt: Date.now() + 10000,
  authMethod: 'claude.ai', apiProvider: 'firstParty', subscriptionType: 'pro' }; }

await test('native model refusal keeps its safe error and drains the original failed result', async () => {
  let closed = 0;
  const f = fixture({ admit: async ({ binding }) => admission(binding), closeAdmission: async () => { closed++; } },
    { resolvedModel: 'owned-model' });
  try {
    await f.engine.initialize(); await f.engine.send('Own original input'); await tick();
    const failure = { type: 'assistant', uuid: randomUUID(), session_id: f.frozen.nativeSessionId, error: 'model_not_found',
      message: { id: 'owned-model-error', model: '<synthetic>', content: [{ type: 'text', text: 'private provider response' },
        { type: 'tool_use', id: 'unbound-error-tool', name: 'mcp__studio__read_file', input: { path: 'private' } }] } };
    const projected = publicFrame(failure);
    assert.equal(projected.error, 'model_not_found'); assert.match(projected.error_message, /no replacement/);
    assert.deepEqual(projected.message.content, []); assert.equal(JSON.stringify(projected).includes('private'), false);
    f.feed.emit(failure); await tick();
    assert.equal(f.engine.nativeFailure, true); assert.equal(f.engine.modelObserved, false); assert.equal(closed, 1);
    f.feed.emit({ type: 'result', subtype: 'error_during_execution', is_error: true, uuid: randomUUID(), session_id: f.frozen.nativeSessionId });
    await tick(); assert.equal(f.engine.error, null); assert.equal(f.engine.result.is_error, true);
    assert.equal(f.grants.length, 0); assert.equal(f.sent.length, 1);
  } finally { await f.engine.close(); }
});

await test('a late Stop preserves an already confirmed original result', async () => {
  const f = fixture({ admit: async ({ binding }) => admission(binding) });
  try {
    await f.engine.initialize(); await f.engine.send('Own original input'); await tick();
    const result = { type: 'result', subtype: 'success', is_error: false, uuid: randomUUID(), session_id: f.frozen.nativeSessionId };
    f.feed.emit(result); await tick();
    await f.engine.interrupt(); assert.equal(f.interrupts(), 0); assert.equal(f.engine.result, result);
    assert.equal(f.engine.error, null);
  } finally { await f.engine.close(); }
});

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

await test('queued native tools require the original echoed input ID and foreign echoes fail closed', async () => {
  const f = fixture({ admit: async ({ binding }) => admission(binding) }, { requireInputReceipt: true });
  try {
    await f.engine.initialize(); await f.engine.send('Own queued text'); await tick();
    assert.deepEqual(f.options.extraArgs, {'replay-user-messages':null});
    const input = { hook_event_name: 'PreToolUse', session_id: f.frozen.nativeSessionId, tool_name: 'mcp__studio__read_file',
      tool_use_id: 'own-queued-tool', tool_input: { path: 'own.c' }, mcp_server: { name: 'studio', source: 'dynamic' } };
    assert.equal((await f.engine.beforeTool(input)).hookSpecificOutput.permissionDecision, 'deny');
    assert.equal(f.grants.length, 0);
    f.feed.emit({type:'system',subtype:'status',session_id:f.frozen.nativeSessionId,uuid:randomUUID(),user_message_uuids:[f.frozen.requestId]});
    await tick();assert.equal(f.engine.inputAccepted,false);
    f.feed.emit({ type:'user',isReplay:true,uuid:f.frozen.requestId,session_id:f.frozen.nativeSessionId,
      parent_tool_use_id:null,message:{role:'user',content:'Own queued text'} });
    await tick(); assert.equal(f.engine.inputAccepted, true);
    assert.deepEqual(f.received[1].identity.nativeInputRequestIds, [f.frozen.requestId]);
    assert.equal((await f.engine.beforeTool(input)).hookSpecificOutput.permissionDecision, 'allow');
    f.feed.emit({ type: 'assistant', uuid: randomUUID(), session_id: f.frozen.nativeSessionId,
      user_message_uuid: randomUUID(), message: { id: 'own-foreign-input', content: [] } });
    await tick(); assert.equal(f.engine.state, 'unconfirmed');
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

await test('bounded Studio GOAL uses distinct native inputs and automatic origin with fresh admission per step', async () => {
  const admissions = [];
  const f = fixture({ admit: async ({ binding }) => { admissions.push(binding.requestId); return admission(binding); } }, { goal: true });
  const echo = input => f.feed.emit({ type: 'user', isReplay: true, uuid: input.uuid, session_id: f.frozen.nativeSessionId,
    parent_tool_use_id: null, message: { role: 'user', content: input.message.content } });
  const result = () => f.feed.emit({ type: 'result', subtype: 'success', is_error: false, uuid: randomUUID(), session_id: f.frozen.nativeSessionId });
  try {
    await f.engine.initialize(); await f.engine.send('The original owned objective.'); await tick();
    echo(f.sent[0]); await tick(); result(); await tick();
    assert.equal(f.engine.state, 'between'); assert.equal(f.sent.length, 1);
    const next = randomUUID(); await f.engine.continue(next); await tick();
    assert.equal(admissions.length, 2); assert.equal(f.sent.length, 2);
    assert.equal(f.sent[0].origin.kind, 'human'); assert.equal(f.sent[1].origin.kind, 'auto-continuation');
    assert.equal(f.sent[1].uuid, next); assert.equal(f.sent[1].message.content, GOAL_CONTINUE_TEXT);
    assert.equal(f.engine.inputAccepted, false);
    echo(f.sent[1]); await tick();
    assert.equal(f.engine.inputAccepted, true);
    const last = f.received.at(-1).identity;
    assert.equal(last.studioRequestId, f.frozen.requestId); assert.equal(last.studioGoalStepId, next);
    assert.deepEqual(last.nativeInputRequestIds, [next]); assert.equal(last.nativeTurnId, null);
    result(); await tick(); await assert.rejects(f.engine.continue(next));
  } finally { await f.engine.close(); }
});

await test('native GOAL step cap prevents a ninth input and never self-continues on a result', async () => {
  const f = fixture({ admit: async ({ binding }) => admission(binding) }, { goal: true });
  try {
    await f.engine.initialize(); await f.engine.send('Owned bounded objective'); await tick();
    for (let step = 0; step < 8; step++) {
      const input = f.sent[step];
      f.feed.emit({ type: 'user', isReplay: true, uuid: input.uuid, session_id: f.frozen.nativeSessionId,
        parent_tool_use_id: null, message: { role: 'user', content: input.message.content } });
      await tick();
      f.feed.emit({ type: 'result', subtype: 'success', is_error: false, uuid: randomUUID(), session_id: f.frozen.nativeSessionId });
      await tick(); assert.equal(f.sent.length, step + 1);
      if (step < 7) { await f.engine.continue(randomUUID()); await tick(); }
    }
    await assert.rejects(f.engine.continue(randomUUID())); assert.equal(f.sent.length, 8);
  } finally { await f.engine.close(); }
});

await test('refused or revoked later Goal admission keeps the completed predecessor without interrupting it', async () => {
  for (const live of [false, true]) for (const stop of [false, true]) {
    let admissions = 0, release;
    const f = fixture({ admit: async ({ binding }) => {
      if (++admissions <= (live ? 2 : 1)) return admission(binding);
      return stop ? await new Promise(resolve => { release = () => resolve(admission(binding)); }) : { allowed: false };
    } }, live ? liveOptions : { goal: true });
    try {
      await f.engine.initialize(); await f.engine.send('Owned initial input'); await tick(); echo(f, f.sent[0]); await tick();
      const source = randomUUID(), executionId = randomUUID();
      if (live) f.engine.armGoal({ executionId, objective: 'Owned accepted objective', maxSteps: 8, maxActiveSeconds: 900 });
      f.feed.emit({ type: 'result', uuid: source, session_id: f.frozen.nativeSessionId, subtype: 'success', is_error: false }); await tick();
      if (live) {
        await f.engine.beginGoal(executionId); await tick(); echo(f, f.sent[1]); await tick();
        f.feed.emit({ type: 'result', uuid: randomUUID(), session_id: f.frozen.nativeSessionId, subtype: 'success', is_error: false }); await tick();
      }
      const previousInput = f.sent.at(-1).uuid, previousResult = f.engine.result.uuid;
      const next = randomUUID(), pending = f.engine.continue(next), rejected = assert.rejects(pending);
      if (stop) { await tick(); await f.engine.interrupt(); release(); }
      await rejected;
      await f.engine.close();
      assert.equal(f.sent.length, live ? 2 : 1); assert.equal(f.engine.inputId, next); assert.equal(f.engine.inputSubmitted, false);
      assert.equal(f.engine.result.uuid, previousResult); assert.equal(f.engine.resultInputId, previousInput);
      if (live) { assert.equal(f.engine.liveSourceResult.uuid, source); assert.equal(f.engine.liveGoalInputSubmitted, true); }
      assert.equal(f.interrupts(), 0); assert.equal(f.engine.error, null);
    } finally { await f.engine.close(); }
  }
});
