/** Fixed private worker transport. No caller-selected module, command or URL. */
import { readFile } from 'node:fs/promises';
import { connect } from 'node:net';
import { createInterface } from 'node:readline';
import { pathToFileURL } from 'node:url';
import { ClaudeSessionEngine } from './claude_session_engine.mjs';

export function publicFrame(native) {
  const base = { type: native.type, subtype: native.subtype, uuid: native.uuid, session_id: native.session_id, parent_tool_use_id: native.parent_tool_use_id };
  if (native.type === 'user' && native.isReplay === true) return { ...base, isReplay: true };
  if (native.type === 'assistant') return { ...base, ...(native.error == null ? {} : { error: 'nativeError' }), message: { id: native.message?.id, model: native.message?.model,
    usage: native.message?.usage && typeof native.message.usage === 'object'
      ? Object.fromEntries(['input_tokens','cache_creation_input_tokens','cache_read_input_tokens'].map(key => {
        const value = native.message.usage[key]; return [key, Number.isSafeInteger(value) && value >= 0 ? value : null];
      })) : null,
    content: (native.message?.content ?? []).filter(v => ['text', 'tool_use'].includes(v.type)).map(v => v.type === 'text'
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
    return { ...base, event };
  }
  if (native.type === 'result') return { ...base, is_error: native.is_error, duration_ms: native.duration_ms,
    usage: native.usage, modelUsage: native.modelUsage, num_turns: native.num_turns };
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
  let admissionClosed = false;
  const engine = new ClaudeSessionEngine(sdk, { ...config, cwd: '/inference', home: '/home/studio', config: '/config',
    executable: '/runtime/native/claude' }, config.binding, {
    authorize: value => admissionClosed ? false : broker({ ...value, operation: 'authorize', capability: config.capability }),
    admit: async ({ binding, query }) => {
      if (admissionClosed) return { allowed: false };
      const reported = await query.usage_EXPERIMENTAL_MAY_CHANGE_DO_NOT_RELY_ON_THIS_API_YET({ skipBehaviors: true });
      const account = await query.accountInfo();
      if (admissionClosed) return { allowed: false };
      return broker({ operation: 'admit', binding, account, usage: { subscription_type: reported?.subscription_type,
        rate_limits_available: reported?.rate_limits_available, rate_limits: reported?.rate_limits }, capability: config.capability });
    },
    closeAdmission: async () => { admissionClosed = true; },
    receive: async value => { const native = publicFrame(value.native); if (native) emit({ event: 'native', identity: value.identity, native }); },
  });
  const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
  const operations = new Set(); let busy = false;
  emit({ event: 'transport_ready', nativeSessionId: config.binding.nativeSessionId });
  try {
    for await (const line of lines) {
      if (Buffer.byteLength(line) > 262144) throw Error('The original native command exceeds its bound.');
      const command = JSON.parse(line);
      if (!command || typeof command !== 'object' || !['initialize', 'send', 'continue', 'interrupt', 'close'].includes(command.operation)
        || Object.keys(command).some(k => !['operation', ...(command.operation === 'send' ? ['text'] : command.operation === 'continue' ? ['inputRequestId'] : [])].includes(k))) throw Error('Invalid fixed native worker command.');
      if (command.operation === 'close') break;
      if (command.operation === 'interrupt') { await engine.interrupt(); emit({ event: 'interrupted' }); continue; }
      if (busy) throw Error('The original native operation is busy.');
      busy = true;
      const pending = (async () => {
        try {
          if (command.operation === 'initialize') { await engine.initialize(); emit({ event: 'ready', nativeSessionId: config.binding.nativeSessionId }); }
          if (command.operation === 'send' || command.operation === 'continue') {
            if (command.operation === 'send') await engine.send(command.text); else await engine.continue(command.inputRequestId);
            emit({ event: 'submitted', requestId: config.binding.requestId, inputRequestId: engine.inputId });
          }
        } catch {
          emit({ event: 'unconfirmed', requestId: config.binding.requestId, promptSubmitted: engine.sent,
            inputRequestId: engine.inputId, inputSubmitted: engine.inputSubmitted,
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
      inputRequestId: engine.inputId, inputSubmitted: engine.inputSubmitted,
      resultId: engine.result?.uuid ?? null, subtype: engine.result?.subtype ?? null, historyReadable,
      originalStreamConfirmed: !engine.error });
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main().catch(() => { process.stderr.write('The original native Claude worker is unavailable.\n'); process.exitCode = 1; });
}
