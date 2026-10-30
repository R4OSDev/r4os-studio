import type { OpenRouterSettings } from '../../../../../shared/api-providers';

export interface RouterDraft { order: string; only: string; allowFallbacks: boolean; shareAttribution: boolean; appUrl: string; appTitle: string }
export const routerDraft = (value?: OpenRouterSettings): RouterDraft => ({ order: value?.order.join(', ') ?? '', only: value?.only.join(', ') ?? '',
  allowFallbacks: value?.allowFallbacks ?? false, shareAttribution: !!value?.attribution, appUrl: value?.attribution?.url ?? '', appTitle: value?.attribution?.title ?? 'R4OS Studio' });
export const routerSettings = (draft: RouterDraft): OpenRouterSettings => ({ order: draft.order.split(',').map(v => v.trim()).filter(Boolean),
  only: draft.only.split(',').map(v => v.trim()).filter(Boolean), allowFallbacks: draft.allowFallbacks,
  attribution: draft.shareAttribution ? { url: draft.appUrl.trim(), title: draft.appTitle.trim() } : null });

export function OpenRouterFields({ draft, change }: { draft: RouterDraft; change: (value: RouterDraft) => void }) {
  const patch = (value: Partial<RouterDraft>) => change({ ...draft, ...value });
  return <div className="api-router-fields">
    <h3>OpenRouter routing</h3><p className="field-help">Choose backends for the selected model using exact OpenRouter provider slugs. Support for all sent tool parameters is required.</p>
    <label htmlFor="router-order">Preferred provider order (optional)</label><input id="router-order" value={draft.order} maxLength={2048} autoComplete="off" placeholder="provider-a, provider-b/region" onChange={event => patch({ order: event.target.value })} />
    <label htmlFor="router-only">Allowed providers (optional)</label><input id="router-only" value={draft.only} maxLength={2048} autoComplete="off" placeholder="provider-a, provider-b/region" onChange={event => patch({ only: event.target.value })} />
    <p className="field-help">Up to 16 exact slugs in each list, separated by commas. When an allowlist is set, it must include each preferred provider.</p>
    <label className="api-enabled"><input type="checkbox" checked={draft.allowFallbacks} onChange={event => patch({ allowFallbacks: event.target.checked })} />Allow OpenRouter backend fallbacks</label>
    <p className="field-help">OpenRouter may try another allowed backend within the same request.</p>
    <label className="api-enabled"><input type="checkbox" checked={draft.shareAttribution} onChange={event => patch({ shareAttribution: event.target.checked })} />Share app attribution</label>
    <p className="field-help">Send the app URL and title to OpenRouter for its app rankings and analytics.</p>
    {draft.shareAttribution && <><label htmlFor="router-app-url">App URL</label><input id="router-app-url" type="url" required maxLength={512} value={draft.appUrl} placeholder="https://example.com/your-app" onChange={event => patch({ appUrl: event.target.value })} />
      <label htmlFor="router-app-title">App title</label><input id="router-app-title" required maxLength={80} value={draft.appTitle} onChange={event => patch({ appTitle: event.target.value })} /></>}
  </div>;
}
