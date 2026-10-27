import { useEffect, useState } from 'react';
import type { RoadmapBinding, RoadmapExport, RoadmapExportInput } from '../../../../shared/project-roadmaps';
import { ProjectRequestError, projectRequestId } from '../projects/api';
import { roadmapRequest } from './api';

export function ExportVersion({ id, versionId, token, binding, disabled, busyChanged }: {
  id: string; versionId: string; token: string; binding: RoadmapBinding; disabled: boolean;
  busyChanged: (value: boolean) => void;
}) {
  const key = `studio.roadmap.export.${id}.${versionId}`;
  const [recovery] = useState(() => {
    try {
      const stored = sessionStorage.getItem(key);
      const value = stored ? JSON.parse(stored) as RoadmapExportInput : null;
      if (value && (value.versionId !== versionId || typeof value.requestId !== 'string'
        || typeof value.currentVersionId !== 'string' || !Number.isSafeInteger(value.expectedRevision))) {
        throw new Error('The original export request needs reconciliation. Browser data was preserved.');
      }
      return { request: value, error: '' };
    } catch (cause) { return { request: null, error: (cause as Error).message }; }
  });
  const [pending, setPending] = useState(recovery.request);
  const [saved, setSaved] = useState<RoadmapExport | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(recovery.error);
  useEffect(() => { busyChanged(busy); return () => busyChanged(false); }, [busy, busyChanged]);
  async function prepare() {
    if (disabled || busy || recovery.error) return;
    const body = pending ?? { requestId: projectRequestId(), versionId,
      expectedRevision: binding.revision, currentVersionId: binding.currentVersionId };
    try { sessionStorage.setItem(key, JSON.stringify(body)); }
    catch { setError('The browser could not retain the export request. Enable session storage before continuing.'); return; }
    setPending(body); setBusy(true); setError('');
    try {
      const value = await roadmapRequest<RoadmapExport>(id, '/exports', token, 'POST', body);
      sessionStorage.removeItem(key); setPending(null); setSaved(value);
      const link = document.createElement('a');
      link.href = `/api/projects/${id}/roadmap/exports/${value.id}/content`;
      link.download = value.filename; document.body.append(link); link.click(); link.remove();
    } catch (cause) {
      const failure = cause as ProjectRequestError;
      if (failure.status >= 400 && failure.status < 500) { sessionStorage.removeItem(key); setPending(null); }
      setError(failure.message || 'The export result could not be confirmed. Confirm the original request.');
    } finally { setBusy(false); }
  }
  return <div className="roadmap-export">
    <button type="button" disabled={disabled || busy || !!recovery.error} onClick={() => void prepare()}>
      {busy ? 'Preparing export…' : pending ? 'Confirm original export' : 'Export saved version'}
    </button>
    {error && <p className="project-error" role="alert">{error}</p>}
    {saved && <div className="roadmap-export-result"><a href={`/api/projects/${id}/roadmap/exports/${saved.id}/content`} download={saved.filename}>Download {saved.filename}</a>
      <details><summary>Export details</summary><dl>
        <div><dt>Saved revision</dt><dd>{saved.revision}</dd></div>
        <div><dt>Version ID</dt><dd>{saved.versionId}</dd></div>
        <div><dt>Encoding / bytes</dt><dd>UTF-8 / {saved.byteLength}</dd></div>
        <div><dt>SHA-256</dt><dd><code>{saved.sha256}</code></dd></div>
      </dl></details></div>}
  </div>;
}
