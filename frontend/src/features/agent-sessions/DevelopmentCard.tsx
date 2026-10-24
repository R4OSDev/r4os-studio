import { useEffect, useRef, useState } from 'react';
import type { DevelopmentEvidence, DevelopmentJob, DevelopmentJobPage } from '../../../../shared/project-development';
import { busyRun, projectRequest, projectRequestId } from './api';
import { CodeBlock } from './Transcript';
const uuid = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;
export function developmentRef(value: unknown): { jobId: string } | null {
  if (!value || typeof value !== 'object') return null;
  const jobId = (value as { jobId?: unknown }).jobId;
  return typeof jobId === 'string' && uuid.test(jobId) ? { jobId } : null;
}
export function DevelopmentImage({ projectId, value }: { projectId: string; value: unknown }) {
  if (!value || typeof value !== 'object') return null;
  const image = value as DevelopmentEvidence & { jobId?: string };
  if (image.kind !== 'screenshot' || !uuid.test(image.id) || !image.jobId || !uuid.test(image.jobId)) return null;
  const path = `/api/projects/${projectId}/development/jobs/${image.jobId}/evidence/${image.id}`;
  return <figure className="development-image"><a href={path} target="_blank" rel="noopener noreferrer"><img src={path} loading="lazy" alt="Assigned VM screenshot" width={image.width} height={image.height} /></a><figcaption>{new Date(image.createdAt).toLocaleString()} · {image.width} × {image.height}</figcaption></figure>;
}
export function DevelopmentCard({ projectId, jobId, token }: { projectId: string; jobId: string; token: string }) {
  const [job, setJob] = useState<DevelopmentJob | null>(null), [error, setError] = useState(''), [stopping, setStopping] = useState(false);
  const [open, setOpen] = useState(false), [output, setOutput] = useState(''), [more, setMore] = useState(false), [loading, setLoading] = useState(false);
  const cursor = useRef(0), [kind, setKind] = useState('Output'), [truncated, setTruncated] = useState(false);
  const recoveryId = useRef<string | null>(null);
  const path = `/${projectId}/development/jobs/${jobId}`;
  useEffect(() => {
    const controller = new AbortController(); let timer: number | undefined;
    const refresh = async () => {
      try {
        const page = await projectRequest<DevelopmentJobPage>(path + '?offset=0', '', 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return; setJob(page.job); setError('');
        if (busyRun(page.job.state)) timer = window.setTimeout(() => void refresh(), 2000);
      } catch (e) { if (!controller.signal.aborted) { setError((e as Error).message); timer = window.setTimeout(() => void refresh(), 4000); } }
    };
    void refresh(); return () => { controller.abort(); window.clearTimeout(timer); };
  }, [path]);
  async function readOutput() {
    if (loading) return; setLoading(true);
    try {
      const page = await projectRequest<DevelopmentJobPage>(path + '?offset=' + cursor.current);
      setJob(page.job); setOutput((old) => old + page.output); setKind(page.outputKind === 'console' ? 'Console output' : page.outputKind === 'diagnostic' ? 'Diagnostic output' : 'Build output');
      setMore(page.nextOffset > cursor.current || busyRun(page.job.state)); cursor.current = page.nextOffset; setTruncated(page.truncated); setError('');
    } catch (e) { setError((e as Error).message); } finally { setLoading(false); }
  }
  async function stop() {
    setStopping(true);
    try { const r = await projectRequest<{ job: DevelopmentJob }>(path + '/stop', token, 'POST'); setJob(r.job); setError(''); }
    catch (e) { setError((e as Error).message); } finally { setStopping(false); }
  }
  async function reconcile() {
    setStopping(true); recoveryId.current ??= projectRequestId();
    try { const r = await projectRequest<{ job: DevelopmentJob }>(path + '/reconcile', token, 'POST', { requestId: recoveryId.current }); setJob(r.job); recoveryId.current = null; setError(''); }
    catch (e) { setError((e as Error).message); } finally { setStopping(false); }
  }
  return <section className="development-card" aria-label="Development job">
    <div className="development-card-header"><strong>{job?.kind === 'vm_start' ? 'Start VM' : job?.kind === 'execution' ? 'Run' : job?.kind === 'deploy' ? 'Deploy' : 'Build'}</strong><span role="status">{job?.state ?? 'Loading'}</span>{job && busyRun(job.state) && <button type="button" disabled={stopping} onClick={() => void stop()}>{stopping ? 'Stopping…' : 'Stop job'}</button>}</div>
    {job && <><p className="development-phase">{job.phase.replaceAll('_', ' ')}</p>{job.check && <p>Checks: {job.check.state}{job.check.assessment ? ` · ${job.check.assessment}` : ''}</p>}
      {job.check?.findings.map((text, i) => <p key={i}>{text}</p>)}{job.error && <p className="agent-error">{job.error}</p>}</>}
    {job?.vmStart?.ready && <p>SSH ready · R4OS {job.vmStart.guestRelease}{job.vmStart.checkedAt ? ` · ${new Date(job.vmStart.checkedAt).toLocaleString()}` : ''}</p>}
    {job?.state === 'unknown' && !job.guestState?.closeConfirmed && <button type="button" disabled={stopping} onClick={() => void reconcile()}>{stopping ? 'Reconciling…' : 'Reconcile receipts'}</button>}
    {job?.state === 'unknown' && job.guestState?.closeConfirmed && <p>Process end confirmed. Exit status unavailable.</p>}
    {job?.recovery?.reason && <p>{job.recovery.reason}</p>}
    <button type="button" aria-expanded={open} onClick={() => { setOpen(!open); if (!open && !output) void readOutput(); }}>{open ? 'Hide details' : 'Show details'}</button>
    {open && <><CodeBlock text={output} label="Copy job output" language={kind} />{truncated && <p>Output limit reached.</p>}{(more || !!job && busyRun(job.state)) && <button type="button" disabled={loading} onClick={() => void readOutput()}>{loading ? 'Loading…' : 'Load more output'}</button>}</>}
    {error && <p className="agent-error" role="alert">{error}</p>}
  </section>;
}
