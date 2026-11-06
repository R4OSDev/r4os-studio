import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import type { VirtualMachine, VmFile } from '../../../../shared/virtual-machines';
import type { VmApi } from './useVms';
import type { VmResetControl } from './VmReset';
import { Icon } from '../../app/Icon';
import exchangePolicy from '../../../../shared/exchange-host.json';

const parent = (path: string) => path.split('/').slice(0, -1).join('/');
const leaf = (path: string) => path.split('/').at(-1) ?? path;
function size(bytes: number) {
  if (bytes < 1024) return bytes.toLocaleString() + ' B';
  const unit = bytes < 1024 ** 2 ? 1 : bytes < 1024 ** 3 ? 2 : 3;
  return (bytes / 1024 ** unit).toLocaleString(undefined, { maximumFractionDigits: 1 }) + ' ' + ['B', 'KiB', 'MiB', 'GiB'][unit];
}
function type(file: VmFile) {
  if (file.kind === 'directory') return 'Folder';
  const extension = leaf(file.name).split('.').at(-1)?.toLowerCase();
  return ({ txt: 'Text file', log: 'Log file', r4x: 'R4X app', ini: 'Settings', json: 'JSON file', png: 'PNG image', bmp: 'Bitmap image' } as Record<string, string>)[extension ?? ''] ?? 'File';
}

export function ExchangeExplorer({ api, vm, reset }: { api: VmApi; vm: VirtualMachine; reset: VmResetControl }) {
  const [path, setPath] = useState(''), [selected, setSelected] = useState('');
  const [files, setFiles] = useState<VmFile[]>([]), [error, setError] = useState('');
  const [readError, setReadError] = useState(''), [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(true);
  const apiRef = useRef(api), generation = useRef(0), life = useRef({ live: true }), uploading = useRef<HTMLInputElement>(null), mutating = useRef(false);
  const rootPending = useRef(false);
  useLayoutEffect(() => { apiRef.current = api; }, [api]);
  useEffect(() => {
    const current = { live: true }; life.current = current;
    return () => { current.live = false; };
  }, []);
  const refresh = useCallback(async (root = false) => {
    if (root) rootPending.current = true;
    const epoch = ++generation.current, lifetime = life.current;
    setLoading(true);
    try {
      const result = await apiRef.current.request<{ files: VmFile[] }>(`/${vm.id}/files`);
      if (!lifetime.live || generation.current !== epoch) return;
      const returnRoot = rootPending.current; rootPending.current = false;
      setFiles(result.files); setLoaded(true); setReadError(''); setError('');
      setPath(old => returnRoot || old && !result.files.some(file => file.kind === 'directory' && file.name === old) ? '' : old);
      setSelected(old => returnRoot || !result.files.some(file => file.name === old) ? '' : old);
    } catch (cause) { if (lifetime.live && generation.current === epoch) setReadError((cause as Error).message); }
    finally { if (lifetime.live && generation.current === epoch) setLoading(false); }
  }, [vm.id]);
  const lastReset = useRef(reset.completed);
  useEffect(() => {
    const root = lastReset.current !== reset.completed; lastReset.current = reset.completed;
    void refresh(root);
  }, [refresh, vm.state, vm.shareSync?.lastSyncedAt, reset.completed]);
  const entries = useMemo(() => files.filter(file => parent(file.name) === path).sort((a, b) =>
    Number(b.kind === 'directory') - Number(a.kind === 'directory') || a.name.localeCompare(b.name)), [files, path]);
  const folders = useMemo(() => files.filter(file => file.kind === 'directory').sort((a, b) => a.name.localeCompare(b.name)), [files]);
  const chosen = entries.find(file => file.name === selected), stopped = ['stopped', 'failed'].includes(vm.state);
  const locked = busy || reset.busy || !!reset.pending || !api.available || !stopped;
  function navigate(next: string) { setPath(next); setSelected(''); }
  async function mutate(work: () => Promise<unknown>) {
    if (locked || mutating.current) return;
    const lifetime = life.current;
    mutating.current = true; setBusy(true); setError('');
    try { await work(); if (lifetime.live) { await apiRef.current.reload(); await refresh(); } }
    catch (cause) { if (lifetime.live) setError((cause as Error).message); }
    finally { mutating.current = false; if (lifetime.live) setBusy(false); }
  }
  function keyboard(event: KeyboardEvent<HTMLTableRowElement>, file: VmFile, index: number) {
    if (event.target !== event.currentTarget) return;
    const direction = event.key === 'ArrowDown' ? 1 : event.key === 'ArrowUp' ? -1 : 0;
    if (direction || event.key === 'Home' || event.key === 'End') {
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? entries.length - 1 : Math.max(0, Math.min(entries.length - 1, index + direction));
      setSelected(entries[next].name);
      event.currentTarget.parentElement?.querySelectorAll<HTMLTableRowElement>('tr')[next]?.focus();
    } else if (event.key === 'Enter' && file.kind === 'directory') { event.preventDefault(); navigate(file.name); }
    else if (event.key === ' ') { event.preventDefault(); setSelected(file.name); }
  }
  const crumbs = path ? path.split('/') : [];
  return <section className="exchange-explorer" aria-label="Exchange file manager">
    <header className="exchange-heading"><Icon name="box" /><div><h2>Exchange</h2><p>{vm.name} · R4SHARE</p></div><span className={`vm-status ${vm.state}`}>{vm.state}</span></header>
    <div className="exchange-manager">
      <div className="exchange-toolbar" aria-label="Exchange actions">
        <button type="button" className="button-primary" disabled={locked} onClick={() => uploading.current?.click()}><Icon name="attachment" />Upload file</button>
        <input ref={uploading} hidden type="file" aria-label="Upload exchange file" disabled={locked} onChange={event => {
          const file = event.target.files?.[0]; event.target.value = ''; if (!file) return;
          void mutate(async () => {
            if (file.size > 8 * 1024 ** 2) throw new Error('Files are limited to 8 MiB per upload.');
            const bytes = new Uint8Array(await file.arrayBuffer()); let binary = '';
            for (let offset = 0; offset < bytes.length; offset += 8192) binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
            await apiRef.current.request(`/${vm.id}/files`, 'POST', { name: path ? path + '/' + file.name : file.name, content: btoa(binary) });
          });
        }} />
        <button type="button" className="button-secondary" disabled={locked || !chosen} onClick={() => {
          if (chosen) void mutate(() => apiRef.current.request(`/${vm.id}/files/${encodeURIComponent(chosen.name)}`, 'DELETE'));
        }}><Icon name="stop" />Remove</button>
        <button type="button" className="button-danger exchange-empty" disabled={locked} onClick={() => reset.open('exchange')}><Icon name="folder" />Empty Exchange</button>
      </div>
      <div className="exchange-address">
        <button type="button" className="button-secondary exchange-up" disabled={!path} onClick={() => navigate(parent(path))} aria-label="Up one folder">↑</button>
        <nav aria-label="Exchange path"><Icon name="box" /><button type="button" onClick={() => navigate('')} aria-current={!path ? 'location' : undefined}>Exchange</button>
          {crumbs.map((part, index) => <span key={index}><Icon name="chevron" /><button type="button" aria-current={index === crumbs.length - 1 ? 'location' : undefined} onClick={() => navigate(crumbs.slice(0, index + 1).join('/'))}>{part}</button></span>)}</nav>
        <button type="button" className="button-secondary" aria-label="Refresh exchange files" disabled={loading || busy || reset.busy} onClick={() => void refresh()}><Icon name="restart" /></button>
      </div>
      <div className="exchange-body">
        <nav className="exchange-tree" aria-label="Exchange folders"><p>Folders</p>
          <button type="button" aria-current={!path ? 'location' : undefined} onClick={() => navigate('')}><Icon name="box" />Exchange</button>
          {folders.map(file => <button type="button" key={file.name} title={file.name} style={{ paddingLeft: 12 + file.name.split('/').length * 10 }} aria-current={path === file.name ? 'location' : undefined} onClick={() => navigate(file.name)}><Icon name="folder" /><span>{leaf(file.name)}</span></button>)}</nav>
        <div className="exchange-table-wrap" aria-busy={loading}>
          <table role="grid" aria-label="Exchange files" className="exchange-files"><thead><tr><th>Name</th><th>Type</th><th>Size</th></tr></thead>
            <tbody>{entries.map((file, index) => <tr key={file.name} aria-selected={selected === file.name} tabIndex={selected === file.name || !chosen && index === 0 ? 0 : -1}
              onFocus={event => { if (event.target === event.currentTarget) setSelected(file.name); }} onClick={() => setSelected(file.name)}
              onDoubleClick={() => { if (file.kind === 'directory') navigate(file.name); }} onKeyDown={event => keyboard(event, file, index)}>
              <td><button type="button" tabIndex={-1} className="exchange-file-name" aria-label={(file.kind === 'directory' ? 'Open folder ' : 'Select ') + leaf(file.name)} onClick={event => {
                event.stopPropagation(); if (file.kind === 'directory') navigate(file.name); else {setSelected(file.name);event.currentTarget.closest('tr')?.focus();}
              }}><Icon name={file.kind === 'directory' ? 'folder' : type(file).endsWith('image') ? 'image' : file.name.endsWith('.r4x') ? 'box' : 'note'} /><span>{leaf(file.name)}</span></button></td>
              <td>{type(file)}</td><td>{file.kind === 'directory' ? '—' : size(file.size)}</td>
            </tr>)}</tbody></table>
          {!entries.length && <div className="exchange-empty-state"><Icon name="folder" /><p>{loading ? 'Reading host copy…' : readError ? 'Host files could not be read.' : 'This folder is empty.'}</p></div>}
        </div>
      </div>
      <footer className="exchange-status" role="status"><span>{loaded ? <>{readError ? 'Last confirmed copy · ' : ''}{entries.length} {entries.length === 1 ? 'item' : 'items'} · {size(entries.reduce((sum, file) => sum + (file.kind === 'directory' ? 0 : file.size), 0))}</> : 'Inventory unavailable'}{loading ? ' · Reading…' : ''}</span><span>{chosen ? leaf(chosen.name) + ' selected' : 'Nothing selected'}</span></footer>
    </div>
    {(error || readError) && <p className="vm-alert" role="alert">{error || readError}</p>}
    <div className="exchange-sync"><span>{vm.shareSync?.pending ? stopped ? 'Guest changes need synchronization.' : 'Last host copy · guest changes pending.' : 'Last host copy'}{vm.shareSync?.lastSyncedAt ? ' · Last synchronized ' + new Date(vm.shareSync.lastSyncedAt).toLocaleString() : ''}</span>
      {stopped && vm.shareSync?.pending && <button type="button" className="button-secondary" disabled={locked} onClick={() => void mutate(() => apiRef.current.request(`/${vm.id}/actions`, 'POST', { action: 'sync-exchange' }))}>Retry exchange sync</button>}
      <details><summary>Details</summary><p>Guest changes are copied here after the VM stops. Host changes apply at the next VM start. The guest assigns the Exchange drive letter.</p>
        <code>{vm.sharePath}</code><p>Root files and Build subfolders only. ASCII names; no links. Uploads up to 8 MiB. Up to {exchangePolicy.limits.files} files, {exchangePolicy.limits.bytes / 1024 ** 3} GiB, {exchangePolicy.limits.directories} folders and {exchangePolicy.limits.depth} levels, including reserved metadata. STXCHG.JSN is managed by Studio. Remove folders after emptying them.</p></details>
    </div>
    {vm.shareSync?.error && <p className="vm-alert" role="alert">{vm.shareSync.error}</p>}
    {!stopped && <p className="vm-help">Stop the VM and wait for synchronization before changing Exchange files.</p>}
  </section>;
}
