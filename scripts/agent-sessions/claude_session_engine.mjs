/** Persistent native Claude query and fixed Studio MCP boundary. */
import { createHash } from 'node:crypto';
import { messageIdentity } from './claude_engine.mjs';

const uuid = value => typeof value === 'string' && /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(value);
const opaque = value => typeof value === 'string' && Buffer.byteLength(value) > 0 && Buffer.byteLength(value) <= 256
  // eslint-disable-next-line no-control-regex -- native call IDs cannot contain controls.
  && !/[\x00-\x20\x7f\ud800-\udfff]/u.test(value);
const fingerprint = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const bounded = (value, max) => Buffer.byteLength(JSON.stringify(value)) <= max;
export const GOAL_CONTINUE_TEXT = 'Continue the original saved Studio GOAL within its unchanged scope and permissions. '
  + 'Inspect original receipts before acting; never repeat an unconfirmed effect. '
  + 'Before ending this step, call mcp__studio__report_goal with continue, complete or blocked and a concise reason.';
async function deadline(work, ms = 15000) {
  let timer;
  try { return await Promise.race([work, new Promise((_, reject) => { timer = setTimeout(() => reject(Error('The original Claude operation timed out.')), ms); })]); }
  finally { clearTimeout(timer); }
}

class Inputs {
  constructor() { this.values = []; this.waiter = null; this.closed = false; }
  push(value) {
    if (this.closed || this.values.length) throw Error('The original native input is unavailable.');
    this.values.push(value); this.waiter?.(); this.waiter = null;
  }
  close() { this.closed = true; this.waiter?.(); this.waiter = null; }
  async *stream() {
    while (!this.closed) {
      if (!this.values.length) await new Promise(resolve => { this.waiter = resolve; });
      if (this.closed) return;
      if (this.values.length) yield this.values.shift();
    }
  }
}

export function sessionEnvironment(options) {
  return { PATH: '/usr/bin', USER: 'r4os-studio', HOME: options.home, CLAUDE_CONFIG_DIR: options.config,
    DISABLE_AUTOUPDATER: '1', DISABLE_UPDATES: '1', ENABLE_CLAUDEAI_MCP_SERVERS: 'false', ENABLE_TOOL_SEARCH: 'false', MCP_DISCOVERY_CACHE: '0',
    MAX_MCP_OUTPUT_TOKENS: '262144',
    DISABLE_TELEMETRY: '1', DISABLE_ERROR_REPORTING: '1',
    CLAUDE_CODE_DISABLE_AUTO_MEMORY: '1', CLAUDE_CODE_DISABLE_CLAUDE_MDS: '1',
    CLAUDE_CODE_DISABLE_BACKGROUND_TASKS: '1', CLAUDE_CODE_DISABLE_AGENT_VIEW: '1', CLAUDE_CODE_DISABLE_BG_EXIT_HANDOFF: '1',
    CLAUDE_CODE_DISABLE_CRON: '1', CLAUDE_CODE_DISABLE_ARTIFACT: '1', CLAUDE_CODE_DISABLE_ADVISOR_TOOL: '1',
    CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS: '1', CLAUDE_CODE_DISABLE_BUNDLED_SKILLS: '1',
    CLAUDE_CODE_DISABLE_FAST_MODE: '1', CLAUDE_CODE_DISABLE_FILE_CHECKPOINTING: '1',
    CLAUDE_CODE_DISABLE_LEGACY_MODEL_REMAP: '1',
    CLAUDE_CODE_DISABLE_FILE_MENTIONS: '1', CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS: '1' };
}

function binding(value) {
  if (!value || !['providerId', 'studioSessionId', 'nativeSessionId', 'runId', 'requestId', 'ownerId'].every(key => uuid(value[key]))
    || !['project', 'skill'].includes(value.ownerType) || typeof value.model !== 'string' || !value.model || value.model.length > 200
    || !['studio-tools-v14', 'studio-tools-v15', 'studio-skill-tools-v5'].includes(value.toolProfile)) throw Error('Invalid frozen Claude session binding.');
  return Object.freeze(structuredClone(value));
}

function mcpTool(name) {
  const match = typeof name === 'string' && /^mcp__studio__([a-z][a-z0-9_]{0,79})$/.exec(name);
  return match ? match[1] : null;
}

/** Host callbacks carry original binding/receipts, never user-chosen RPCs. */
export class ClaudeSessionEngine {
  constructor(sdk, options, frozen, host) {
    this.binding = binding(frozen); this.host = host; this.inputs = new Inputs(); this.grants = new Map();
    this.state = 'initializing'; this.sent = false; this.result = null; this.error = null;
    this.requireInputReceipt = options.requireInputReceipt === true; this.inputAccepted = false;
    this.inputId = this.binding.requestId; this.inputSubmitted = false; this.inputOrigin = 'human';
    this.stepCount = 0; this.inputIds = new Set([this.inputId]); this.goalStartedAt = null;
    this.goal = options.goal ?? null;
    if (this.goal && (Object.keys(this.goal).sort().join(',') !== 'executionId,maxActiveSeconds,maxSteps'
      || this.goal.executionId !== this.binding.requestId || this.goal.maxSteps !== 8 || this.goal.maxActiveSeconds !== 900
      || !this.requireInputReceipt || !options.tools?.includes('report_goal'))) throw Error('Invalid bounded Studio GOAL contract.');
    if (!host || !['authorize', 'receive', 'admit', 'closeAdmission'].every(k => typeof host[k] === 'function')
      || typeof options.systemPrompt !== 'string' || Buffer.byteLength(options.systemPrompt) > 131072
      || !['new', 'resume'].includes(options.mode) || options.mode === 'resume' && options.historyConfirmed !== true) {
      throw Error('The original Claude session or host boundary is unavailable.');
    }
    const tools = new Set(options.tools);
    if (!Array.isArray(options.tools) || tools.size !== options.tools.length || tools.size > 128
      || [...tools].some(name => !/^[a-z][a-z0-9_]{0,79}$/.test(name))) throw Error('Invalid frozen Studio tools.');
    this.tools = tools;
    this.expectedModel = options.resolvedModel ?? null; this.modelObserved = false;
    if (this.expectedModel !== null && this.expectedModel !== this.binding.model) throw Error('The frozen native model identifier changed.');
    if (options.effort !== undefined && options.effort !== '' && !['low','medium','high','xhigh','max'].includes(options.effort)) throw Error('Invalid frozen native effort.');
    this.enveloped = new Set(options.envelopedTools ?? []);
    if ([...this.enveloped].some(name => !this.tools.has(name))) throw Error('Invalid frozen Studio argument envelope.');
    this.query = sdk.query({ prompt: this.inputs.stream(), options: {
      cwd: options.cwd, pathToClaudeCodeExecutable: options.executable, env: sessionEnvironment(options),
      ...(options.mode === 'new' ? { sessionId: this.binding.nativeSessionId, title: 'Studio session' } : { resume: this.binding.nativeSessionId }),
      persistSession: true, model: this.binding.model, systemPrompt: { type: 'custom', prompt: options.systemPrompt, snapshot: true },
      ...(this.requireInputReceipt ? { extraArgs: { 'replay-user-messages': null } } : {}),
      ...(options.effort ? { effort: options.effort } : {}),
      tools: [], disallowedTools: [...sdk.BUILTIN_TOOL_NAMES], settingSources: [], skills: [], plugins: [], agents: {},
      settings: { precomputeCompactionEnabled: false, fallbackModel: [], availableModels: [this.binding.model] },
      strictMcpConfig: true, permissionMode: 'default', enableFileCheckpointing: false, includePartialMessages: true,
      mcpServers: { studio: { type: 'stdio', command: '/usr/bin/python3', args: ['/bridge/mcp.py'], alwaysLoad: true, timeout: 1200000 } },
      hooks: { PreToolUse: [{ hooks: [input => this.beforeTool(input)] }] },
      canUseTool: async (name, input, details) => {
        const grant = this.grants.get(details.toolUseID), tool = mcpTool(name);
        if (this.state === 'active' && (!this.requireInputReceipt || this.inputAccepted) && tool && this.tools.has(tool) && details.mcpServer?.name === 'studio'
          && details.mcpServer.source === 'dynamic' && !details.agentID && grant?.tool === tool && grant.hash === fingerprint(input)) {
          return { behavior: 'allow', updatedInput: input };
        }
        return { behavior: 'deny', message: 'Only the original bound Studio tool call is available.' };
      }, stderr: () => {},
    } });
    this.pump = this.read();
  }

  async beforeTool(input) {
    const tool = mcpTool(input?.tool_name);
    const wireInput = input?.tool_input;
    const args = tool && this.enveloped.has(tool) ? wireInput && Object.keys(wireInput).length === 1
      && Object.hasOwn(wireInput, 'request') ? wireInput.request : null : wireInput;
    let allowed = false;
    if (this.state === 'active' && (!this.requireInputReceipt || this.inputAccepted) && (!this.expectedModel || this.modelObserved) && input?.hook_event_name === 'PreToolUse' && input.session_id === this.binding.nativeSessionId
      && tool && this.tools.has(tool) && opaque(input.tool_use_id) && !input.agent_id
      && input.mcp_server?.name === 'studio' && input.mcp_server.source === 'dynamic'
      && args && typeof args === 'object' && !Array.isArray(args) && bounded(args, 131072)) {
      const grant = { tool, hash: fingerprint(input.tool_input) }, old = this.grants.get(input.tool_use_id);
      if ((!old || old.tool === grant.tool && old.hash === grant.hash) && this.grants.size < 1024) {
        try { allowed = await deadline(this.host.authorize({ binding: this.binding, nativeToolUseId: input.tool_use_id, tool, arguments: args })) === true; }
        catch { allowed = false; }
        if (allowed && this.state === 'active') this.grants.set(input.tool_use_id, grant); else allowed = false;
      }
    }
    return { hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: allowed ? 'allow' : 'deny',
      permissionDecisionReason: allowed ? 'Original bound Studio tool permission.' : 'The original Studio tool admission is unavailable.' } };
  }

  async initialize() {
    if (this.state !== 'initializing') throw Error('The original native initialization is unavailable.');
    const value = await deadline(this.query.initializationResult());
    if (value.claude_code_version !== '2.1.312' || value.hooks_applied !== true) throw Error('The pinned native hooks/version were not confirmed.');
    let servers; const until = Date.now() + 5000;
    do {
      servers = await deadline(this.query.mcpServerStatus());
      if (servers?.[0]?.status !== 'pending' || servers.length !== 1 || servers[0].name !== 'studio') break;
      if (Date.now() >= until || this.state !== 'initializing') break;
      await new Promise(resolve => setTimeout(resolve, 50));
    } while (Date.now() < until && this.state === 'initializing');
    if (!Array.isArray(servers) || servers.length !== 1 || servers[0].name !== 'studio' || servers[0].status !== 'connected') {
      throw Error('The original fixed Studio MCP server is unavailable.');
    }
    const names = servers[0].tools?.map(tool => tool.name);
    if (servers[0].source !== 'dynamic' || !Array.isArray(names) || names.length !== this.tools.size
      || new Set(names).size !== names.length || names.some(name => !this.tools.has(name))) {
      throw Error('The original native Studio tool catalog is incomplete or changed.');
    }
    if (this.state !== 'initializing') throw Error('The native stream ended during initialization.');
    this.state = 'ready'; return { binding: this.binding, servers };
  }

  async send(text) {
    if (this.state !== 'ready' || this.sent || typeof text !== 'string' || !text.trim() || Buffer.byteLength(text) > 131072) {
      throw Error('Only one explicit original Studio request can be submitted by this worker.');
    }
    await this.submit(text, 'ready');
  }

  async continue(inputId) {
    if (!this.goal || this.state !== 'between' || !this.result || this.result.subtype !== 'success' || this.result.is_error
      || !uuid(inputId) || this.inputIds.has(inputId) || this.stepCount >= this.goal.maxSteps
      || this.goalStartedAt === null || Date.now() - this.goalStartedAt >= this.goal.maxActiveSeconds * 1000) {
      throw Error('The original bounded Studio GOAL cannot continue.');
    }
    this.inputId = inputId; this.inputIds.add(inputId); this.inputOrigin = 'auto-continuation';
    this.inputSubmitted = false; this.inputAccepted = false; this.state = 'admitting';
    await this.submit(GOAL_CONTINUE_TEXT, 'admitting');
  }

  async submit(text, expectedState) {
    // The limit/auth stage owns admission. A real native plan and disabled
    // overage must be proved there; an SDK model list is never authorization.
    const account = await deadline(this.query.accountInfo());
    const admission = await deadline(this.host.admit({ binding: this.binding, account, query: this.query }));
    // SDK accountInfo uses display labels ("Claude Pro") and may omit a token
    // source for a native file login. Auth status/limit admission must provide
    // the positive native method and normalized plan; absence is not proof.
    const plan = { 'Claude Pro': 'pro', 'Claude Max': 'max', pro: 'pro', max: 'max' }[account.subscriptionType];
    if (this.state !== expectedState || account.apiProvider !== 'firstParty' || account.apiKeySource != null && account.apiKeySource !== 'none'
      || account.tokenSource != null && account.tokenSource !== 'claude.ai' || !plan
      || admission?.authMethod !== 'claude.ai' || admission.apiProvider !== 'firstParty' || admission.subscriptionType !== plan
      || admission.allowed !== true || admission.extraUsageDisabled !== true
      || admission.providerId !== this.binding.providerId || admission.nativeSessionId !== this.binding.nativeSessionId
      || admission.model !== this.binding.model || !uuid(admission.admissionId) || !Number.isFinite(admission.expiresAt)
      || admission.expiresAt < Date.now() || admission.expiresAt > Date.now() + 30000) {
      throw Error('The original native subscription/limit admission is unavailable. No model prompt was submitted.');
    }
    this.sent = true; this.state = 'active';
    this.result = null; this.inputSubmitted = true; this.stepCount++;
    this.inputTextSha256 = createHash('sha256').update(text).digest('hex');
    this.inputs.push({ type: 'user', message: { role: 'user', content: text }, parent_tool_use_id: null,
      uuid: this.inputId, session_id: this.binding.nativeSessionId, origin: { kind: this.inputOrigin }, client_composed: true });
  }

  async read() {
    try {
      for await (const message of this.query) {
        if (!message || typeof message !== 'object' || !bounded(message, 16 * 1024 * 1024)) throw Error('Native Claude frame exceeds its bound.');
        const reportedModel = message.message?.model ?? message.event?.message?.model;
        if (this.expectedModel && reportedModel != null) {
          if (reportedModel !== this.expectedModel) throw Error('The native model response differs from the frozen selection. No replacement model was accepted.');
          this.modelObserved = true;
        }
        // Image tool results can be large; identity checks never duplicate
        // those bytes into Studio events or call-receipt metadata.
        const parts = Array.isArray(message.message?.content) ? message.message.content : [];
        const identity = messageIdentity({ type: message.type, subtype: message.subtype, session_id: message.session_id,
          uuid: message.uuid, parent_tool_use_id: message.parent_tool_use_id,
          user_message_uuid: message.user_message_uuid, user_message_uuids: message.user_message_uuids,
          event: { message: { id: message.event?.message?.id } },
          message: message.message ? { id: message.message.id, content: parts.filter(v => v?.type === 'tool_use').map(v => ({ type: v.type, id: v.id, name: v.name })) } : undefined }, this.binding.requestId);
        if (this.goal) identity.studioGoalStepId = this.inputId;
        if (message.type === 'user' && message.isReplay === true && message.uuid === this.inputId) {
          const content = message.message?.content;
          const text = typeof content === 'string' ? content : Array.isArray(content) && content.length === 1 && content[0]?.type === 'text' ? content[0].text : null;
          if (!this.inputSubmitted || message.isSynthetic === true && this.inputOrigin !== 'auto-continuation' || message.parent_tool_use_id != null || message.message?.role !== 'user'
            || typeof text !== 'string' || createHash('sha256').update(text).digest('hex') !== this.inputTextSha256
            || identity.nativeInputRequestIds.some(id => id !== this.inputId)) {
            throw Error('The native input echo does not match the original submitted text.');
          }
          identity.nativeInputRequestIds = [message.uuid];
          identity.nativeInputReceiptKind = 'stdinEcho';
          identity.nativeInputTextSha256 = this.inputTextSha256;
        }
        if (identity.nativeInputRequestIds.some(id => id !== this.inputId)
          || identity.nativeSessionId && identity.nativeSessionId !== this.binding.nativeSessionId || message.parent_tool_use_id != null
          || message.resume_reason || ['assistant', 'stream_event', 'result'].includes(message.type)
            && this.state !== 'active' && !(this.state === 'stopping' && this.sent)) {
          throw Error('Native Claude produced an unbound, resumed or autonomous turn.');
        }
        if (identity.nativeInputRequestIds.length && (['assistant','stream_event','result'].includes(message.type)
          || identity.nativeInputReceiptKind === 'stdinEcho')) {
          this.inputAccepted = true;
          if (this.goal && this.goalStartedAt === null) this.goalStartedAt = Date.now();
        }
        const between = message.type === 'result' && this.goal && this.state === 'active'
          && message.subtype === 'success' && !message.is_error;
        if (message.type === 'result') {
          this.result = message; this.state = between ? 'between' : 'completed'; this.grants.clear();
        }
        await this.host.receive({ binding: this.binding, identity, native: message });
        if (message.type === 'result' && !between) {
          this.inputs.close();
          await this.host.closeAdmission(this.binding); this.query.close();
        }
      }
      if (!['completed', 'stopping', 'closed'].includes(this.state)) throw Error('The original native stream ended without completion.');
    } catch (error) {
      this.error = error; this.state = 'unconfirmed'; this.grants.clear(); this.inputs.close();
      try { await this.host.closeAdmission(this.binding); } finally { this.query.close(); }
    }
  }

  async interrupt() {
    if (this.state === 'closed' || this.state === 'stopping') return;
    this.state = 'stopping'; this.grants.clear();
    await this.host.closeAdmission(this.binding);
    try { await deadline(this.query.interrupt(), 5000); } finally {
      this.inputs.close();
      // A native interrupt acknowledgement is not its original terminal
      // result. Drain that result before closing; otherwise a clean Stop can
      // unnecessarily leave an unresumable, unconfirmed transcript.
      if (this.sent && !this.result && !this.error) {
        try { await deadline(this.pump, 6000); } catch { /* Missing result stays protected. */ }
      }
      this.query.close();
    }
  }

  async close() {
    if (this.state === 'closed') return;
    if (this.goal && this.state === 'between') {
      this.state = 'completed'; await this.host.closeAdmission(this.binding);
    }
    if (!['completed', 'unconfirmed'].includes(this.state)) await this.interrupt();
    this.inputs.close(); this.query.close(); await deadline(this.pump, 12000); this.state = 'closed';
  }
}
