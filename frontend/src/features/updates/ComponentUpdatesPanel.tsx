import { useEffect, useState } from 'react';
import type { ComponentKind, ComponentsStatus } from '../../../../shared/components';
import './styles.css';

export const componentNames: Record<ComponentKind, string> = { sdk: 'SDK', contract: 'Contract', libraries: 'Libraries', zig: 'Zig', qemu: 'QEMU', codex: 'Codex', r4os: 'R4OS Releases' };

export function ComponentUpdatesPanel({ kind }: { kind: ComponentKind }) {
  const [status, setStatus] = useState<ComponentsStatus | null>(null);
  const [error, setError] = useState('');
  const [requesting, setRequesting] = useState(false);
  const [selection, setSelection] = useState('');
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    async function refresh() {
      try {
        const response = await fetch('/api/updates/components', { cache: 'no-store', signal: controller.signal });
        if (!response.ok) throw new Error('Component versions could not be loaded.');
        setStatus(await response.json()); setLoaded(true);
      } catch (cause) { if (!controller.signal.aborted) setError((cause as Error).message); }
    }
    void refresh();
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(); }, 2000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, []);
  const inventory = status?.components[kind];
  const active = inventory?.installed.find((value) => value.id === inventory.activeId);
  const selected = selection || inventory?.activeId || inventory?.installed[0]?.id || '';
  const busy = requesting || status?.job?.phase === 'working';
  async function action(command: 'check' | 'download' | 'default', id?: string, older = false) {
    if (!status) return;
    setRequesting(true); setError('');
    try {
      const response = await fetch(`/api/updates/components/${command}`, { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-csrf-token': status.csrfToken ?? '' },
        body: JSON.stringify({ kind, ...(id ? { id } : {}), ...(older ? { older } : {}) }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message ?? 'The component operation failed.');
      setStatus({ ...result, csrfToken: status.csrfToken });
    } catch (cause) { setError((cause as Error).message); }
    finally { setRequesting(false); }
  }
  const versions = [...(inventory?.available ?? []).map((remote) => ({ ...remote, ...inventory?.installed.find((local) => local.id === remote.id) })), ...(inventory?.installed ?? []).filter((local) => !inventory?.available.some((remote) => remote.id === local.id))];
  return <section className="updates-content" aria-label={`${componentNames[kind]} updates`}>
    <div className="updates-card">
      <div className="updates-title"><h2>{componentNames[kind]}</h2><span className="updates-version">{active ? `Default: ${active.version}` : 'No active default'}</span></div>
      <p className="updates-help">Download versions and choose which installed version to use by default. Projects can use their own versions when project profiles are available.</p>
      {kind === 'sdk' && <p className="updates-help">Selecting an SDK also selects its required installed Contract and compiler. Existing project pins stay in place.</p>}
      {kind === 'codex' && <p className="updates-help">Only the latest Codex version is available to download. Previously installed versions remain selectable.</p>}
      {kind === 'r4os' && <p className="updates-help">The default is used for new virtual machines. Existing virtual machines keep their selected release.</p>}
      {!loaded && !error && <p role="status">Loading component versions…</p>}
      {status && !status.enabled && <p className="updates-alert">{status.message}</p>}
      {(error || inventory?.error) && <p className="updates-alert" role="alert">{error || inventory?.error}</p>}
      {status?.job && <div className={status.job.phase === 'failed' ? 'updates-alert' : 'updates-state'} role="status">
        <span>{componentNames[status.job.kind]}: {status.job.error || status.job.message}
          {status.job.total ? ` (${Math.min(100, Math.round((status.job.received ?? 0) / status.job.total * 100))}%)` : ''}</span>
      </div>}
      <div className="updates-actions"><button type="button" disabled={!status?.enabled || busy} onClick={() => void action('check')}>Check for updates</button></div>
      <div className="component-default">
        <label htmlFor={`default-${kind}`}>Active default</label>
        <select id={`default-${kind}`} value={selected} disabled={!status?.enabled || busy || !inventory?.installed.length} onChange={(event) => setSelection(event.target.value)}>
          {!inventory?.installed.length && <option value="">No installed versions</option>}
          {inventory?.installed.map((value) => <option key={value.id} value={value.id}>{value.version}{value.revision ? ` · ${value.revision.slice(0, 8)}` : ''}{value.external ? ' · system installation' : ''}</option>)}
        </select>
        <button type="button" disabled={!status?.enabled || busy || !selected || selected === inventory?.activeId} onClick={() => void action('default', selected)}>Use as default</button>
      </div>
      <div className="component-version-list">
        {versions.map((value) => {
          const installed = inventory?.installed.some((local) => local.id === value.id);
          const downloadable = inventory?.available.some((remote) => remote.id === value.id) && (kind !== 'codex' || value.id === inventory?.latestId);
          return <div className="component-version" key={value.id}>
            <div><strong>{value.version}</strong>{value.id === inventory?.latestId && <span className="component-label">Latest</span>}{value.id === inventory?.activeId && <span className="component-label">Default</span>}
              {value.revision && <small>{value.revision}</small>}{value.sha256 && <small>{value.external ? 'Binary' : kind === 'r4os' && installed ? 'Disk' : 'Archive'} SHA-256: {value.sha256}</small>}</div>
            {installed ? <span className="component-label">Installed</span> : <button type="button" disabled={!downloadable || busy} onClick={() => void action('download', value.id)}>Download</button>}
          </div>;
        })}
        {loaded && !versions.length && <p className="updates-help">No versions loaded. Check for updates to retrieve the official version list.</p>}
      </div>
      {inventory?.hasMore && kind !== 'codex' && <div className="updates-actions"><button type="button" disabled={busy} onClick={() => void action('check', undefined, true)}>Load older versions</button></div>}
      {inventory?.checkedAt && <p className="updates-help">Last checked: {new Date(inventory.checkedAt).toLocaleString()}</p>}
    </div>
  </section>;
}
