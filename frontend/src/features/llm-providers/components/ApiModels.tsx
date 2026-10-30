import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type { ApiCapability, ApiEffort, ApiModel, ApiModelCatalog, ApiModelFacts, ApiProvider } from '../../../../../shared/api-providers';
import type { ProviderApi } from '../useProviders';
import { useApiMutation } from '../useApiMutation';
import type { LeaveGuard } from './ApiConnectionForm';

const labels = { text: 'Text', functionTools: 'Function tools', streaming: 'Streaming', reasoning: 'Reasoning', imageInput: 'Image input', webSearch: 'Web search', imageGeneration: 'Image generation', goals: 'Goal' };
const efforts: ApiEffort[] = ['none', 'minimal', 'low', 'medium', 'high', 'xhigh'];
const empty = (): ApiModelFacts => ({ id: '', name: '', contextWindow: null, maxOutputTokens: null,
  capabilities: { text: 'unknown', functionTools: 'unknown', streaming: 'unknown', reasoning: 'unknown', imageInput: 'unknown', webSearch: 'unknown', imageGeneration: 'unknown', goals: 'unknown' }, efforts: [], defaultEffort: null });

export function ApiModels({ api, provider, setLeaveGuard }: { api: ProviderApi; provider: ApiProvider; setLeaveGuard: LeaveGuard }) {
  const [catalog, setCatalog] = useState<ApiModelCatalog | null>(null), [error, setError] = useState('');
  const [draft, setDraft] = useState<ApiModelFacts | null>(null), [notice, setNotice] = useState('');
  const mutation = useApiMutation(api, provider.id, true), request = api.request;
  const { read, pending } = mutation;
  const reload = useCallback(async () => {
    try { setCatalog(await request<ApiModelCatalog>(`/api-connections/${provider.id}/models`)); setError(''); }
    catch (cause) { setError((cause as Error).message); }
  }, [request, provider.id]);
  useEffect(() => {
    let active = true;
    void request<ApiModelCatalog>(`/api-connections/${provider.id}/models`).then(value => { if (active) { setCatalog(value); setError(''); } })
      .catch((cause: Error) => { if (active) setError(cause.message); });
    return () => { active = false; };
  }, [request, provider.id]);
  useEffect(() => {
    if (!pending || pending.operation !== 'check') return;
    let attempts = 0;
    const timer = setInterval(() => { if (++attempts >= 16) clearInterval(timer); void read().then(result => { if (result?.state === 'unknown') clearInterval(timer); if (result?.state === 'complete') { setNotice('Metadata check completed. This does not confirm model access or run inference.'); void reload(); } }); }, 2000);
    return () => clearInterval(timer);
  }, [pending, read, reload]);
  useEffect(() => {
    setLeaveGuard(() => !mutation.busy && (!draft || window.confirm('Discard unsaved model facts?')));
    const warn = (event: BeforeUnloadEvent) => { if (draft) event.preventDefault(); };
    window.addEventListener('beforeunload', warn);
    return () => { setLeaveGuard(() => true); window.removeEventListener('beforeunload', warn); };
  }, [draft, mutation.busy, setLeaveGuard]);
  function edit(model?: ApiModel) {
    if (draft && !window.confirm('Discard unsaved model facts?')) return;
    setDraft(model ? { id: model.id, name: model.name, contextWindow: model.contextWindow, maxOutputTokens: model.maxOutputTokens,
      capabilities: { ...model.declaredCapabilities }, efforts: [...model.efforts], defaultEffort: model.defaultEffort } : empty());
    setNotice('');
  }
  async function save(event: FormEvent) {
    event.preventDefault(); if (!draft || !catalog) return;
    const result = await mutation.send('model', { providerRevision: provider.revision, catalogRevision: catalog.revision, model: draft }, !!pending);
    if (result?.state === 'complete') { setDraft(null); setNotice('Explicit model facts saved. No model request was made.'); await reload(); }
  }
  const patch = (values: Partial<ApiModelFacts>) => setDraft(previous => previous ? { ...previous, ...values } : previous);
  return <section className="api-models" aria-labelledby="api-models-title">
    <div className="usage-heading"><div><h3 id="api-models-title">Models</h3><p>Cached metadata and explicitly configured model contracts.</p></div><button type="button" className="button-secondary" disabled={!provider.enabled || mutation.busy || !!pending || !!draft} onClick={() => {
      setNotice(''); void mutation.send('check', { providerRevision: provider.revision });
    }}>{pending?.operation === 'check' ? 'Checking metadata…' : 'Check connection / refresh models'}</button></div>
    <p className="field-help">Check connection reads this endpoint’s Models API once from the Studio host worker. It does not generate text or verify access to individual models. Exact manual IDs are supported when no model list is available.</p>
    {provider.server && provider.server !== 'custom' && <p className="field-help">{provider.server === 'ollama' ? 'Ollama' : 'LM Studio'}: a listed model may be unloaded. Enter the actual configured context window and confirm text, streaming and function tools for an explicitly nonreasoning model. Image and reasoning history are unavailable in this server adapter. Studio does not install, download, load or reconfigure models during metadata checks.</p>}
    {catalog?.checkedAt && <p className="field-help">Last metadata: <time dateTime={catalog.checkedAt}>{new Date(catalog.checkedAt).toLocaleString()}</time>{!catalog.metadataCurrent ? ' · earlier connection revision' : ''}</p>}
    {catalog?.stale && <p className="provider-alert">These facts belong to earlier connection settings. Refresh metadata or explicitly save current model facts before starting a run.</p>}
    {catalog?.truncated && <p className="field-help">The catalog is limited to 256 models. Add any other exact ID manually.</p>}
    {!catalog && !error && <p role="status">Loading cached models…</p>}
    {error && <p className="provider-alert" role="alert">{error}<button type="button" onClick={() => void reload()}>Reload cached models</button></p>}
    {mutation.error && <p className="provider-alert" role="alert">{mutation.error}</p>}
    {notice && <p className="field-help" role="status">{notice}</p>}
    {pending && <div className="provider-alert" role="status"><span>Original model request: {pending.requestId}</span><button type="button" disabled={mutation.busy} onClick={() => void read().then(result => { if (result?.state === 'complete') { setDraft(null); void reload(); } })}>Read original result</button></div>}
    {pending && mutation.notFound && pending.operation === 'check' && <button type="button" className="button-secondary" disabled={mutation.busy} onClick={() => void mutation.send('check', { providerRevision: provider.revision }, true)}>Retry same metadata check</button>}
    <div className="api-model-list">{catalog?.models.map(model => <details key={model.id}>
      <summary><span><strong>{model.name}</strong><code>{model.id}</code></span><span className="provider-status">{catalog.stale ? 'Stale' : model.available ? 'Configured' : 'Needs model facts'}</span></summary>
      <p className="field-help">Source: {model.source?.kind === 'manual' ? 'Explicit manual configuration' : model.source?.kind === 'metadata' ? 'Models API metadata' : 'Unknown'}{model.source?.recordedAt ? ` · ${new Date(model.source.recordedAt).toLocaleString()}` : ''}</p>
      {model.source?.url && <p className="field-help api-model-source">{model.source.url}</p>}
      <dl className="provider-properties"><div><dt>Context / output</dt><dd>{model.contextWindow ?? 'Unknown'} / {model.maxOutputTokens ?? 'Unknown'} tokens</dd></div><div><dt>Reasoning levels</dt><dd>{model.efforts.length ? model.efforts.join(', ') : 'Unknown'} · Default: {model.defaultEffort ?? 'Unknown'}</dd></div>
        {Object.entries(labels).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{model.capabilities[key as keyof typeof labels]}{model.capabilities[key as keyof typeof labels] !== model.declaredCapabilities[key as keyof typeof labels] ? ` · model: ${model.declaredCapabilities[key as keyof typeof labels]}; unavailable in this adapter` : ''}</dd></div>)}</dl>
      {!!model.unavailableReasons.length && <p className="field-help">{model.unavailableReasons.join(' ')}</p>}
      <button type="button" className="button-secondary" disabled={mutation.busy || !!pending} onClick={() => edit(model)}>Edit model facts</button>
    </details>)}</div>
    {catalog && !catalog.models.length && <p className="field-help">No cached models. Check metadata or add an exact model ID.</p>}
    <p className="field-help">GOAL is provided by Studio when text, streaming and function tools are confirmed. It starts only after Play. Image input, hosted web search, image generation and Fast Mode are unavailable through these API adapters.</p>
    {!draft ? <button type="button" className="button-secondary" disabled={!catalog || mutation.busy || !!pending && !(mutation.notFound && pending.operation === 'model')} onClick={() => edit()}>{pending?.operation === 'model' ? 'Re-enter original model facts' : 'Add exact model ID'}</button>
      : <form className="provider-form api-model-form" onSubmit={event => void save(event)} aria-label="Explicit model facts">
        <h4>Explicit model facts</h4><p className="field-help">Enter facts from the model and endpoint documentation. Unknown capabilities stay unavailable for agent execution; saving does not test them.</p>
        <fieldset disabled={mutation.busy || !!pending && !mutation.notFound}>
          <label htmlFor="api-model-id">Exact model ID</label><input id="api-model-id" value={draft.id} required maxLength={200} autoComplete="off" onChange={event => patch({ id: event.target.value, ...(!draft.name || draft.name === draft.id ? { name: event.target.value } : {}) })} />
          <label htmlFor="api-model-name">Display name</label><input id="api-model-name" value={draft.name} required maxLength={200} onChange={event => patch({ name: event.target.value })} />
          <div className="api-model-limits">{(['contextWindow', 'maxOutputTokens'] as const).map(key => <div key={key}><label htmlFor={`api-model-${key}`}>{key === 'contextWindow' ? 'Context window' : 'Maximum output tokens'}</label><input id={`api-model-${key}`} type="number" min={1} max={2147483647} step={1} placeholder="Unknown" value={draft[key] ?? ''} onChange={event => patch({ [key]: event.target.value ? Number(event.target.value) : null })} /></div>)}</div>
          {(['text', 'functionTools', 'streaming', 'reasoning', 'imageInput'] as const).map(key => <div key={key}><label htmlFor={`api-model-${key}`}>{labels[key]}</label><select id={`api-model-${key}`} value={draft.capabilities[key]} onChange={event => {
            const value = event.target.value as ApiCapability; patch({ capabilities: { ...draft.capabilities, [key]: value }, ...(key === 'reasoning' ? { efforts: value === 'unsupported' ? ['none'] : [], defaultEffort: value === 'unsupported' ? 'none' : null } : {}) });
          }}><option value="unknown">Unknown</option><option value="supported">Supported</option><option value="unsupported">Unsupported</option></select></div>)}
          {draft.capabilities.reasoning === 'supported' && <><fieldset className="api-efforts"><legend>Documented reasoning levels</legend>{efforts.map(effort => <label key={effort}><input type="checkbox" checked={draft.efforts.includes(effort)} onChange={event => {
            const chosen = event.target.checked ? [...draft.efforts, effort] : draft.efforts.filter(value => value !== effort); patch({ efforts: chosen, defaultEffort: draft.defaultEffort && chosen.includes(draft.defaultEffort) ? draft.defaultEffort : null });
          }} />{effort}</label>)}</fieldset><label htmlFor="api-default-effort">Default reasoning level</label><select id="api-default-effort" required value={draft.defaultEffort ?? ''} onChange={event => patch({ defaultEffort: event.target.value as ApiEffort })}><option value="" disabled>Select documented default</option>{draft.efforts.map(value => <option key={value}>{value}</option>)}</select></>}
        </fieldset>
        <div className="provider-actions"><button className="button-primary" disabled={mutation.busy || !!pending && !mutation.notFound}>{pending ? 'Retry original model save' : 'Save model facts'}</button><button type="button" className="button-secondary" disabled={mutation.busy || !!pending} onClick={() => setDraft(null)}>Cancel model changes</button></div>
      </form>}
  </section>;
}
