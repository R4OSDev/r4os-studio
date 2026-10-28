import { useCallback, useEffect, useRef, useState } from 'react';
import type { RemoteHost, RemoteJobSummary, RemoteJobDetail, RemoteReviewInput, RemoteReviewReceipt } from '../../../../shared/remote-hosts';
import type { RemoteHostsApi } from './useRemoteHosts';
import { getHostJob, getHostReview, hostCapabilities, listHostJobs, RemoteHostRequestError } from './api';
import { projectRequestId } from '../projects/api';
import { CodeBlock } from '../agent-sessions/Transcript';

type Pending = { projectId: string; jobId: string; input: RemoteReviewInput };
const keyFor = (id: string) => 'studio.remote-review.' + id;
function savedPending(id: string): Pending | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(keyFor(id)) ?? 'null') as Pending | null;
    if (!value || ![value.projectId, value.jobId, value.input?.requestId].every((text) => typeof text === 'string' && /^[a-f0-9-]{36}$/.test(text))
      || value.input.confirmUnknown !== true || typeof value.input.expectedUpdatedAt !== 'string') return null;
    return value;
  } catch { return null; }
}

export function HostJobs({ host, api }: { host: RemoteHost; api: RemoteHostsApi }) {
  const [jobs, setJobs] = useState<RemoteJobSummary[]>([]), [detail, setDetail] = useState<RemoteJobDetail | null>(null);
  const [supported, setSupported] = useState(false), [truncated, setTruncated] = useState(false), [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Pending | null>(() => savedPending(host.id));
  const initial = useRef(pending), mounted = useRef(true), listGeneration = useRef(0), detailGeneration = useRef(0), detailRequest = useRef<AbortController | null>(null);
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; detailRequest.current?.abort(); }; }, []);
  const refresh = useCallback((signal?: AbortSignal) => {
    const generation = ++listGeneration.current;
    return hostCapabilities(signal).then(async (caps) => {
      if (!mounted.current || signal?.aborted || generation !== listGeneration.current) return;
      setSupported(caps.lifecycle === 1);
      if (caps.lifecycle !== 1) return;
      const value = await listHostJobs(host.id, signal);
      if (mounted.current && !signal?.aborted && generation === listGeneration.current) { setJobs(value.jobs); setTruncated(value.truncated); setError(''); }
    }).catch((cause: Error) => { if (mounted.current && !signal?.aborted && generation === listGeneration.current) setError(cause.message); });
  }, [host.id]);
  const inspect = useCallback(async (projectId: string, jobId: string) => {
    detailRequest.current?.abort(); const controller = new AbortController(); detailRequest.current = controller; const generation = ++detailGeneration.current;
    try {
      const value = await getHostJob(host.id, projectId, jobId, controller.signal);
      if (mounted.current && !controller.signal.aborted && generation === detailGeneration.current) { setDetail(value); setError(''); }
    } catch (cause) { if (mounted.current && !controller.signal.aborted && generation === detailGeneration.current) setError((cause as Error).message); }
  }, [host.id]);
  const confirmed = useCallback((value: Pending, receipt: RemoteReviewReceipt) => {
    if (receipt.jobId !== value.jobId || receipt.projectId !== value.projectId || receipt.requestId !== value.input.requestId) throw new Error('The original review receipt changed.');
    try { sessionStorage.removeItem(keyFor(host.id)); } catch { /* Reload can read the same confirmed receipt again. */ }
    if (!mounted.current) return;
    setPending(null); setNotice('Acknowledgement saved. The original result is still unknown.');
    void refresh(); void inspect(value.projectId, value.jobId);
  }, [host.id, inspect, refresh]);
  useEffect(() => {
    const controller = new AbortController(); void refresh(controller.signal);
    const value = initial.current;
    if (value) void getHostReview(host.id, value.projectId, value.jobId, value.input.requestId, controller.signal)
      .then((receipt) => { if (!controller.signal.aborted) confirmed(value, receipt); })
      .catch((cause: Error) => { if (!controller.signal.aborted && mounted.current) setError(cause.message + ' Inspect the original acknowledgement; no new request was sent.'); });
    return () => controller.abort();
  }, [host.id, refresh, confirmed]);
  async function execute(value: Pending) {
    if (busy || !api.ready) return;
    try { sessionStorage.setItem(keyFor(host.id), JSON.stringify(value)); }
    catch { setError('The original acknowledgement could not be retained. No request was sent.'); return; }
    setPending(value); setBusy(true); setError(''); setNotice('');
    try { confirmed(value, await api.review(host.id, value.projectId, value.jobId, value.input)); }
    catch (cause) {
      const failure = cause as RemoteHostRequestError;
      if (failure.status >= 400 && failure.status < 500) {
        try { sessionStorage.removeItem(keyFor(host.id)); } catch { /* Only a later original read is possible after reload. */ }
        if (mounted.current) setPending(null);
      }
      if (mounted.current) setError(failure.message);
    } finally { if (mounted.current) setBusy(false); }
  }
  async function recover(value: Pending) {
    if (busy) return; setBusy(true); setError('');
    try { confirmed(value, await getHostReview(host.id, value.projectId, value.jobId, value.input.requestId)); }
    catch (cause) { if (mounted.current) setError((cause as Error).message + ' Retry only the same acknowledgement if it was not recorded.'); }
    finally { if (mounted.current) setBusy(false); }
  }
  function acknowledge() {
    if (!detail || detail.state !== 'unknown' || pending || busy) return;
    if (!window.confirm(`Acknowledge uncertainty for original job ${detail.id} on ${detail.hostName}? This permits new work. The command result and remote process end remain unknown; no remote action is performed.`)) return;
    void execute({ projectId: detail.projectId, jobId: detail.id, input: { requestId: projectRequestId(), expectedUpdatedAt: detail.updatedAt, confirmUnknown: true } });
  }
  return <section className="remote-jobs" aria-label="Remote jobs"><h3>Remote jobs</h3>
    <p>Original jobs across linked projects. Reading these receipts does not connect to the remote computer.</p>
    {!supported ? <p role="status">Job review needs the latest idle Remote Host broker.</p> : <>
      <button type="button" disabled={busy} onClick={() => void refresh()}>Refresh jobs</button>
      {!jobs.length && <p>No saved jobs for this host.</p>}
      <ul>{jobs.map((job) => <li key={job.id}><button type="button" disabled={busy} onClick={() => void inspect(job.projectId, job.id)} aria-label={`Inspect remote job ${job.id}`}>
        <span>{job.projectName} · {job.action ?? job.commandPreview ?? job.operation}</span><span>{job.state === 'unknown_reviewed' ? 'Unknown · Reviewed' : job.state}</span>
      </button></li>)}</ul>
      {truncated && <p>Showing the latest bounded job history. Older original receipts remain in their projects.</p>}
      {detail && <section aria-label="Original remote job"><h4>Original job</h4>
        <CodeBlock text={JSON.stringify(detail, null, 2)} label="Copy original remote job" />
        {detail.state === 'unknown' && <><p>Inspect the original effect and finish current project agent runs before acknowledging uncertainty. The saved result stays unknown. Acknowledgement permits new work and target changes; it does not repeat, undo or stop remote work.</p><button type="button" disabled={busy || !!pending || !api.ready} onClick={acknowledge}>Acknowledge uncertainty</button></>}
        {detail.state === 'unknown_reviewed' && <p>Uncertainty acknowledged. The original outcome and remote process end remain unconfirmed.</p>}
      </section>}
    </>}
    {pending && <div role="status"><p>Original acknowledgement {pending.input.requestId} is retained.</p><button type="button" disabled={busy} onClick={() => void recover(pending)}>Check acknowledgement receipt</button><button type="button" disabled={busy || !supported} onClick={() => void execute(pending)}>Retry same acknowledgement</button><button type="button" disabled={busy} onClick={() => {
      if (!window.confirm('Dismiss this browser’s request reminder? The saved job and any original acknowledgement remain unchanged. No result is confirmed and no remote work is repeated.')) return;
      try { sessionStorage.removeItem(keyFor(host.id)); setPending(null); setNotice('Local reminder dismissed. Original job history is unchanged.'); }
      catch { setError('The local request reminder could not be removed.'); }
    }}>Dismiss local reminder</button></div>}
    {notice && <p role="status">{notice}</p>}{error && <p className="remote-error" role="alert">{error}</p>}
  </section>;
}
