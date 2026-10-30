import { useEffect, useRef, useState } from 'react';
import type { RoadmapBinding, RoadmapExport, RoadmapExportInput } from '../../../../shared/project-roadmaps';
import { Icon } from '../../app/Icon';
import { ProjectRequestError, projectRequestId } from '../projects/api';
import { roadmapRequest } from './api';

type Props = {
  id: string; versionId: string; token: string; binding: RoadmapBinding; disabled: boolean;
  busyChanged: (value: boolean) => void;
};
type Confirmed = { input: RoadmapExportInput; metadata: RoadmapExport };
type Recovery = { schema: 2; pending: RoadmapExportInput | null; confirmed: Confirmed | null };
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const recoveryError = 'The original export needs reconciliation. Browser data was preserved.';

function checkInput(input: RoadmapExportInput, versionId: string) {
  if (!input || input.versionId !== versionId || !uuid.test(input.requestId)
    || !uuid.test(input.currentVersionId) || !Number.isSafeInteger(input.expectedRevision) || input.expectedRevision < 1) {
    throw new Error(recoveryError);
  }
}
function checkExport(value: RoadmapExport, input: RoadmapExportInput, projectId: string) {
  if (!value || value.id !== input.requestId || value.projectId !== projectId || value.versionId !== input.versionId
    || value.revision !== input.expectedRevision || value.currentVersionId !== input.currentVersionId
    || !uuid.test(value.roadmapId) || !/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.X$/.test(value.number)
    || value.filename !== value.number + '.txt' || value.encoding !== 'utf-8'
    || !/^[a-f0-9]{64}$/.test(value.sha256) || !Number.isSafeInteger(value.byteLength) || value.byteLength < 1) {
    throw new Error(recoveryError);
  }
}
function restore(key: string, id: string, versionId: string): Recovery {
  const raw = sessionStorage.getItem(key);
  if (!raw) return { schema: 2, pending: null, confirmed: null };
  const parsed = JSON.parse(raw);
  // Retain requests saved by the previous text button, without issuing a request on mount.
  const value: Recovery = parsed.schema === 2 ? parsed : { schema: 2, pending: parsed, confirmed: null };
  if (value.pending) checkInput(value.pending, versionId);
  if (value.confirmed) {
    checkInput(value.confirmed.input, versionId);
    checkExport(value.confirmed.metadata, value.confirmed.input, id);
  }
  if (!value.pending && !value.confirmed) throw new Error(recoveryError);
  return value;
}

export function ExportVersion(props: Props) {
  return <ExportControl key={`${props.id}:${props.versionId}`} {...props} />;
}
function ExportControl({ id, versionId, token, binding, disabled, busyChanged }: Props) {
  const key = `studio.roadmap.export.${id}.${versionId}`;
  const [initial] = useState(() => {
    try { return { value: restore(key, id, versionId), error: '' }; }
    catch { return { value: { schema: 2 as const, pending: null, confirmed: null }, error: recoveryError }; }
  });
  const [recovery, setRecovery] = useState(initial.value);
  const [busy, setBusy] = useState(false), [error, setError] = useState(initial.error);
  const live = useRef(false), inFlight = useRef(false), controller = useRef<AbortController | null>(null);
  useEffect(() => { live.current = true; return () => { live.current = false; controller.current?.abort(); }; }, []);
  useEffect(() => { busyChanged(busy); return () => busyChanged(false); }, [busy, busyChanged]);

  const sameSnapshot = recovery.confirmed?.input.expectedRevision === binding.revision
    && recovery.confirmed.input.currentVersionId === binding.currentVersionId;
  const label = busy ? 'Preparing export…' : recovery.pending ? 'Resume original export'
    : sameSnapshot ? 'Download saved version again' : 'Export saved version';
  async function prepare() {
    if (disabled || inFlight.current || initial.error) return;
    inFlight.current = true; setBusy(true); setError('');
    const input = recovery.pending ?? (sameSnapshot ? recovery.confirmed!.input : {
      requestId: projectRequestId(), versionId, expectedRevision: binding.revision, currentVersionId: binding.currentVersionId,
    });
    try {
      // Hold the synchronous latch even for an already confirmed download.
      await Promise.resolve();
      let confirmed = !recovery.pending && sameSnapshot ? recovery.confirmed : null;
      if (!confirmed) {
        const pending: Recovery = { ...recovery, pending: input };
        sessionStorage.setItem(key, JSON.stringify(pending)); setRecovery(pending);
        controller.current = new AbortController();
        const metadata = await roadmapRequest<RoadmapExport>(id, '/exports', token, 'POST', input, controller.current.signal);
        checkExport(metadata, input, id);
        confirmed = { input, metadata };
        // A late response must never replace a newer request in a remounted view.
        const stored = restore(key, id, versionId);
        if (stored.pending?.requestId !== input.requestId) return;
        const ready: Recovery = { schema: 2, pending: null, confirmed };
        sessionStorage.setItem(key, JSON.stringify(ready));
        if (live.current) setRecovery(ready);
      }
      if (!live.current) return;
      const link = document.createElement('a');
      link.href = `/api/projects/${id}/roadmap/exports/${confirmed.metadata.id}/content`;
      link.download = confirmed.metadata.filename; document.body.append(link);
      try { link.click(); } finally { link.remove(); }
      // The browser owns saving the file; a click is not a completed-download receipt.
    } catch (cause) {
      if (!live.current) return;
      const failure = cause as ProjectRequestError;
      // These rejections cannot have prepared an export. Unknown/temporary results retain the original input.
      if ([400, 404, 410, 413, 422].includes(failure.status)) {
        try {
          const stored = restore(key, id, versionId);
          if (stored.pending?.requestId === input.requestId) {
            const cleared: Recovery = { ...stored, pending: null };
            if (cleared.confirmed) sessionStorage.setItem(key, JSON.stringify(cleared)); else sessionStorage.removeItem(key);
            setRecovery(cleared);
          }
        } catch { /* Preserve original browser data if reconciliation is unavailable. */ }
      }
      setError(failure.message || 'The export could not be confirmed. Use the icon to resume the original request.');
    } finally {
      inFlight.current = false; controller.current = null;
      if (live.current) setBusy(false);
    }
  }
  return <div className="roadmap-export">
    <button type="button" className={`roadmap-export-icon${busy ? ' is-busy' : ''}`}
      aria-label={label} title={label} aria-busy={busy} disabled={disabled || busy || !!initial.error}
      onClick={event => { if (event.detail < 2) void prepare(); }}><Icon name="download" /></button>
    {error && <p className="project-error" role="alert">{error}</p>}
  </div>;
}
