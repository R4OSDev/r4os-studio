/** Z.AI Coding Plan wire compatibility; no agent loop or provider fallback.
 * OpenCode v1.19.5, MIT, packages/opencode/src/session/llm/request.ts.
 * See THIRD-PARTY-ZAI.md. This reference's non-OpenCode-provider branch
 * sends its User-Agent and session affinity, without x-opencode-client.
 */
import { ChatFault } from './api_chat_fault.mjs';
export const ZAI_BASE = 'https://api.z.ai/api/coding/paas/v4';
export const ZAI_ERRORS = Object.freeze({
  '1302': 'rate_limit_exceeded', '1305': 'api_service_unavailable',
  '1308': 'zai_subscription_exhausted', '1310': 'zai_subscription_exhausted',
  '1309': 'zai_subscription_expired', '1314': 'zai_subscription_expired',
  '1311': 'zai_model_unavailable', '1313': 'zai_subscription_restricted',
  '1315': 'zai_subscription_key_type',
  ...Object.fromEntries(['1316','1317','1318','1319','1320','1321'].map(code => [code, 'zai_subscription_exhausted'])),
});
export const ZAI_MESSAGES = Object.freeze({
  zai_subscription_exhausted: 'The Z.AI subscription allowance is exhausted. Check its actual limits and reset.',
  zai_subscription_expired: 'The Z.AI subscription has expired. Review the subscription before continuing.',
  zai_model_unavailable: 'This Z.AI subscription cannot access the selected model.',
  zai_subscription_restricted: 'Z.AI has restricted this subscription. Review its account status.',
  zai_subscription_key_type: 'This Z.AI key belongs to a different subscription product.',
});
/** Native evidence only. Unknown reset values never become a local timer. */
export function zaiFailure(value, status = null, retryAfter = null, observedAt = Date.now()) {
  const code = String(value?.error?.code ?? value?.code ?? '');
  if (!Object.hasOwn(ZAI_ERRORS, code)) return null;
  const native = value?.error?.nextResetTime ?? value?.nextResetTime;
  let resetAt = null;
  if (typeof native === 'number' && Number.isFinite(native) && native > 0 && native <= 8640000000000000) resetAt = new Date(native).toISOString();
  const flush = value?.error?.next_flush_time ?? value?.next_flush_time;
  if (!resetAt && typeof flush === 'string' && flush.length <= 40 && /(?:Z|[+-]\d\d:\d\d)$/.test(flush) && Number.isFinite(Date.parse(flush))) resetAt = new Date(flush).toISOString();
  // Retry-After is a provider instruction, not an estimate from a quota window.
  if (!resetAt && typeof retryAfter === 'string' && retryAfter.length <= 80) {
    const timestamp = /^\d{1,8}$/.test(retryAfter) ? observedAt + Number(retryAfter) * 1000 : Date.parse(retryAfter);
    if (Number.isFinite(timestamp) && timestamp > observedAt && timestamp <= 8640000000000000) resetAt = new Date(timestamp).toISOString();
  }
  return { code, resetAt, httpStatus: status, safeCode: ZAI_ERRORS[code] };
}
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
