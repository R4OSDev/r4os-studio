import { useEffect, useRef, useState } from 'react';
import type { DevelopmentEvidence, DevelopmentExecutionEvidence, DevelopmentJob, DevelopmentJobPage } from '../../../../shared/project-development';
import { busyRun, projectRequest, projectRequestId } from './api';
import { CodeBlock } from './Transcript';
import { UpdateRecord } from '../projects/UpdateRecord';
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
  return <figure className="development-image"><a href={path} target="_blank" rel="noopener noreferrer"><img src={path} loading="lazy" alt="Assigned VM screenshot" width={image.width} height={image.height} /></a><figcaption>{image.diagnosticOnly ? 'Diagnostic only · Desktop content unconfirmed · ' : ''}{new Date(image.createdAt).toLocaleString()} · {image.width} × {image.height}</figcaption></figure>;
}
export function DevelopmentCard({ projectId, jobId, token }: { projectId: string; jobId: string; token: string }) {
  const [job, setJob] = useState<DevelopmentJob | null>(null), [error, setError] = useState(''), [stopping, setStopping] = useState(false);
  const [open, setOpen] = useState(false), [output, setOutput] = useState(''), [more, setMore] = useState(false), [loading, setLoading] = useState(false);
  const [evidence, setEvidence] = useState<DevelopmentEvidence[]>([]);
  const [executionEvidence, setExecutionEvidence] = useState<DevelopmentExecutionEvidence | null>(null);
  const cursor = useRef(0), [kind, setKind] = useState('Output'), [truncated, setTruncated] = useState(false);
  const recoveryId = useRef<string | null>(null);
  const completionId = useRef<string | null>(null);
  const path = `/${projectId}/development/jobs/${jobId}`;
  useEffect(() => {
    const controller = new AbortController(); let timer: number | undefined;
    const refresh = async () => {
      try {
        const page = await projectRequest<DevelopmentJobPage>(path + '?metadataOnly=true', '', 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return; setJob(page.job); setEvidence(page.evidence); setExecutionEvidence(page.executionEvidence ?? null); setError('');
        if (busyRun(page.job.state)) timer = window.setTimeout(() => void refresh(), 2000);
      } catch (e) { if (!controller.signal.aborted) { setError((e as Error).message); timer = window.setTimeout(() => void refresh(), 4000); } }
    };
    void refresh(); return () => { controller.abort(); window.clearTimeout(timer); };
  }, [path]);
  async function readOutput() {
    if (loading) return; setLoading(true);
    try {
      const page = await projectRequest<DevelopmentJobPage>(path + '?offset=' + cursor.current);
      setJob(page.job); setEvidence(page.evidence); setExecutionEvidence(page.executionEvidence ?? null); setOutput((old) => old + page.output); setKind(page.outputKind === 'console' ? 'Console output' : page.outputKind === 'diagnostic' ? 'Diagnostic output' : 'Build output');
      setMore(page.hasMore ?? (page.nextOffset > cursor.current || busyRun(page.job.state))); cursor.current = page.nextOffset; setTruncated(page.truncated); setError('');
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
  async function completeChecks() {
    setStopping(true); completionId.current ??= projectRequestId();
    try {
      const page = await projectRequest<DevelopmentJobPage>(path + '/complete', token, 'POST', { requestId: completionId.current });
      setJob(page.job); setExecutionEvidence(page.executionEvidence ?? null); completionId.current = null; setError('');
    } catch (e) { setError((e as Error).message); } finally { setStopping(false); }
  }
  return <section className="development-card" aria-label="Development job">
    {job?.kind === 'execution' && job.state === 'running' && job.check?.state === 'passed' && !job.checkCompletion && <button type="button" disabled={stopping} onClick={() => void completeChecks()}>Complete checks and close app</button>}
    <div className="development-card-header"><strong>{job?.kind === 'update_recovery' ? 'Recover own update' : job?.kind === 'update_verify' ? 'Verify installed update' : job?.kind === 'update_commit' ? 'Commit update and reboot' : job?.kind === 'update_install' ? 'Install or stage update' : job?.kind === 'update_transfer' ? 'Transfer update package' : job?.kind === 'update_probe' ? 'Check update status' : job?.kind === 'package' ? 'Build update package' : job?.kind === 'vm_start' ? 'Start VM' : job?.kind === 'execution' ? 'Run' : job?.kind === 'deploy' ? 'Deploy' : 'Build'}</strong><span role="status">{job?.state ?? 'Loading'}</span>{job && busyRun(job.state) && <button type="button" disabled={stopping} onClick={() => void stop()}>{stopping ? 'Stopping…' : 'Stop job'}</button>}</div>
    {job && <><p className="development-phase">{({ authenticating: 'Authenticating SSH', resolving_exchange: 'Locating Exchange', checking_exchange_capacity: 'Checking Exchange capacity', transferring: 'Uploading and verifying', verifying_deployment: 'Verifying package', starting_guest: 'Starting application', service_ready: 'Service ready', guest_running: 'Application running', guest_completed: 'Application ended', checking_helper: 'Checking controller', publishing: 'Confirming package', desktop_request: 'Confirming launch request', desktop_accepted: 'Desktop request accepted', desktop_starting: 'Desktop starting application', desktop_process: 'Process confirmed', desktop_window: 'Window attached', desktop_content: 'Desktop content confirmed', window_visible: 'Window visible' } as Record<string, string>)[job.phase] ?? job.phase.replaceAll('_', ' ')}</p>{job.check && <p>Checks: {job.check.state}{job.check.assessment ? ` · ${job.check.assessment}` : ''}</p>}
      {job.check?.findings.map((text, i) => <p key={i}>{text}</p>)}{job.error && <p className="agent-error">{job.error}</p>}</>}
    {job?.nextStep && <p>{job.nextStep}</p>}
    {job?.updatePlan && <p>Package {job.updatePlan.metadata.packageId} {job.updatePlan.metadata.packageVersion} · Target release {job.updatePlan.metadata.targetRelease} · {job.updatePlan.activation}</p>}
    {job?.updatePackage && <p>R4U2 · {job.updatePackage.bytes.toLocaleString()} bytes · SHA-256 <code>{job.updatePackage.sha256}</code></p>}
    {job?.updateProbe && <p>Native preflight: {job.updateProbe.state} · Installed release {job.updateProbe.installedRelease ?? 'unconfirmed'} · Kernel {job.updateProbe.activeKernel ?? 'unconfirmed'}</p>}
    {job?.updateTransfer && <p>{job.updateTransfer.published ? 'Inbox publication confirmed · full byte readback verified' : 'Transport unconfirmed'} · <code>{job.updateTransfer.guestPath ?? job.updateTransfer.final ?? 'No published path'}</code></p>}
    {job?.updateInstallation && <UpdateRecord projectId={projectId} updateId={job.updateInstallation.id} token={token} />}
    {open && job && (job.kind === 'package' || job.kind.startsWith('update_')) && <details><summary>Original package / native receipts</summary><CodeBlock text={JSON.stringify({ plan: job.updatePlan, package: job.updatePackage, preflight: job.updateProbe, transfer: job.updateTransfer, update: job.updateInstallation }, null, 2)} label="Copy original update receipts" language="json" /></details>}
    {job?.checkCompletion && <p>{job.checkCompletion.state === 'completed' ? 'Checks completed · Application closed' : job.checkCompletion.state === 'closing' ? 'Completing checks · Closing application' : 'Check completion failed'}</p>}
    {executionEvidence && <div className="development-execution-evidence" aria-label="Execution evidence">
      <p>Process end: {executionEvidence.processEndConfirmed ? 'Confirmed' : 'Unconfirmed'} · Helper cleanup: {executionEvidence.cleanupConfirmed ? 'Confirmed' : 'Unconfirmed'}</p>
      <p>Exit status: {executionEvidence.exitStatusConfirmed ? executionEvidence.exitCode : 'Unavailable'}{!executionEvidence.exitStatusConfirmed && executionEvidence.exitStatusReason ? ` · ${executionEvidence.exitStatusReason}` : ''}</p>
      <p>Process console: {executionEvidence.output.state}{executionEvidence.output.bytes !== undefined ? ` · ${executionEvidence.output.bytes.toLocaleString()} bytes retained` : ''}. {executionEvidence.output.reason}</p>
    </div>}
    {job?.package && <p className="development-package"><code>{job.package.relativeDirectory}</code>{job.package.format === 'legacy-c' && <small>Historical C: deployment · Deploy again to use Exchange Build.</small>}</p>}
    {job?.readiness && <p>{({ transferred: 'Package verified', ready: 'Application ready', started: 'Process started', completed: 'Application ended', unsupported: 'Start unavailable', unknown: 'Outcome unconfirmed', failed: 'Start failed', interrupted: 'Interrupted' } as Record<string, string>)[job.readiness.state] ?? job.readiness.state}</p>}
    {job?.readiness?.reasonCode === 'desktop_content_unconfirmed' && <><p>{job.readiness.reason}</p>{job.readiness.desktopEvidence && <p>Process confirmed · Window {job.readiness.desktopEvidence.windowVisible ? 'visible' : 'unconfirmed'} / {job.readiness.desktopEvidence.windowFocused ? 'focused' : 'unfocused'} · Content unconfirmed. Original STATUS reconciliation is bounded{job.readiness.desktopEvidence.statusRetentionExpired ? '; native retention expired' : ''}.</p>}</>}
    {job?.liveFileObservation && <details className="development-live-files"><summary>Registered output files · {job.outputFiles?.filter(file=>file.state==='observed-stable').length ?? 0} observed stable</summary>
      <p>Observed {new Date(job.liveFileObservation.checkedAt).toLocaleString()}. File criteria do not confirm process completion.</p>
      <ul>{job.outputFiles?.map(file=><li key={file.name}><strong>{file.name}</strong> · {file.state ?? 'Recorded'}{file.error ? ` · ${file.error}` : file.sha256 ? <> · SHA-256 <code>{file.sha256}</code></> : ''}</li>)}</ul>
    </details>}
    {job?.state === 'unknown' && <p>No action was repeated.</p>}
    {job?.vmStart?.ready && <p>SSH ready · R4OS {job.vmStart.guestRelease}{job.vmStart.checkedAt ? ` · ${new Date(job.vmStart.checkedAt).toLocaleString()}` : ''}</p>}
    {job?.state === 'unknown' && !job.guestState?.closeConfirmed && <button type="button" disabled={stopping} onClick={() => void reconcile()}>{stopping ? 'Reconciling…' : 'Reconcile receipts'}</button>}
    {job?.state === 'unknown' && job.guestState?.closeConfirmed && !executionEvidence && <p>Process end confirmed. Exit status unavailable.</p>}
    {job?.recovery?.reason && <p>{job.recovery.reason}</p>}
    <button type="button" aria-expanded={open} onClick={() => { setOpen(!open); if (!open && !output) void readOutput(); }}>{open ? 'Hide details' : 'Show details'}</button>
    {open && <>{job?.package && <code>{job.package.guestDirectory}</code>}{job?.process && <p>Process {job.process.instanceId} · Generation {job.process.generation}{job.process.serviceName ? ` · ${job.process.serviceName}` : ''}</p>}<CodeBlock text={output} label="Copy job output" language={kind} />{truncated && <p>Output limit reached.</p>}{(more || !!job && busyRun(job.state)) && <button type="button" disabled={loading} onClick={() => void readOutput()}>{loading ? 'Loading…' : 'Load more output'}</button>}</>}
    {open && job?.desktopLaunch && <div className="development-desktop-receipt"><p>DESKRUN · {job.desktopLaunch.phase} · {job.desktopLaunch.error} ({job.desktopLaunch.errorlevel})</p><p>Request <code>{job.desktopLaunch.request}</code></p><p>Window {job.desktopLaunch.window} · Content {job.desktopLaunch.content}</p>{job.desktopLaunch.statusError && <p>Status: {job.desktopLaunch.statusError} · Earlier receipts retained.</p>}</div>}
    {open && evidence.map((entry) => entry.kind === 'screenshot' ? <DevelopmentImage key={entry.id} projectId={projectId} value={{ ...entry, jobId }} /> : entry.kind === 'file' ? <p key={entry.id}><a href={`/api/projects/${projectId}/development/jobs/${jobId}/evidence/${entry.id}`}>{entry.name ?? 'Output file'}</a> · {entry.bytes.toLocaleString()} bytes</p> : null)}
    {error && <p className="agent-error" role="alert">{error}</p>}
  </section>;
}
