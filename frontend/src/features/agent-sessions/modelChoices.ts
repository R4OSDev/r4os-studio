import type { AgentSession, SessionOptions } from '../../../../shared/agent-sessions';
type Provider = SessionOptions['providers'][number];
export const providerLabel = (provider: Provider) => provider.name + (provider.type === 'api' ? ' · API' : '') + (provider.unavailableReason ? ' · unavailable' : '');
export const availableModels = (provider?: Provider) => provider?.models.filter(model => model.available !== false) ?? [];
export function providerAllowed(session: AgentSession, provider: Provider) {
  return session.engine.api ? provider.id === session.providerId : provider.type !== 'api';
}
