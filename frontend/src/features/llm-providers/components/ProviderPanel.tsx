import { deferView } from '../../../app/DeferredView';
import type { Provider } from '../../../../../shared/llm-providers.js';
import type { ProviderApi } from '../useProviders';
const NewProvider = deferView(() => import('./NewProvider').then(module=>({default:module.NewProvider})));
const ProviderDetails = deferView(() => import('./ProviderDetails').then(module=>({default:module.ProviderDetails})));
import type { ApiProvider } from '../../../../../shared/api-providers';
const ApiProviderDetails = deferView(() => import('./ApiProviderDetails').then(module=>({default:module.ApiProviderDetails})));
import type { ClaudeSubscriptionProvider } from '../../../../../shared/claude-subscription';
const ClaudeProviderDetails = deferView(() => import('./ClaudeProviderDetails').then(module=>({default:module.ClaudeProviderDetails})));
import type { LeaveGuard } from './ApiConnectionForm';
import '../styles.css';
import { useCallback } from 'react';

export function ProviderPanel({ provider, api, select, setLeaveGuard }: {
  provider?: Provider | ApiProvider | ClaudeSubscriptionProvider; api: ProviderApi; select: (id: string | null) => void; setLeaveGuard?: LeaveGuard;
}) {
  const removed = useCallback(() => select(null), [select]);
  const native = provider?.type === 'api' && provider.kind === 'codex-subscription' ? api.nativeProviders.find(p => p.id === provider.id) : undefined;
  return <section className="provider-content" aria-label="AI provider settings">
    {api.error && <div className="provider-alert" role="alert">{api.error}<button type="button" onClick={() => void api.reload()}>Retry</button></div>}
    {api.apiError && <div className="provider-alert" role="alert">{api.apiError}<button type="button" onClick={() => void api.reload()}>Reload API connections</button></div>}
    {api.claudeError && <div className="provider-alert" role="alert">{api.claudeError}<button type="button" onClick={() => void api.reload()}>Reload Claude subscriptions</button></div>}
    {native && provider?.type === 'api' ? <ProviderDetails key={`${native.id}:${native.status}:${native.account?.scope ?? ''}`} initial={native} connection={provider} api={api} removed={removed} setLeaveGuard={setLeaveGuard} /> : provider?.type === 'claude-subscription' ? <ClaudeProviderDetails key={provider.id} initial={provider} api={api} removed={removed} /> : provider?.type === 'api' ? <ApiProviderDetails key={provider.id} initial={provider} api={api} removed={removed} setLeaveGuard={setLeaveGuard} /> : provider ? <ProviderDetails key={`${provider.id}:${provider.status}:${provider.account?.scope ?? provider.account?.email ?? ''}`} initial={provider} api={api} removed={removed} />
      : <NewProvider api={api} created={select} setLeaveGuard={setLeaveGuard} />}
  </section>;
}

