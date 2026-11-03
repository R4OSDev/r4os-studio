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
