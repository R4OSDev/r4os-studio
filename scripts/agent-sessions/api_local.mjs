/** Named server wire contracts, using the original complete native history. */
import { chatRequest, ChatFault } from './api_chat.mjs';

const plain = { schema: 1, systemRole: 'system', reasoning: 'none', functionTools: true, streaming: true };
export function serverProfile(value = 'custom') {
  if (!['custom', 'ollama', 'lm-studio'].includes(value)) throw new ChatFault('api_server_semantics_unavailable');
  return value;
}
export function localRequest(value, server, protocol) {
  serverProfile(server);
  if (server === 'custom' || !['responses', 'chat-completions'].includes(protocol)) throw new ChatFault('api_server_semantics_unavailable');
  // Validate the same lossless text/function scope on both protocols. This
  // rejects opaque/reasoning/image history and unsupported generation controls.
  const chat = chatRequest(value, plain);
  if (value.parallel_tool_calls !== true) throw new ChatFault('api_server_semantics_unavailable');
  if (protocol === 'chat-completions') {
    // These endpoints do not need native telemetry, storage, cache or service
    // tier controls. Full history is provided on each stateless request.
    const result = { ...chat };
    for (const field of ['store', 'service_tier', 'prompt_cache_key']) delete result[field];
    if (server === 'ollama') {
      // v0.13.3 has no tool_choice/parallel_tool_calls controls. Its default
      // tools contract is automatic; false/required/forced choices are refused.
      delete result.tool_choice; delete result.parallel_tool_calls;
    }
    return result;
  }
  const input = value.input.map(item => {
    if (item.type === 'function_call_output' && typeof item.output !== 'string') throw new ChatFault('api_server_semantics_unavailable');
    return item.type === 'message' && item.role === 'developer' ? { ...item, role: 'system' } : item;
  });
  const result = { model: value.model, input, tools: value.tools, stream: true };
  if (server === 'lm-studio') Object.assign(result, { store: false, tool_choice: 'auto', parallel_tool_calls: true });
  // Ollama Responses is stateless. No previous_response_id/conversation,
  // encrypted reasoning, native client telemetry or unsupported controls.
  // Context is the explicitly configured server value; this adapter cannot
  // change server context or guarantee a vendor's overflow enforcement.
  return result;
}
