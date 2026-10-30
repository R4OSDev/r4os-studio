/** Native Agent SDK control/stream boundary. No Codex RPC or API-key transport. */
import { pathToFileURL } from 'node:url';

const MAX_MESSAGE = 524288;
const uuid = value => typeof value === 'string' && /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(value);
const identifier = value => typeof value === 'string' && value.length > 0 && Buffer.byteLength(value) <= 256
  // eslint-disable-next-line no-control-regex -- native identifiers are opaque but cannot carry controls.
  && !/[\x00-\x20\x7f\ud800-\udfff]/u.test(value);
export function messageIdentity(message, studioRequestId) {
  if (!uuid(studioRequestId) || !message || typeof message !== 'object' || Array.isArray(message)
    || typeof message.type !== 'string' || message.type.length > 80 || Buffer.byteLength(JSON.stringify(message)) > MAX_MESSAGE) throw Error('Invalid native Claude message.');
  const session = message.session_id;
  if (session != null && !uuid(session)) throw Error('Native Claude session identity is invalid.');
  const provider = message.message?.id ?? message.event?.message?.id;
  const content = message.message?.content;
  const tools = Array.isArray(content) ? content.filter(part => part && typeof part === 'object' && part.type === 'tool_use') : [];
  if (tools.some(part => !identifier(part.id) || !identifier(part.name))) throw Error('Native Claude tool identity is invalid.');
  return { studioRequestId, nativeSessionId: session ?? null,
    nativeMessageId: identifier(message.uuid) ? message.uuid : null,
    providerMessageId: identifier(provider) ? provider : null,
    nativeTurnId: null, nativeToolUseId: identifier(message.parent_tool_use_id) ? message.parent_tool_use_id : null,
    toolUses: tools.map(part => ({ id: part.id, name: part.name })),
    nativeType: message.type, subtype: typeof message.subtype === 'string' ? message.subtype.slice(0, 80) : null,
    supportedType: ['system', 'assistant', 'user', 'result', 'stream_event', 'rate_limit_event'].includes(message.type) };
}

export class ClaudeControl {
  constructor(sdk, options, requestId, receive = () => {}) {
    if (!uuid(requestId)) throw Error('Invalid Studio control request identity.');
    this.requestId = requestId; this.receive = receive; this.closed = false; this.nativeSessionId = null;
    this.pending = false; this.events = 0; this.failed = false;
    let finish; const inputClosed = new Promise(resolve => { finish = resolve; }); this.finish = finish;
    // An open input stream with no user messages permits SDK metadata control.
    // Empty text would start a model turn and is never substituted here.
    // eslint-disable-next-line require-yield -- yielding any user message would start a model turn.
    async function* idleInput() { await inputClosed; }
    this.query = sdk.query({ prompt: idleInput(), options: {
      cwd: options.cwd, pathToClaudeCodeExecutable: options.executable,
      env: { PATH: '/usr/bin', HOME: options.home, CLAUDE_CONFIG_DIR: options.config,
        USER: 'r4os-studio', DISABLE_AUTOUPDATER: '1', DISABLE_UPDATES: '1', ENABLE_CLAUDEAI_MCP_SERVERS: 'false',
        CLAUDE_CODE_DISABLE_AUTO_MEMORY: '1', CLAUDE_CODE_DISABLE_CLAUDE_MDS: '1', CLAUDE_CODE_DISABLE_BACKGROUND_TASKS: '1',
        CLAUDE_CODE_DISABLE_CRON: '1', CLAUDE_CODE_DISABLE_BUNDLED_SKILLS: '1', CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS: '1',
        // The pinned native usage control is a first-party Data API request;
        // NONESSENTIAL_TRAFFIC would block it before HTTP. Keep the specific
        // telemetry/report/update exclusions instead of claiming quota proof.
        DISABLE_TELEMETRY: '1', DISABLE_ERROR_REPORTING: '1' },
      tools: [], disallowedTools: [...sdk.BUILTIN_TOOL_NAMES], settingSources: [], skills: [], plugins: [], mcpServers: {},
      settings: { precomputeCompactionEnabled: false },
      strictMcpConfig: true, permissionMode: 'dontAsk', persistSession: false, includePartialMessages: true,
      canUseTool: async () => ({ behavior: 'deny', message: 'This control adapter authorizes no model tools.' }), stderr: () => {},
    } });
    this.pump = this.read();
  }
  async read() {
    try {
      for await (const message of this.query) {
        const identity = messageIdentity(message, this.requestId);
        if (++this.events > 256 || this.nativeSessionId && identity.nativeSessionId && identity.nativeSessionId !== this.nativeSessionId) throw Error('Native Claude stream binding changed.');
        if (identity.nativeSessionId) this.nativeSessionId = identity.nativeSessionId;
        // Original messages stay on this trusted private boundary. Consumers
        // must project public fields; unknown types grant no tool permissions.
        await this.receive({ identity, native: message });
      }
      if (!this.closed) { this.failed = true; this.query.close(); }
    } catch {
      if (!this.closed) { this.failed = true; this.query.close(); }
    }
  }
  async control(operation) {
    if (this.closed || this.failed || this.pending) throw Error('The original Claude control is unavailable or busy.');
    const methods = { initialize: 'initializationResult', models: 'supportedModels', account: 'accountInfo', interrupt: 'interrupt',
      usage: 'usage_EXPERIMENTAL_MAY_CHANGE_DO_NOT_RELY_ON_THIS_API_YET' };
    if (typeof operation !== 'string' || !Object.hasOwn(methods, operation)) throw Error('This adapter does not authorize a model turn or unknown control.');
    this.pending = true; let timer;
    try {
      const value = await Promise.race([operation === 'usage' ? this.query[methods[operation]]({ skipBehaviors: true }) : this.query[methods[operation]](), new Promise((_, reject) => {
        timer = setTimeout(() => reject(Error('The original Claude control timed out.')), 12000);
      })]);
      if (this.failed || this.closed) throw Error('The original native stream is unavailable.');
      if (Buffer.byteLength(JSON.stringify(value ?? null)) > MAX_MESSAGE) throw Error('Native Claude control exceeded its output limit.');
      return { studioRequestId: this.requestId, operation, nativeSessionId: this.nativeSessionId, value: value ?? null };
    } catch {
      this.failed = true; this.query.close(); throw Error('The original Claude control could not be confirmed; it was not repeated.');
    } finally { clearTimeout(timer); this.pending = false; }
  }
  async close() {
    this.closed = true; this.finish(); this.query.close(); let timer;
    try {
      await Promise.race([this.pump, new Promise((_, reject) => { timer = setTimeout(() => reject(Error('Original Claude stream closure is unconfirmed.')), 12000); })]);
    } finally { clearTimeout(timer); }
  }
}

/** Paths are supplied only after the host verifies the immutable runtime. */
export async function openControl(runtime, options, requestId, receive) {
  if (runtime.qualified?.offlineInitialization !== true || runtime.qualified?.modelTurns !== false
    || runtime.version !== '2.1.312' || runtime.sdkVersion !== '0.3.312') throw Error('Unqualified Claude control runtime.');
  const sdk = await import(pathToFileURL(runtime.sdk).href);
  return new ClaudeControl(sdk, { ...options, executable: runtime.native }, requestId, receive);
}
