/** Fixed private worker transport. No caller-selected module, command or URL. */
import { readFile } from 'node:fs/promises';
import { connect } from 'node:net';
import { createInterface } from 'node:readline';
import { pathToFileURL } from 'node:url';
import { ClaudeSessionEngine } from './claude_session_engine.mjs';

const nativeErrors = {
  authentication_failed: 'Claude sign-in is no longer valid. Check this provider before continuing.',
  oauth_org_not_allowed: 'This Claude organization does not allow the selected subscription session.',
  account_on_hold: 'Claude reports that this account is on hold. Check the provider before continuing.',
  verification_required: 'Claude requires account verification before this session can continue.',
  billing_error: 'Claude rejected the billing or subscription state. No API billing fallback was used.',
  rate_limit: 'Claude limited this request. Check subscription limits before continuing; the limit scope may be unknown.',
  overloaded: 'Claude reports temporary overload. This request was not replayed.',
  invalid_request: 'Claude rejected this request. Check the selected model and session settings.',
  model_not_found: 'The selected Claude model is unavailable for this account. Choose an available model; no replacement was used.',
  server_error: 'Claude reported a server error. This request was not replayed.',
  max_output_tokens: 'Claude reached the response output limit. Inspect its retained result before continuing.',
  cloud_credential_error: 'Claude reported an unexpected cloud credential state. Check this native subscription provider.',
};

const nativeErrorKinds = new Set(['max_output_tokens', 'dlp_request_denied', 'claude_code_version_too_old',
  'safety_monitor_blocked', 'effort_requires_thinking', 'advisor_incompatible', 'tool_history_mismatch',
  'autocompact_thrashing', 'pdf_too_large', 'pdf_password_protected', 'media_removed', 'no_response',
  'tls_untrusted_ca', 'gateway_content_type', 'provider_credentials', 'gateway_signin_required',
  'gateway_session_expired', 'api_key_auth_disabled', 'org_disabled_credential', 'invalid_credential_header',
  'model_requires_usage_credits', 'long_context_credits_required', 'consent_unanswered', 'no_allowed_fallback',
  'model_substitution_disabled', 'field_not_granted', 'usage_limit_reached', 'empty_completion',
  'unattended_start_limit', 'unattended_start_unconfirmed']);
const safeHttpStatus = value => Number.isInteger(value) && value >= 100 && value <= 599 ? value : null;
const safeCount = (value, min, max) => Number.isSafeInteger(value) && value >= min && value <= max ? value : null;

/** Passive stream evidence. Absence of a frame is never retry admission. */
export class NativeResponseObservation {
  constructor(binding) {
    this.binding = binding; this.input = null; this.retired = new Set(); this.invalid = false;
  }

  observe({ identity, native }) {
    const input = identity.nativeRetry?.claim?.inputRequestId ?? identity.studioGoalStepId ?? this.binding.requestId;
    if (input !== this.input?.id) {
      if (this.input && !this.input.terminal || this.retired.has(input) || this.retired.size >= 4096) this.invalid = true;
      if (this.input && this.retired.size < 4096) this.retired.add(this.input.id);
      this.input = { id: input, received: false, terminal: false, active: null, starts: 0, stops: 0,
        snapshots: 0, tools: false, retry: false, compaction: false, terminalDelta: false, abandoned: false };
    }
    const current = this.input, ids = identity.nativeInputRequestIds;
    if (Object.hasOwn(native, 'abandoned_blocks')) current.abandoned = true;
    if (native.session_id != null && native.session_id !== this.binding.nativeSessionId
      || native.parent_tool_use_id != null || !Array.isArray(ids) || ids.some(id => id !== input)) this.invalid = true;
    if (ids?.length && (['assistant', 'stream_event', 'result'].includes(native.type)
      || ['stdinEcho','stdinEmptyBlocksEcho'].includes(identity.nativeInputReceiptKind))) current.received = true;
    if (native.type === 'system') {
      if (native.subtype === 'api_retry') current.retry = true;
      if (native.subtype === 'compact_boundary') current.compaction = true;
    } else if (native.type === 'stream_event') {
      if (current.terminal) this.invalid = true;
      const event = native.event;
      if (event?.type === 'message_start') {
        const id = event.message?.id;
        if (current.active !== null || typeof id !== 'string' || !id || id.length > 256) this.invalid = true;
        current.active = id ?? null; current.starts++; current.terminalDelta = false;
      } else if (event?.type === 'message_stop') {
        if (current.active === null || !current.terminalDelta) this.invalid = true;
        current.active = null; current.stops++;
      } else if (['content_block_start', 'content_block_delta', 'content_block_stop', 'message_delta'].includes(event?.type)) {
        if (current.active === null) this.invalid = true;
        if (event.type === 'message_delta') current.terminalDelta = ['end_turn','tool_use','max_tokens','stop_sequence',
          'pause_turn','refusal','model_context_window_exceeded'].includes(event.delta?.stop_reason);
        if (event.type === 'content_block_start' && event.content_block?.type === 'tool_use') current.tools = true;
      } else this.invalid = true;
    } else if (native.type === 'assistant' && native.error == null) {
      if (current.terminal) this.invalid = true;
      current.snapshots++;
      if (native.message?.content?.some(part => part.type === 'tool_use')) current.tools = true;
    } else if (native.type === 'result') {
      if (current.terminal) this.invalid = true;
      current.terminal = true;
    }
    if ([current.starts, current.stops, current.snapshots].some(count => count > 65535)) this.invalid = true;
  }

  snapshot() {
    const value = this.input;
    const state = !value || this.invalid || !value.received ? 'unknown'
      : value.abandoned ? 'partialResponseObserved'
      : value.active !== null ? 'partialResponseObserved'
        : value.starts !== value.stops ? 'unknown'
          : value.starts > 0 ? 'completeResponsesObserved'
            : value.snapshots > 0 ? 'snapshotWithoutStreamBoundary' : 'noResponseObserved';
    return { schema: 1, state, inputReceiptObserved: value?.received === true,
      streamStarts: safeCount(value?.starts, 0, 65535), streamStops: safeCount(value?.stops, 0, 65535),
      assistantSnapshots: safeCount(value?.snapshots, 0, 65535), toolUseObserved: value?.tools === true,
      nativeRetryObserved: value?.retry === true, compactionObserved: value?.compaction === true,
      abandonedResponseObserved: value?.abandoned === true,
      retryAllowed: false };
  }
}

/** Diagnostics only: a terminal HTTP number is not a pre-response retry permit. */
export function nativeFailureFacts(native, observation = null) {
  if (native.type !== 'result' || native.subtype !== 'success' || native.is_error !== true) return null;
  return { schema: 1, source: 'claude-code-2.1.312/sdk-0.3.312/result',
    httpStatusCode: safeHttpStatus(native.api_error_status),
    kind: native.api_error === undefined ? null : nativeErrorKinds.has(native.api_error) ? native.api_error : 'unrecognized',
    origin: native.api_error_origin === 'first_party' ? 'first_party' : null,
    serverCodePresent: Object.hasOwn(native, 'api_error_code'), responseBoundary: 'unqualified',
    ...(observation ? { wireObservation: observation } : {}) };
}

export function nativeRetryFacts(native) {
  if (native.type !== 'system' || native.subtype !== 'api_retry') return null;
  return { schema: 1, source: 'claude-code-2.1.312/sdk-0.3.312/api_retry',
    attempt: safeCount(native.attempt, 1, 65535), maxRetries: safeCount(native.max_retries, 0, 65535),
    delayMs: safeCount(native.retry_delay_ms, 0, 3600000), httpStatusCode: safeHttpStatus(native.error_status),
    code: typeof native.error === 'string' && Object.hasOwn(nativeErrors, native.error) ? native.error : 'nativeError' };
}

export function publicFrame(native, observation = null) {
  const base = { type: native.type, subtype: native.subtype, uuid: native.uuid, session_id: native.session_id, parent_tool_use_id: native.parent_tool_use_id };
  if (native.type === 'user' && native.isReplay === true) return { ...base, isReplay: true };
  const failure = native.error == null ? null : Object.hasOwn(nativeErrors, native.error) ? native.error : 'nativeError';
  if (native.type === 'assistant') return { ...base, ...(failure === null ? {} : { error: failure,
    error_message: nativeErrors[failure] ?? 'Claude could not complete this request. Check the provider and retained session result.' }), message: { id: native.message?.id, model: native.message?.model,
    usage: native.message?.usage && typeof native.message.usage === 'object'
      ? Object.fromEntries(['input_tokens','cache_creation_input_tokens','cache_read_input_tokens'].map(key => {
        const value = native.message.usage[key]; return [key, Number.isSafeInteger(value) && value >= 0 ? value : null];
      })) : null,
    content: (failure === null ? native.message?.content ?? [] : []).filter(v => ['text', 'tool_use'].includes(v.type)).map(v => v.type === 'text'
      ? { type: 'text', text: v.text } : { type: 'tool_use', id: v.id, name: v.name, input: v.input }) } };
  if (native.type === 'stream_event') {
    const e = native.event, event = { type: e?.type, index: e?.index };
    if (e?.type === 'message_start') event.message = { id: e.message?.id, model: e.message?.model };
    if (e?.type === 'message_delta') {
      const output = e.usage?.output_tokens;
      event.usage = { output_tokens: Number.isSafeInteger(output) && output >= 0 ? output : null };
      event.delta = { stop_reason: ['end_turn','tool_use','max_tokens','stop_sequence','pause_turn','refusal','model_context_window_exceeded'].includes(e.delta?.stop_reason)
        ? e.delta.stop_reason : null };
    }
    if (e?.type === 'content_block_start') event.content_block = { type: e.content_block?.type,
      ...(e.content_block?.type === 'tool_use' ? { id: e.content_block.id, name: e.content_block.name } : {}) };
    if (e?.type === 'content_block_delta') event.delta = e.delta?.type === 'text_delta' ? { type: 'text_delta', text: e.delta.text }
      : { type: e.delta?.type };
    return { ...base, event, ...(Object.hasOwn(native, 'abandoned_blocks') ? { incompleteResponse: true } : {}) };
  }
  if (native.type === 'result') {
    const providerError = nativeFailureFacts(native, observation);
    return { ...base, is_error: native.is_error, duration_ms: native.duration_ms,
      usage: native.usage, modelUsage: native.modelUsage, num_turns: native.num_turns,
      ...(providerError ? { providerError } : {}) };
  }
  if (native.type === 'system' && native.subtype === 'api_retry') return { ...base, nativeRetry: nativeRetryFacts(native) };
  if (native.type === 'system' && native.subtype === 'compact_boundary') return { ...base, compact_metadata: native.compact_metadata };
  if (native.type === 'system' && ['init', 'status', 'session_title_changed'].includes(native.subtype)) return { ...base, status: native.status };
  if (native.type === 'rate_limit_event') return { ...base, rate_limit_info: native.rate_limit_info };
  return null;
}

function emit(value) {
  const data = JSON.stringify(value);
  if (Buffer.byteLength(data) > 524288) throw Error('The original Claude worker event exceeds its bound.');
  process.stdout.write(data + '\n');
}
function broker(value) {
  return new Promise((resolve, reject) => {
    const socket = connect('/bridge/host.sock'); let raw = '', settled = false;
    const finish = (error, result) => {
      if (settled) return;
      settled = true; clearTimeout(timer); socket.destroy();
      if (error) reject(error); else resolve(result);
    };
    const timer = setTimeout(() => finish(Error('Original Claude host control is unconfirmed.')), 15000);
    socket.setEncoding('utf8'); socket.on('error', () => finish(Error('Original Claude host control is unavailable.')));
    socket.on('connect', () => socket.end(JSON.stringify(value) + '\n'));
    socket.on('data', part => {
      raw += part;
      if (Buffer.byteLength(raw) > 65536) return finish(Error('Original Claude host control exceeds its bound.'));
      if (!raw.includes('\n')) return;
      try { const value = JSON.parse(raw.split('\n')[0]); if (!Object.hasOwn(value, 'result')) throw Error(); finish(null, value.result); }
      catch { finish(Error('Original Claude host control is unconfirmed.')); }
    });
    socket.on('end', () => { if (!settled) finish(Error('Original Claude host control closed without a result.')); });
  });
}

async function main() {
  const raw = await readFile('/bridge/runtime.json');
  if (raw.byteLength > 262144) throw Error('Invalid frozen native runtime input.');
  const config = JSON.parse(raw);
  if (config.schema !== 1 || !/^[a-f0-9]{64}$/.test(config.capability)) throw Error('Invalid frozen native runtime binding.');
  const sdk = await import(pathToFileURL('/runtime/sdk/sdk.mjs').href);
  let frozenInput;
  if (config.inputContract) {
    const input = await readFile('/bridge/input.json');
    if (input.byteLength > 12582912 + 4096) throw Error('The original native content exceeds its bound.');
    frozenInput = JSON.parse(input);
    const keys = ['profileId','requestId','textSha256','contentSha256'];
    if (Object.keys(config.inputContract).length !== keys.length || keys.some(key => config.inputContract[key] !== frozenInput[key])) throw Error('Changed native input manifest.');
  }
  let admissionClosed = false, admissionSuspended = false;
  const observation = new NativeResponseObservation(config.binding);
  const engine = new ClaudeSessionEngine(sdk, { ...config, frozenInput, cwd: '/inference', home: '/home/studio', config: '/config',
    executable: '/runtime/native/claude' }, config.binding, {
    authorize: value => admissionClosed || admissionSuspended ? false : broker({ ...value, operation: 'authorize', capability: config.capability }),
    admit: async ({ binding, query, retry }) => {
      if (admissionClosed) return { allowed: false };
      const reported = await query.usage_EXPERIMENTAL_MAY_CHANGE_DO_NOT_RELY_ON_THIS_API_YET({ skipBehaviors: true });
      const account = await query.accountInfo();
      if (admissionClosed) return { allowed: false };
      return broker({ operation: 'admit', binding, account, ...(retry ? { retry } : {}), usage: { subscription_type: reported?.subscription_type,
        rate_limits_available: reported?.rate_limits_available, rate_limits: reported?.rate_limits }, capability: config.capability });
    },
    closeAdmission: async () => { admissionClosed = true; },
    suspendAdmission: async () => { admissionSuspended = true; },
    receive: async value => {
      observation.observe(value);
      const native = publicFrame(value.native, value.native.type === 'result' ? observation.snapshot() : null);
      if (native) emit({ event: 'native', identity: value.identity, native });
      if (value.identity.nativeRetry && value.identity.nativeInputReceiptKind === 'stdinEmptyBlocksEcho') {
        if (admissionClosed) return;
        const accepted = await broker({ operation: 'retry_receipt', binding: config.binding,
          retry: value.identity.nativeRetry.claim, capability: config.capability });
        if (admissionClosed) return;
        if (accepted?.allowed !== true) throw Error('The original retry input receipt was not accepted.');
        admissionSuspended = false;
      }
    },
  });
  const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
  const operations = new Set(); let busy = false;
  emit({ event: 'transport_ready', nativeSessionId: config.binding.nativeSessionId });
  try {
    for await (const line of lines) {
      if (Buffer.byteLength(line) > 262144) throw Error('The original native command exceeds its bound.');
      const command = JSON.parse(line);
      const fields = { initialize: [], send: ['text'], continue: ['inputRequestId'], interrupt: [], close: [],
        arm_goal: ['executionId','objective','maxSteps','maxActiveSeconds'], begin_goal: ['executionId'], retry: ['claim'] };
      if (!command || typeof command !== 'object' || !Object.hasOwn(fields, command.operation)
        || Object.keys(command).some(k => !['operation', ...fields[command.operation]].includes(k))) throw Error('Invalid fixed native worker command.');
      if (command.operation === 'close') break;
      if (command.operation === 'interrupt') { await engine.interrupt(); emit({ event: 'interrupted' }); continue; }
      if (command.operation === 'arm_goal') {
        const contract = Object.fromEntries(fields.arm_goal.map(key => [key, command[key]]));
        try { emit({ event: 'goal_armed', requestId: config.binding.requestId, nativeSessionId: config.binding.nativeSessionId, ...engine.armGoal(contract) }); }
        catch { emit({ event: 'goal_arm_refused', requestId: config.binding.requestId, executionId: command.executionId }); }
        continue;
      }
      if (busy) throw Error('The original native operation is busy.');
      busy = true;
      const pending = (async () => {
        try {
          if (command.operation === 'initialize') { await engine.initialize(); emit({ event: 'ready', nativeSessionId: config.binding.nativeSessionId }); }
          if (['send','continue','begin_goal','retry'].includes(command.operation)) {
            if (command.operation === 'send') await engine.send(command.text);
            else if (command.operation === 'continue') await engine.continue(command.inputRequestId);
            else if (command.operation === 'begin_goal') await engine.beginGoal(command.executionId);
            else await engine.retry(command.claim);
            emit({ event: command.operation === 'retry' ? 'retry_submitted' : 'submitted', requestId: config.binding.requestId,
              inputRequestId: engine.inputId, ...(command.operation === 'retry' ? { claim: engine.retryClaim } : {}) });
          }
        } catch {
          emit({ event: 'unconfirmed', requestId: config.binding.requestId, promptSubmitted: engine.sent,
            inputRequestId: engine.inputId, inputSubmitted: engine.inputSubmitted,
            ...(command.operation === 'retry' ? { operation: 'retry', claim: engine.retryClaim,
              sourceResultId: engine.retryBoundary?.resultId ?? null } : {}),
            message: command.operation === 'initialize' ? 'The original native Claude/MCP initialization was not confirmed.'
              : engine.sent ? 'The original native operation is unconfirmed. It was not repeated.' : 'Native subscription/limit admission is unavailable. No model prompt was submitted.' });
        } finally { busy = false; }
      })();
      operations.add(pending); void pending.finally(() => operations.delete(pending));
    }
  } finally {
    lines.close(); await engine.close(); await Promise.allSettled([...operations]);
    let historyReadable = false;
    if (engine.result) {
      const info = await sdk.getSessionInfo(config.binding.nativeSessionId, { dir: '/inference' });
      historyReadable = info?.sessionId === config.binding.nativeSessionId;
    }
    emit({ event: 'closed', nativeSessionId: config.binding.nativeSessionId, studioRequestId: config.binding.requestId, promptSubmitted: engine.sent,
      ...(engine.liveActivation ? { liveGoal: { ...engine.activationReceipt(), sourceResultId: engine.liveSourceResult?.uuid ?? null, inputSubmitted: engine.liveGoalInputSubmitted } } : {}),
      inputRequestId: engine.inputId, inputSubmitted: engine.inputSubmitted,
      ...(engine.retryClaim ? { retry: { claim: engine.retryClaim, stepInputId: engine.stepInputId } } : {}),
      resultId: engine.result?.uuid ?? null, resultInputRequestId: engine.resultInputId, subtype: engine.result?.subtype ?? null, historyReadable,
      originalStreamConfirmed: !engine.error });
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main().catch(() => { process.stderr.write('The original native Claude worker is unavailable.\n'); process.exitCode = 1; });
}
