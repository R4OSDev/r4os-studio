/** Z.AI Coding Plan wire compatibility; no agent loop or provider fallback.
 * OpenCode v1.19.5, MIT, packages/opencode/src/session/llm/request.ts.
 * See THIRD-PARTY-ZAI.md. This reference's non-OpenCode-provider branch
 * sends its User-Agent and session affinity, without x-opencode-client.
 */
import { ChatFault } from './api_chat_fault.mjs';
export const ZAI_BASE = 'https://api.z.ai/api/coding/paas/v4';
const bad = () => { throw new ChatFault('chat_semantics_unavailable'); };
export function zaiHeaders(client) {
  if (!client || client.schema !== 1 || !/^\d+\.\d+\.\d+$/.test(client.referenceVersion)
    || !/^[a-f0-9]{40}$/.test(client.referenceCommit)
    || client.userAgent !== `opencode/${client.referenceVersion}` || !/^ses_[a-f0-9]{64}$/.test(client.sessionId)) bad();
  return { 'User-Agent': client.userAgent, 'x-opencode-session-id': client.sessionId,
    'x-session-affinity': client.sessionId, 'X-Session-Id': client.sessionId };
}

/** Keep provider defaults and complete thinking history; strip native-only hints. */
export function zaiRequest(chat, policy) {
  if (chat.tools.length && chat.parallel_tool_calls !== true || chat.service_tier != null && chat.service_tier !== 'default') bad();
  const request = { ...chat };
  for (const key of ['store','parallel_tool_calls','service_tier','prompt_cache_key']) delete request[key];
  request.tools = chat.tools.map(tool => {
    const definition = { ...tool.function }; delete definition.strict;
    return { type: 'function', function: definition };
  });
  request.thinking = { type: policy.reasoning === 'none' || policy.selectedEffort === 'none' ? 'disabled' : 'enabled', clear_thinking: false };
  if (policy.reasoningFacts?.mandatory && request.thinking.type === 'disabled') bad();
  const family = /(?:^|\/)glm-(\d+)(?:\.(\d+))?(?:-|$)/i.exec(request.model);
  if (request.tools.length && family && (Number(family[1]) > 4 || Number(family[1]) === 4 && Number(family[2] ?? 0) >= 6)) request.tool_stream = true;
  return request;
}
