import { useCallback, useEffect, useRef, useState } from 'react';
import type { ComponentsStatus } from '../../../../shared/components';

type SdkRequest = { kind: 'sdk'; id: string; requestId: string; expectedProfileRevision: string; manifestSha256?: string };
type Pending = { command: 'download' | 'default'; body: SdkRequest };
const pendingKey = 'studio-sdk-operation';
function remembered(): Pending | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(pendingKey) ?? 'null');
    return value && ['download', 'default'].includes(value.command) && value.body?.kind === 'sdk'
      && /^[a-f0-9]{40}$/.test(value.body.id) && /^[a-f0-9-]{36}$/.test(value.body.requestId)
      && /^[a-f0-9]{64}$/.test(value.body.expectedProfileRevision) ? value as Pending : null;
  } catch { return null; }
}
function requestId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function SdkUpdatesPanel() {
  const [status, setStatus] = useState<ComponentsStatus | null>(null);
  const [error, setError] = useState(''), [selection, setSelection] = useState('');
  const [requesting, setRequesting] = useState(false);
  const [pending, setPending] = useState<Pending | null>(remembered);
  const pendingRef = useRef(pending);
  const receive = useCallback((value: ComponentsStatus) => {
    setStatus(value);
    if (pendingRef.current && ((value.job?.requestId === pendingRef.current.body.requestId && value.job.phase === 'complete')
      || value.sdkOperation?.requestId === pendingRef.current.body.requestId)) {
      try { sessionStorage.removeItem(pendingKey); } catch { /* In-memory receipt remains sufficient for this page. */ }
      pendingRef.current = null; setPending(null);
    }
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    async function refresh() {
      try {
        const response = await fetch('/api/updates/components', { cache: 'no-store', signal: controller.signal });
        if (!response.ok) throw new Error('SDK versions could not be loaded.');
        receive(await response.json());
      } catch (cause) { if (!controller.signal.aborted) setError((cause as Error).message); }
    }
    void refresh();
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(); }, 2000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [receive]);
  const inventory = status?.components.sdk;
  const versions = [...(inventory?.available ?? []).map((remote) => ({ ...remote, ...inventory?.installed.find((local) => local.id === remote.id) })),
    ...(inventory?.installed ?? []).filter((local) => !inventory?.available.some((remote) => remote.id === local.id))];
  const selectedId = selection || inventory?.activeId || inventory?.latestId || versions[0]?.id || '';
  const selected = versions.find((value) => value.id === selectedId);
  const active = inventory?.installed.find((value) => value.id === inventory.activeId);
  const capable = status?.enabled && status.features?.sdkSelection === 1;
  const busy = requesting || status?.job?.phase === 'working';
  const blocked = !capable || busy || !!pending;

  async function send(command: 'check' | 'download' | 'default', body: Record<string, unknown>) {
    if (!status) return;
    setRequesting(true); setError('');
    try {
      const response = await fetch(`/api/updates/components/${command}`, { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-csrf-token': status.csrfToken ?? '' }, body: JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message ?? 'The SDK operation failed.');
      receive({ ...result, csrfToken: status.csrfToken });
    } catch (cause) { setError((cause as Error).message); }
    finally { setRequesting(false); }
  }
  function begin(command: 'download' | 'default', id: string) {
    if (blocked || !status?.profileRevision) return;
    const sdk = versions.find((value) => value.id === id);
    if (sdk?.sdkSet?.state !== 'ready') return;
    const value: Pending = { command, body: { kind: 'sdk', id, requestId: requestId(),
      expectedProfileRevision: status.profileRevision, manifestSha256: sdk.sdkSet.manifestSha256 } };
    try { sessionStorage.setItem(pendingKey, JSON.stringify(value)); }
    catch { setError('The SDK request could not be retained. Enable browser session storage and retry.'); return; }
    pendingRef.current = value; setPending(value);
    void send(command, value.body);
  }
  function dismiss() {
    if (busy) return;
    try { sessionStorage.removeItem(pendingKey); } catch { /* Keep the current page usable. */ }
    pendingRef.current = null; setPending(null); setError('');
  }
  const sdkSet = selected?.sdkSet;
  return <section className="updates-content" aria-label="SDK updates"><div className="updates-card">
    <div className="updates-title"><h2>SDK</h2><span className="updates-version">{active ? `Default: ${active.version}` : 'No active default'}</span></div>
    <p className="updates-help">Contract and Libraries follow the selected SDK. Existing projects keep their pinned versions.</p>
    {!status && !error && <p role="status">Loading SDK versions…</p>}
    {status && !status.enabled && <p className="updates-alert">{status.message}</p>}
    {status?.enabled && !capable && <p className="updates-alert">The component service is switching releases. Retry shortly.</p>}
    {(error || inventory?.error) && <p className="updates-alert" role="alert">{error || inventory?.error}</p>}
    {status?.job && <div className={status.job.phase === 'failed' ? 'updates-alert' : 'updates-state'} role="status">
      {status.job.error || status.job.message}{status.job.total ? ` (${Math.min(100, Math.round((status.job.received ?? 0) / status.job.total * 100))}%)` : ''}
    </div>}
    {pending && !busy && <div className="sdk-pending" role="status"><p>Retry the retained SDK operation, or dismiss it before making a new selection.</p>
      <div className="updates-actions"><button type="button" disabled={!capable} onClick={() => void send(pending.command, pending.body)}>Retry operation</button>
        <button type="button" onClick={dismiss}>Dismiss</button></div>
    </div>}
    <div className="updates-actions"><button type="button" disabled={blocked} onClick={() => void send('check', { kind: 'sdk' })}>Check for updates</button></div>
    <div className="component-default"><label htmlFor="sdk-version">SDK version</label>
      <select id="sdk-version" value={selectedId} disabled={!capable || busy || !!pending || !versions.length} onChange={(event) => setSelection(event.target.value)}>
        {!versions.length && <option value="">No versions loaded</option>}
        {versions.map((value) => <option key={value.id} value={value.id}>{value.version} · {value.id.slice(0, 8)}</option>)}
      </select>
      <button type="button" disabled={blocked || sdkSet?.state !== 'ready' || sdkSet.active} onClick={() => begin('default', selectedId)}>Use as default</button>
    </div>
    {sdkSet?.state === 'ready' && sdkSet.components ? <div className="sdk-set-parts" aria-label="SDK components">
      {(['sdk', 'contract', 'libraries'] as const).map((kind) => {
        const part = sdkSet.components![kind];
        return <div key={kind}><h3>{kind === 'sdk' ? 'SDK' : kind === 'contract' ? 'Contract' : 'Libraries'}</h3>
          <strong>{part.version}</strong><code title={part.revision}>{part.revision.slice(0, 12)}</code>
          <span className="component-label">{part.installed ? 'Installed' : 'Not installed'}</span></div>;
      })}
    </div> : sdkSet && <p className={sdkSet.state === 'unavailable' ? 'updates-alert' : 'updates-help'} role="status">{sdkSet.reason}</p>}
    {active?.sdkSet?.state === 'ready' && !active.sdkSet.active && <p className="updates-help">The default SDK set is incomplete. Select it and use it as default to complete the set.</p>}
    <div className="component-version-list">{versions.map((value) => <div className="component-version" key={value.id}>
      <div><strong>{value.version}</strong>{value.id === inventory?.latestId && <span className="component-label">Latest</span>}
        {value.id === inventory?.activeId && <span className="component-label">Default</span>}<small>{value.id}</small>
        {value.sdkSet?.state === 'unavailable' && <small>{value.sdkSet.reason}</small>}
      </div>
      {value.sdkSet?.complete ? <span className="component-label">Installed</span>
        : <button type="button" disabled={blocked || value.sdkSet?.state !== 'ready'} onClick={() => begin('download', value.id)}>Download</button>}
    </div>)}</div>
    {status && !versions.length && <p className="updates-help">Check for updates to load SDK versions.</p>}
    {inventory?.hasMore && <div className="updates-actions"><button type="button" disabled={blocked} onClick={() => void send('check', { kind: 'sdk', older: true })}>Load older versions</button></div>}
    {inventory?.checkedAt && <p className="updates-help">Last checked: {new Date(inventory.checkedAt).toLocaleString()}</p>}
  </div></section>;
}
