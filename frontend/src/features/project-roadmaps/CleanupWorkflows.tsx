import { useCallback, useEffect, useRef, useState } from 'react';
import type { RoadmapWorkflow, RoadmapWorkflowPage, RoadmapWorkflowSummary } from '../../../../shared/project-roadmaps';
import { roadmapRequest } from './api';
import { workflowLabels } from './workflow';

const formattedTime = (value: string) => Number.isNaN(Date.parse(value)) ? value
  : new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });

function Workflow({ id, entry }: { id: string; entry: RoadmapWorkflowSummary }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<{ key: string; value?: RoadmapWorkflow; error?: string }>({ key: '' });
  const key = entry.workflowId + ':' + entry.updatedAt;
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void roadmapRequest<RoadmapWorkflow>(id, '/workflows/' + entry.workflowId, '', 'GET', undefined, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setState({ key, value }); })
      .catch((error: Error) => { if (!controller.signal.aborted) setState({ key, error: error.message }); });
    return () => controller.abort();
  }, [id, entry.workflowId, open, key]);
  const current = state.key === key ? state : null, value = state.value;
  return <details className="roadmap-cleanup-entry" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary><strong>{entry.number}</strong><span>{Object.hasOwn(workflowLabels, entry.phase) ? workflowLabels[entry.phase] : entry.phase}</span>
      {entry.nextNumber && <small>Next: {entry.nextNumber}</small>}</summary>
    {open && <div className="roadmap-cleanup-body">
      {!current && <p role="status">{value ? 'Refreshing cleanup receipt…' : 'Loading cleanup receipt…'}</p>}
      {current?.error && <p role="alert" className="project-error">{current.error}</p>}
      {value && <>
        <dl><div><dt>Workflow</dt><dd>{value.workflowId}</dd></div>
          <div><dt>Snapshot revision</dt><dd>{value.sourceBinding.revision}</dd></div>
          <div><dt>Updated</dt><dd>{formattedTime(value.updatedAt)}</dd></div>
          {value.nextNumber && <div><dt>Next empty version</dt><dd>{value.nextNumber}</dd></div>}</dl>
        {value.archive ? <div><p>Archive: <code>{value.archive.path}</code> · {value.archive.byteLength.toLocaleString()} bytes · UTF-8</p>
          <p>SHA-256: <code>{value.archive.sha256}</code></p>
          <a download href={`/api/projects/${id}/roadmap/exports/${value.archive.exportId}/content`}>Download prepared snapshot</a></div>
          : <p>The archive has not been confirmed yet. Inspect the original workflow before retrying.</p>}
        <p>{value.documentCount} knowledge document{value.documentCount === 1 ? '' : 's'} confirmed.</p>
        {value.documentationSummary && <p className="roadmap-cleanup-summary">{value.documentationSummary}</p>}
        {value.documents.length > 0 && <ul>{value.documents.map((document) => <li key={document.path}><code>{document.path}</code><br /><code>{document.sha256}</code></li>)}</ul>}
        <p className="roadmap-shared-note">These receipts record verified steps. Finalization checks the files again. Use the original workflow to reconcile an interruption; document changes are preserved.</p>
      </>}
    </div>}
  </details>;
}

export function CleanupWorkflows({ id, versionId }: { id: string; versionId?: string }) {
  const [page, setPage] = useState<RoadmapWorkflowPage | null>(null), [error, setError] = useState('');
  const [busy, setBusy] = useState(false), [history, setHistory] = useState(false);
  const mounted = useRef(true), sequence = useRef(0), active = useRef(false), controller = useRef<AbortController | null>(null);
  const load = useCallback(async (cursor?: string) => {
    if (active.current) return;
    active.current = true; const current = ++sequence.current;
    const pending = new AbortController(); controller.current = pending; setBusy(true);
    const query = new URLSearchParams(); if (versionId) query.set('versionId', versionId); if (cursor) query.set('cursor', cursor);
    try {
      const result = await roadmapRequest<RoadmapWorkflowPage>(id, '/workflows?' + query.toString(), '', 'GET', undefined, pending.signal);
      if (!mounted.current || current !== sequence.current || pending.signal.aborted) return;
      setPage((old) => cursor && old ? { ...result, items: [...old.items, ...result.items] } : result);
      setError(''); setHistory(!!cursor);
    } catch (failure) {
      if (mounted.current && current === sequence.current && !pending.signal.aborted) setError((failure as Error).message);
    } finally {
      if (current === sequence.current) { active.current = false; if (mounted.current) setBusy(false); }
    }
  }, [id, versionId]);
  const cancel = useCallback(() => { mounted.current = false; sequence.current++; active.current = false; controller.current?.abort(); }, []);
  useEffect(() => {
    mounted.current = true;
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => { window.clearTimeout(timer); cancel(); };
  }, [load, cancel]);
  useEffect(() => {
    if (history) return;
    const interval = window.setInterval(() => { if (document.visibilityState === 'visible') void load(); }, 5000);
    return () => window.clearInterval(interval);
  }, [load, history]);
  return <section className="roadmap-card roadmap-cleanup" aria-label="Cleanup workflows">
    <div className="roadmap-collection-heading"><h3>Cleanup history</h3>
      <button type="button" disabled={busy} onClick={() => void load()}>Refresh cleanup history</button></div>
    {error && <p role="alert" className="project-error">{error}</p>}
    {!page && !error && <p role="status">Loading cleanup history…</p>}
    {page && page.items.length === 0 && <p>No cleanup workflows for this view.</p>}
    {page?.items.map((entry) => <Workflow key={entry.workflowId} id={id} entry={entry} />)}
    {history && <p className="roadmap-shared-note">Showing workflow history. Refresh for the latest state.</p>}
    {page?.nextCursor && <button type="button" disabled={busy} onClick={() => void load(page.nextCursor!)}>More cleanup workflows</button>}
  </section>;
}
