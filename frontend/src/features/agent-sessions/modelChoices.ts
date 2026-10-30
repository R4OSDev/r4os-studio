import type { AgentSession, SessionOptions } from '../../../../shared/agent-sessions';
type Provider = SessionOptions['providers'][number];
export const providerLabel = (provider: Provider) => provider.name + (provider.type === 'api' ? ' · API' : provider.type === 'claude-subscription' ? ' · Claude subscription' : '') + (provider.unavailableReason ? ' · unavailable' : '');
export const availableModels = (provider?: Provider) => provider?.models.filter(model => model.available !== false) ?? [];
export const effortLabel = (effort: string, provider?: Provider) => effort || (provider?.type === 'claude-subscription' ? 'Native default' : 'Provider default');
export function providerAllowed(session: AgentSession, provider: Provider) {
  if (session.engine.kind === 'claude-code') return provider.id === session.providerId;
  if (provider.type === 'claude-subscription') return false;
  return session.engine.api ? provider.id === session.providerId : provider.type !== 'api';
}
