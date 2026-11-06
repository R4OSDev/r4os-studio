import { useState } from 'react';
import type { ComponentKind } from '../../../../shared/components';
import './styles.css';
import { SdkUpdatesPanel } from './SdkUpdatesPanel';
import { useComponents } from './useComponents';
import { VmReleaseBatchActions } from './VmReleaseBatch';

export const componentNames: Record<ComponentKind | 'c', string> = { sdk: 'SDK', contract: 'Contract', libraries: 'Libraries', zig: 'Zig', c: 'C', rust: 'Rust', qemu: 'QEMU', codex: 'Codex', r4upack: 'R4UPack', r4os: 'R4OS Releases' };

export function ComponentUpdatesPanel({ kind: viewKind }: { kind: ComponentKind | 'c' }) {
  return viewKind === 'sdk' || viewKind === 'contract' || viewKind === 'libraries' ? <SdkUpdatesPanel /> : <ToolUpdatesPanel kind={viewKind} />;
}

function ToolUpdatesPanel({ kind: viewKind }: { kind: ComponentKind | 'c' }) {
  const kind: ComponentKind = viewKind === 'c' ? 'zig' : viewKind;
  const { status, error, setError, receive, refresh, refreshing } = useComponents();
  const [requesting, setRequesting] = useState(false);
  const [selection, setSelection] = useState('');
  const loaded = !!status;
  const inventory = status?.components[kind];
  const active = inventory?.installed.find((value) => value.id === inventory.activeId);
  const selected = selection || inventory?.activeId || inventory?.installed[0]?.id || '';
  const busy = requesting || refreshing || !!error || status?.job?.phase === 'working';
  const sdkOwned = (kind === 'zig' || kind === 'rust') && status?.features?.sdkProfiles === 1;
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
      receive({ ...result, csrfToken: status.csrfToken });
    } catch (cause) { setError((cause as Error).message); }
    finally { setRequesting(false); }
  }
  const versions = [...(inventory?.available ?? []).map((remote) => ({ ...remote, ...inventory?.installed.find((local) => local.id === remote.id) })), ...(inventory?.installed ?? []).filter((local) => !inventory?.available.some((remote) => remote.id === local.id))];
  return <section className="updates-content" aria-label={`${componentNames[viewKind]} updates`}>
    <div className="updates-card">
      <div className="updates-title"><h2>{componentNames[viewKind]}</h2><span className="updates-version">{active ? `Default: ${active.version}` : 'No active default'}</span></div>
      <p className="updates-help">{sdkOwned ? 'The selected SDK determines this compiler. Select a complete SDK package to change its tools.' : kind === 'r4upack' ? 'Build the qualified native packer separately, then choose its active profile. Existing project SDK and compiler pins stay in place.' : 'Download versions and choose which installed version to use by default. Projects can use their own versions when project profiles are available.'}</p>
      {kind === 'r4upack' && <p className="updates-help">The displayed version identifies Distribution sources; profile IDs, source revisions and SHA-256 identify the tool. The packer option --version sets package metadata. Building does not select a profile or package a project.</p>}
      {viewKind === 'c' && <p className="updates-help">C uses the compiler provided by the selected SDK's Zig toolset.</p>}
      {kind === 'codex' && <p className="updates-help">Only the latest Codex version is available to download. Previously installed versions remain selectable.</p>}
      {kind === 'rust' && <p className="updates-help">Compiler and build tools follow the SDK's original tool profile.</p>}
      {kind === 'r4os' && <p className="updates-help">The default is used for new virtual machines. Existing virtual machines keep their selected release.</p>}
      <div className="updates-actions"><button type="button" disabled={requesting || refreshing} onClick={() => void refresh()}>{refreshing ? 'Checking inventory…' : 'Refresh inventory'}</button></div>
      {status?.inventory?.checkedAt && <p className="updates-help">Inventory checked: {new Date(status.inventory.checkedAt).toLocaleString()}</p>}
      {!loaded && !error && <p role="status">Loading component versions…</p>}
      {status && !status.enabled && <p className="updates-alert">{status.message}</p>}
      {(error || inventory?.error) && <p className="updates-alert" role="alert">{error || inventory?.error}</p>}
      {status?.job && <div className={status.job.phase === 'failed' ? 'updates-alert' : 'updates-state'} role="status">
        <span>{componentNames[status.job.kind]}: {status.job.error || status.job.message}
          {status.job.total ? ` (${Math.min(100, Math.round((status.job.received ?? 0) / status.job.total * 100))}%)` : ''}</span>
      </div>}
      {!sdkOwned && <div className="updates-actions"><button type="button" disabled={!status?.enabled || busy} onClick={() => void action('check')}>{kind === 'r4upack' ? 'Check qualified profiles' : 'Check for updates'}</button></div>}
      {!sdkOwned && <div className="component-default">
        <label htmlFor={`default-${kind}`}>Active default</label>
        <select id={`default-${kind}`} value={selected} disabled={!status?.enabled || busy || !inventory?.installed.length} onChange={(event) => { setSelection(event.target.value); void refresh(); }}>
          {!inventory?.installed.length && <option value="">No installed versions</option>}
          {inventory?.installed.map((value) => <option key={value.id} value={value.id}>{value.version}{value.sdkVersion ? ` · SDK ${value.sdkVersion}` : ''}{value.revision ? ` · ${value.revision.slice(0, 8)}` : ''}{value.external ? ' · system installation' : ''}</option>)}
        </select>
        <button type="button" disabled={!status?.enabled || busy || !selected || !inventory?.installed.some(value => value.id === selected) || selected === inventory?.activeId} onClick={() => void action('default', selected)}>Use as default</button>
        {kind === 'r4os' && <VmReleaseBatchActions choice={inventory?.installed.find(value => value.id === selected)} disabled={!status?.enabled || busy}
          older={!!inventory?.available.some(value => value.version.localeCompare(inventory.installed.find(item => item.id === selected)?.version ?? '', undefined, { numeric: true }) > 0)} />}
      </div>}
      <div className="component-version-list">
        {versions.map((value) => {
          const installed = inventory?.installed.some((local) => local.id === value.id);
          const downloadable = !sdkOwned && inventory?.available.some((remote) => remote.id === value.id) && (kind !== 'codex' || value.id === inventory?.latestId);
          return <div className="component-version" key={value.id}>
            <div><strong>{value.version}</strong>{value.sdkVersion && <span className="component-label">SDK {value.sdkVersion}</span>}{value.id === inventory?.latestId && <span className="component-label">Latest</span>}{value.id === inventory?.activeId && <span className="component-label">Default</span>}
              {value.revision && <small>{value.revision}</small>}
              {kind === 'rust' && value.cargoVersion && <small>Cargo {value.cargoVersion} · {value.targets?.join(', ')}</small>}
              {kind === 'r4upack' && value.sdkRevision && <small>SDK sources: {value.sdkRevision}</small>}
              {value.profileSha256 && <small>Profile SHA-256: {value.profileSha256}</small>}
              {value.sha256 && <small>{value.external || kind === 'r4upack' ? 'Binary' : kind === 'rust' ? 'Manifest' : kind === 'r4os' && installed ? 'Disk' : 'Archive'} SHA-256: {value.sha256}</small>}</div>
            {installed ? <span className="component-label">Installed</span> : <button type="button" disabled={!downloadable || busy} onClick={() => void action('download', value.id)}>{kind === 'r4upack' ? 'Build profile' : 'Download'}</button>}
          </div>;
        })}
        {loaded && !versions.length && <p className="updates-help">No versions loaded. Check for updates to retrieve the official version list.</p>}
      </div>
      {!sdkOwned && inventory?.hasMore && kind !== 'codex' && <div className="updates-actions"><button type="button" disabled={busy} onClick={() => void action('check', undefined, true)}>Load older versions</button></div>}
      {inventory?.checkedAt && <p className="updates-help">Last checked: {new Date(inventory.checkedAt).toLocaleString()}</p>}
    </div>
  </section>;
}
