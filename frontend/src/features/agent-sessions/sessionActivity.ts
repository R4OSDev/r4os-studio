import type { AgentEvent } from '../../../../shared/agent-sessions';
export type SessionActivity = { scope: 'project' | 'skill'; ownerId: string; sessionId: string; event?: AgentEvent; connected?: boolean };
const name = 'studio-session-activity';
export function publishSessionActivity(value: SessionActivity) { window.dispatchEvent(new CustomEvent(name, { detail: value })); }
export function watchSessionActivity(scope: string, ownerId: string, sessionId: string, receive: (value: SessionActivity) => void) {
  const listen = (event: Event) => {
    const value = (event as CustomEvent<SessionActivity>).detail;
    if (value?.scope === scope && value.ownerId === ownerId && value.sessionId === sessionId) receive(value);
  };
  window.addEventListener(name, listen);
  return () => window.removeEventListener(name, listen);
}
export function watchVisible(wake: () => void) {
  const visible = () => { if (!document.hidden) wake(); };
  window.addEventListener('focus', visible); window.addEventListener('online', visible); document.addEventListener('visibilitychange', visible);
  return () => { window.removeEventListener('focus', visible); window.removeEventListener('online', visible); document.removeEventListener('visibilitychange', visible); };
}
