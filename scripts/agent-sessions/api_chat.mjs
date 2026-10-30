/** Bounded wire translation only: no context controller, agent or tool executor. */
import { randomUUID } from 'node:crypto';

const MAX_TEXT = 196608, MAX_ARGS = 131072, MAX_EVENT = 524288, MAX_CALLS = 32;
const PROVIDER_ERRORS = new Set(['context_length_exceeded', 'usage_limit_exceeded', 'insufficient_quota',
  'rate_limit_exceeded', 'invalid_api_key', 'model_not_found', 'api_account_required', 'api_access_denied', 'api_service_unavailable']);
export const CHAT_NATIVE_METADATA = Symbol('private native transport metadata');
export class ChatFault extends Error {
  constructor(code = 'chat_protocol_error') { super(code); this.code = code; }
}
const bad = (code = 'chat_semantics_unavailable') => { throw new ChatFault(code); };
const object = value => value && typeof value === 'object' && !Array.isArray(value);
const bytes = value => Buffer.byteLength(value, 'utf8');
const identifier = value => typeof value === 'string' && value.length > 0 && bytes(value) <= 256
  // eslint-disable-next-line no-control-regex -- protocol identifiers cannot contain controls or separators.
  && !/[\x00-\x20\x7f\ud800-\udfff]/u.test(value);
function text(value, maximum, partial = false) {
  // eslint-disable-next-line no-control-regex -- preserve textual whitespace, reject other transport controls.
  if (typeof value !== 'string' || bytes(value) > maximum || /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(value)
    || !partial && /[\ud800-\udfff]/u.test(value)) bad();
  return value;
}
function parts(value) {
  if (typeof value === 'string') return value;
  if (!Array.isArray(value) || value.some(part => !object(part)
    || !['input_text', 'output_text'].includes(part.type) || typeof part.text !== 'string'
    || part.annotations?.length || part.logprobs?.length)) bad();
  // Preserve every text part and its boundary, rather than flattening images
  // or discarding pieces of tool output. Non-text content is unavailable.
  return value.map(part => ({ type: 'text', text: part.text }));
}
function argumentsObject(value) {
  if (typeof value !== 'string' || bytes(value) > MAX_ARGS) bad('chat_invalid_tool_arguments');
  let parsed; try { parsed = JSON.parse(value); } catch { bad('chat_invalid_tool_arguments'); }
  if (!object(parsed)) bad('chat_invalid_tool_arguments');
  const stack = [[parsed, 0]]; let nodes = 0;
  while (stack.length) {
    const [node, depth] = stack.pop();
    if (++nodes > 65536 || depth > 64 || typeof node === 'number' && (!Number.isFinite(node)
      || Number.isInteger(node) && !Number.isSafeInteger(node))
      || typeof node === 'string' && /[\ud800-\udfff]/u.test(node)) bad('chat_invalid_tool_arguments');
    if (node && typeof node === 'object') for (const [key, child] of Object.entries(node)) {
      if (/[\ud800-\udfff]/u.test(key)) bad('chat_invalid_tool_arguments'); stack.push([child, depth + 1]);
    }
  }
  return value;
}
export function chatRequest(value, policy) {
  if (!object(policy) || policy.schema !== 1 || !['system', 'developer'].includes(policy.systemRole)
    || !['none', 'effort'].includes(policy.reasoning) || policy.functionTools !== true || policy.streaming !== true) bad();
  const allowed = new Set(['model', 'input', 'tools', 'tool_choice', 'parallel_tool_calls', 'reasoning', 'store', 'stream',
    'include', 'service_tier', 'prompt_cache_key', 'client_metadata', 'text']);
  if (!object(value) || Object.keys(value).some(key => !allowed.has(key)) || value.store !== false
    || value.stream !== true || !Array.isArray(value.input) || value.input.length > 8192
    || !Array.isArray(value.tools) || value.tools.length > 128 || value.tool_choice !== 'auto'
    || typeof value.parallel_tool_calls !== 'boolean' || value.text != null
    || value.service_tier != null && value.service_tier !== 'default'
    || value.include?.some(item => item !== 'reasoning.encrypted_content')) bad();
  const tools = value.tools.map(tool => {
    if (!object(tool) || tool.type !== 'function' || !identifier(tool.name)
      || !object(tool.parameters) || Object.keys(tool).some(key => !['type', 'name', 'description', 'parameters', 'strict'].includes(key))
      || tool.strict != null && typeof tool.strict !== 'boolean') bad();
    const definition = { ...tool }; delete definition.type;
    return { type: 'function', function: definition };
  });
  const names = new Set(tools.map(tool => tool.function.name));
  if (names.size !== tools.length) bad();
  const reasoning = value.reasoning ?? {};
  if (!object(reasoning) || Object.keys(reasoning).some(key => key !== 'effort')) bad();
  let effort;
  if (policy.reasoning === 'none') {
    if (reasoning.effort != null && reasoning.effort !== 'none') bad();
  } else {
    if (!['none', 'minimal', 'low', 'medium', 'high', 'xhigh'].includes(reasoning.effort)) bad();
    effort = reasoning.effort;
  }
  if (policy.systemRole === 'system' && value.input.some(item => item.role === 'system')
    && value.input.some(item => item.role === 'developer')) bad(); // Do not collapse distinct priorities.
  const messages = [], pending = new Set();
  for (const item of value.input) {
    if (!object(item) || item.encrypted_content || item.encrypted_function_args || item.namespace) bad();
    if (item.type === 'message') {
      if (!['system', 'developer', 'user', 'assistant'].includes(item.role) || pending.size) bad();
      messages.push({ role: item.role === 'developer' ? policy.systemRole : item.role, content: parts(item.content) });
    } else if (item.type === 'function_call') {
      if (!identifier(item.call_id) || !identifier(item.name) || pending.has(item.call_id)) bad();
      let previous = messages.at(-1);
      if (pending.size && previous?.role !== 'assistant') bad();
      if (previous?.role !== 'assistant') { previous = { role: 'assistant', content: null, tool_calls: [] }; messages.push(previous); }
      previous.tool_calls ??= [];
      previous.tool_calls.push({ id: item.call_id, type: 'function', function: { name: item.name, arguments: argumentsObject(item.arguments) } });
      pending.add(item.call_id);
    } else if (item.type === 'function_call_output') {
      if (!identifier(item.call_id) || !pending.delete(item.call_id)) bad();
      messages.push({ role: 'tool', tool_call_id: item.call_id, content: parts(item.output) });
    } else bad();
  }
  if (pending.size || !messages.length) bad();
  if (value.client_metadata != null && (!object(value.client_metadata) || Object.keys(value.client_metadata).length > 64
    || Object.entries(value.client_metadata).some(([key, data]) => key.length > 256 || typeof data !== 'string' || bytes(data) > 16384)
    || bytes(JSON.stringify(value.client_metadata)) > 65536)) bad();
  if (value.prompt_cache_key != null && (typeof value.prompt_cache_key !== 'string' || bytes(value.prompt_cache_key) > 256)) bad();
  const request = { model: value.model, messages, tools, tool_choice: 'auto', parallel_tool_calls: value.parallel_tool_calls,
    stream: true, store: false, stream_options: { include_usage: true }, ...(effort === undefined ? {} : { reasoning_effort: effort }),
    ...(value.service_tier == null ? {} : { service_tier: value.service_tier }),
    ...(value.prompt_cache_key == null ? {} : { prompt_cache_key: value.prompt_cache_key }) };
  // Codex's private telemetry envelope is not Chat's constrained model metadata.
  // Retain it locally in adapter response metadata, never truncate or forward
  // it as a generation parameter. Symbol properties do not enter wire JSON.
  request[CHAT_NATIVE_METADATA] = value.client_metadata ?? {};
  return request;
}

function usage(value) {
  if (value == null) return undefined;
  if (!object(value)) bad('chat_protocol_error');
  const valid = number => Number.isSafeInteger(number) && number >= 0;
  if (!['prompt_tokens', 'completion_tokens', 'total_tokens'].every(key => valid(value[key]))) bad('chat_protocol_error');
  const result = { input_tokens: value.prompt_tokens, output_tokens: value.completion_tokens, total_tokens: value.total_tokens };
  for (const [source, target, keys] of [['prompt_tokens_details', 'input_tokens_details', ['cached_tokens']],
    ['completion_tokens_details', 'output_tokens_details', ['reasoning_tokens']]]) {
    if (value[source] != null) {
      if (!object(value[source])) bad('chat_protocol_error');
      const details = {};
      for (const key of keys) if (value[source][key] != null) {
        if (!valid(value[source][key])) bad('chat_protocol_error'); details[key] = value[source][key];
      }
      if (Object.keys(details).length) result[target] = details;
    }
  }
  return result;
}

export class ChatStream {
  constructor(request, emit, observer = {}) {
    this.observer = observer;
    this.names = new Set(request.tools.map(tool => tool.function.name)); this.emit = emit;
    this.nativeMetadata = request[CHAT_NATIVE_METADATA] ?? {};
    this.decoder = new TextDecoder('utf-8', { fatal: true }); this.buffer = ''; this.data = [];
    this.eventSize = 0; this.started = false; this.done = false; this.finishReason = null; this.used = undefined;
    this.calls = new Map(); this.text = ''; this.messageStarted = false; this.providerId = undefined;
    this.pendingSurrogate = '';
    // This is explicitly a local transport identity, never a provider receipt.
    this.id = 'studio_chat_' + randomUUID(); this.messageId = this.id + '_message'; this.sequence = 0;
  }
  send(type, fields = {}) { this.emit({ type, sequence_number: this.sequence++, ...fields }); }
  response(extra = {}) {
    return { id: this.id, object: 'response', model: undefined,
      metadata: { studio_transport: 'chat-completions', local_response_id: this.id,
        provider_response_id: this.providerId ?? null, provider_finish_reason: this.finishReason,
        studio_native_metadata: this.nativeMetadata }, ...extra };
  }
  push(chunk, final = false) {
    try { this.buffer += this.decoder.decode(chunk, { stream: !final }); } catch { bad('chat_protocol_error'); }
    while (true) {
      const index = this.buffer.search(/[\r\n]/);
      if (index < 0 || !final && this.buffer[index] === '\r' && index === this.buffer.length - 1) break;
      const line = this.buffer.slice(0, index), width = this.buffer[index] === '\r' && this.buffer[index + 1] === '\n' ? 2 : 1;
      this.buffer = this.buffer.slice(index + width); this.line(line);
    }
    if (this.buffer.length > MAX_EVENT) bad('chat_protocol_error');
    if (final && (this.buffer.length || this.data.length || !this.done)) bad('chat_stream_incomplete');
  }
  line(line) {
    if (line.length > MAX_EVENT) bad('chat_protocol_error');
    if (line === '') {
      if (this.data.length) { const value = this.data.join('\n'); this.data = []; this.eventSize = 0; this.event(value); }
      return;
    }
    if (line.startsWith(':')) return;
    const colon = line.indexOf(':'), field = colon < 0 ? line : line.slice(0, colon);
    if (field !== 'data') return;
    const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '');
    this.eventSize += bytes(value); if (this.eventSize > MAX_EVENT) bad('chat_protocol_error');
    this.data.push(value);
  }
  event(raw) {
    if (this.done) bad('chat_protocol_error');
    if (raw === '[DONE]') { this.complete(); return; }
    let value; try { value = JSON.parse(raw); } catch { bad('chat_protocol_error'); }
    if (!object(value)) bad('chat_protocol_error');
    if (value.error) {
      const code = object(value.error) ? this.observer.errorCode?.(value.error.code) ?? value.error.code : null;
      bad(PROVIDER_ERRORS.has(code) ? code : 'provider_error');
    }
    this.observer.observe?.(value);
    if (!Array.isArray(value.choices) || value.choices.length > 1) bad('chat_protocol_error');
    if (value.id != null) {
      if (!identifier(value.id) || this.providerId !== undefined && this.providerId !== value.id) bad('chat_protocol_error');
      this.providerId = value.id;
    }
    if (!this.started) { this.started = true; this.send('response.created', { response: this.response({ status: 'in_progress' }) }); }
    if (value.usage != null) {
      const current = usage(value.usage);
      if (this.used !== undefined && JSON.stringify(current) !== JSON.stringify(this.used)) bad('chat_protocol_error');
      this.used = current;
    }
    if (!value.choices.length) return;
    const choice = value.choices[0]; if (!object(choice)) bad('chat_protocol_error');
    const delta = choice.delta;
    if (!object(choice) || choice.index !== 0 || !object(delta) || delta.role != null && delta.role !== 'assistant'
      || Object.entries(delta).some(([key, data]) => !['role', 'content', 'tool_calls'].includes(key) && data != null && data !== '')) bad();
    const substantive = delta.content != null && delta.content !== '' || delta.tool_calls?.length;
    if (this.finishReason && substantive) bad('chat_protocol_error');
    if (delta.content != null && delta.content !== '') {
      let content = this.pendingSurrogate + text(delta.content, MAX_TEXT, true); this.pendingSurrogate = '';
      const last = content.charCodeAt(content.length - 1);
      if (last >= 0xd800 && last <= 0xdbff) { this.pendingSurrogate = content.at(-1); content = content.slice(0, -1); }
      text(content, MAX_TEXT); this.text += content;
      if (bytes(this.text) > MAX_TEXT) bad('chat_protocol_error');
      if (!this.messageStarted) {
        this.messageStarted = true;
        this.send('response.output_item.added', { output_index: 0, item: { type: 'message', id: this.messageId, role: 'assistant', content: [] } });
      }
      this.send('response.output_text.delta', { item_id: this.messageId, output_index: 0, content_index: 0, delta: content });
    }
    if (delta.tool_calls != null) {
      if (!Array.isArray(delta.tool_calls) || delta.tool_calls.length > MAX_CALLS) bad('chat_protocol_error');
      for (const part of delta.tool_calls) {
        if (!object(part) || !Number.isSafeInteger(part.index) || part.index < 0 || part.index >= MAX_CALLS
          || part.type != null && part.type !== 'function' || part.function != null && !object(part.function)
          || Object.keys(part).some(key => !['index', 'id', 'type', 'function'].includes(key))) bad();
        const call = this.calls.get(part.index) ?? { id: null, name: '', arguments: '' };
        if (part.id != null) {
          if (!identifier(part.id) || call.id != null && part.id !== call.id) bad('chat_protocol_error'); call.id = part.id;
        }
        const fn = part.function ?? {};
        if (Object.keys(fn).some(key => !['name', 'arguments'].includes(key))) bad();
        if (fn.name != null) { call.name += text(fn.name, 256); if (bytes(call.name) > 256) bad(); }
        if (fn.arguments != null) { call.arguments += text(fn.arguments, MAX_ARGS, true); if (bytes(call.arguments) > MAX_ARGS) bad('chat_invalid_tool_arguments'); }
        this.calls.set(part.index, call);
      }
    }
    if (choice.finish_reason != null) {
      if (!['stop', 'tool_calls', 'length', 'content_filter'].includes(choice.finish_reason)
        || this.finishReason && this.finishReason !== choice.finish_reason) bad();
      this.finishReason = choice.finish_reason;
    }
  }
  complete() {
    if (!this.started || !this.finishReason || this.pendingSurrogate) bad('chat_stream_incomplete');
    if (this.finishReason === 'length' || this.finishReason === 'content_filter') {
      this.send('response.incomplete', { response: this.response({ status: 'incomplete',
        // Codex treats the literal content_filter as a separate retry category.
        // Keep this adapter's refusal terminal, with reported usage preserved.
        incomplete_details: { reason: this.finishReason === 'length' ? 'max_output_tokens' : 'studio_chat_content_filter' },
        ...(this.used === undefined ? {} : { usage: this.used }) }) });
      this.done = true; return;
    }
    if ((this.finishReason === 'tool_calls') !== (this.calls.size > 0) || !this.calls.size && !this.messageStarted) bad('chat_protocol_error');
    const ids = new Set(), output = [];
    // Validate the entire completed call set before releasing any tool item.
    for (const [index, call] of [...this.calls].sort((a, b) => a[0] - b[0])) {
      if (!identifier(call.id) || ids.has(call.id) || !this.names.has(call.name)) bad('chat_invalid_tool_arguments');
      ids.add(call.id); argumentsObject(call.arguments);
      output.push({ type: 'function_call', id: this.id + '_tool_' + index, call_id: call.id, name: call.name, arguments: call.arguments });
    }
    if (this.messageStarted) {
      this.send('response.output_item.done', { output_index: 0, item: { type: 'message', id: this.messageId,
        role: 'assistant', content: [{ type: 'output_text', text: this.text }] } });
    }
    for (let index = 0; index < output.length; index++) {
      this.send('response.output_item.done', { output_index: index + (this.messageStarted ? 1 : 0), item: output[index] });
    }
    this.send('response.completed', { response: this.response({ status: 'completed', ...(this.used === undefined ? {} : { usage: this.used }) }) });
    this.done = true;
  }
}
