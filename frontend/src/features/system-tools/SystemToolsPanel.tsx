import {useCallback, useEffect, useRef, useState} from 'react';
import type {ToolCatalogOverview, ToolCatalogSource, ToolCatalogPage, ToolCatalogRow, ToolCatalogDetail} from '../../../../shared/system-tools';
import {ProjectRequestError, studioRequest} from '../projects/api';
import './styles.css';

// One bounded read pool for this view, no timers or per-row pollers.
let active = 0;
const queue: (() => void)[] = [];
async function read<T>(path: string, signal: AbortSignal): Promise<T> {
  if (active >= 3) await new Promise<void>(resolve => queue.push(resolve));
  else active++;
  try {
    signal.throwIfAborted();
    return await studioRequest<T>('/api/settings/tools', path, '', 'GET', undefined, signal);
  } finally { const next = queue.shift(); if (next) next(); else active--; }
}
const sourcePath = (source: ToolCatalogSource) => '/' + encodeURIComponent(source.id);
const identityQuery = (source: ToolCatalogSource) => '?identity=' + source.identity;

function ToolRow({source, row, open, toggle, authLost}: {source: ToolCatalogSource; row: ToolCatalogRow; open: boolean; toggle: () => void; authLost: () => void}) {
  const [detail, setDetail] = useState<ToolCatalogDetail | null>(null), [error, setError] = useState('');
  useEffect(() => {
    if (!open || detail) return;
    const controller = new AbortController();
    void read<ToolCatalogDetail>(sourcePath(source) + '/' + row.id + identityQuery(source), controller.signal).then(value => {
      if (!controller.signal.aborted && value.source.identity === source.identity && value.tool.id === row.id) { setDetail(value); setError(''); }
    }).catch(cause => {
      if (!controller.signal.aborted) { if ((cause as ProjectRequestError).status === 403) authLost(); else setError((cause as Error).message); }
    });
    return () => controller.abort();
  }, [open, detail, source, row.id, authLost]);
  const id = 'tool-' + source.id + '-' + row.id;
  return <article className="system-tool-row">
    <button type="button" className="system-tool-toggle" aria-expanded={open} aria-controls={id} onClick={toggle}>
      <span className="system-tool-chevron" aria-hidden="true">{open ? '▾' : '▸'}</span>
      <span className="system-tool-name">{row.name}</span><span className="system-tool-origin">{source.name} · {row.scopes.join(' / ')}</span>
    </button>
    {open && <div id={id} className="system-tool-detail">
      {error ? <p role="alert">Metadata unavailable: {error}</p> : !detail ? <p role="status">Loading tool metadata…</p> : <>
        {detail.tool.title && <p>{detail.tool.title}</p>}
        <p>{detail.tool.description ?? 'Description not provided.'}</p>
        <p className="system-tool-context">{detail.tool.context}</p>
        <h3>Input parameters · original schema</h3>
        <pre>{JSON.stringify(detail.tool.inputSchema, null, 2)}</pre>
        {detail.tool.outputSchema && <><h3>Output schema</h3><pre>{JSON.stringify(detail.tool.outputSchema, null, 2)}</pre></>}
      </>}
    </div>}
  </article>;
}

function SourceRows({source, refresh, authLost}: {source: ToolCatalogSource; refresh: number; authLost: () => void}) {
  const [page, setPage] = useState<ToolCatalogPage | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(true);
  const [positions, setPositions] = useState(['0']), [opened, setOpened] = useState<Record<string, boolean>>({});
  const after = positions[positions.length - 1];
  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(async () => {
      if (controller.signal.aborted) return;
      setBusy(true); setError('');
      try {
        const value = await read<ToolCatalogPage>(sourcePath(source) + identityQuery(source) + '&after=' + after, controller.signal);
        if (!controller.signal.aborted && value.source.identity === source.identity) setPage(value);
      } catch (cause) {
        if (!controller.signal.aborted) { setPage(null); if ((cause as ProjectRequestError).status === 403) authLost(); else setError((cause as Error).message); }
      } finally { if (!controller.signal.aborted) setBusy(false); }
    });
    return () => controller.abort();
  }, [source, after, refresh, authLost]);
  const current = page?.source ?? source;
  const rows = page?.tools ?? [];
  return <section className="system-tool-source" aria-label={source.name + ' tools'}>
    <h2>{source.name}<span>{current.kind === 'mcp' ? 'Prepared MCP' : current.kind === 'native' ? 'Native' : 'Studio'}{current.count !== null ? ` · ${current.count} declared contracts` : ' · Count unknown'}</span></h2>
    {current.reason && <p className="system-tool-coverage">{current.reason}</p>}
    {current.revision !== undefined && <p className="system-tool-provenance">Skill revision {current.revision} · Runtime {current.runtimeVersion} · Source {current.sourceCommit}</p>}
    {current.capabilities?.map(capability => <p className="system-tool-coverage" key={capability.id}>{capability.id}: permission capability; callable name, description and schema not provided.</p>)}
    {error && <p role="alert">Source unavailable: {error}</p>}
    {busy && <p role="status">Loading catalog page…</p>}
    {!busy && !error && rows.length === 0 && <p role="status">{page?.complete ? 'No declared tools.' : 'Tool metadata is unavailable or incomplete.'}</p>}
    {!busy && rows.map(row => <ToolRow key={row.id} source={current} row={row} open={!!opened[row.id]} authLost={authLost}
      toggle={() => setOpened(previous => ({...previous, [row.id]: !previous[row.id]}))} />)}
    {page && rows.length > 0 && <div className="system-tool-pages">
      <span>{Number(after) + 1}–{Number(after) + rows.length} of {current.count ?? 'unknown'}{page.next ? ' · More tools available' : ' · End of declared list'}</span>
      {positions.length > 1 && <button type="button" disabled={busy} onClick={() => setPositions(previous => previous.slice(0, -1))}>Previous tools</button>}
      {page.next && <button type="button" disabled={busy} onClick={() => setPositions(previous => [...previous, page.next!])}>Next tools</button>}
    </div>}
  </section>;
}

export function SystemToolsPanel() {
  const [overview, setOverview] = useState<ToolCatalogOverview | null>(null), [error, setError] = useState(''), [refresh, setRefresh] = useState(0);
  const authEpoch = useRef(0);
  const authLost = useCallback(() => { authEpoch.current++; setOverview(null); setError('Access expired. Refresh Tools before continuing.'); }, []);
  useEffect(() => {
    const controller = new AbortController(), epoch = ++authEpoch.current;
    void read<ToolCatalogOverview>('', controller.signal).then(value => {
      if (!controller.signal.aborted && epoch === authEpoch.current) { setOverview(value); setError(''); }
    }).catch(cause => { if (!controller.signal.aborted && epoch === authEpoch.current) { setOverview(null); setError((cause as Error).message); } });
    return () => controller.abort();
  }, [refresh]);
  return <div className="system-tools-panel">
    <div className="system-tools-intro"><p>Declared tools and prepared metadata. Availability depends on the selected runtime, model and session permissions.</p>
      <button type="button" onClick={() => setRefresh(previous => previous + 1)}>Refresh tools</button></div>
    {error && <p role="alert">Tools unavailable: {error}</p>}
    {!overview && !error && <p role="status">Loading tools…</p>}
    {overview && <><p className="system-tool-coverage">{overview.reason}</p>
      {overview.sources.length === 0 && <p role="status">No catalog sources were provided.</p>}
      {overview.sources.map(source => <SourceRows key={source.id + '/' + source.identity} source={source} refresh={refresh} authLost={authLost} />)}
    </>}
  </div>;
}
