import { useEffect, useState } from 'react';
import type { DevelopmentJob } from '../../../../shared/project-development';
import type { UpdateInstallation } from '../../../../shared/update-packages';
import { projectRequest, projectRequestId } from '../agent-sessions/api';
import { CodeBlock } from '../agent-sessions/Transcript';

type Action = 'verify' | 'commit' | 'resume' | 'resume-batch' | 'abort-batch' | 'rollback-last' | 'cleanup';
export function updateActions(record: UpdateInstallation): Action[] {
  const terminal = ['installed', 'live_installed', 'rolled_back', 'aborted'].includes(record.phase);
  const actions: Action[] = ['verify'];
  if (record.phase === 'awaiting_commit' && record.batchId) actions.push('commit', 'abort-batch');
  if (!terminal && record.batchId) actions.push('resume-batch');
  if (!terminal && !record.batchId && record.transactions.length) actions.push('resume');
  if (record.installationConfirmed) actions.push('rollback-last');
  if ((record.installationConfirmed || record.rollbackConfirmed || record.abortConfirmed || record.phase === 'cleanup_unconfirmed') && !record.cleanupConfirmed) actions.push('cleanup');
  return actions;
}
const labels: Record<Action, string> = { verify: 'Verify installed bytes', commit: 'Commit and reboot', resume: 'Resume transaction', 'resume-batch': 'Resume batch (may reboot)', 'abort-batch': 'Abort prepared batch', 'rollback-last': 'Roll back last update (may reboot)', cleanup: 'Clean own transport files' };
export function UpdateRecord({ projectId, updateId, token, submitted }: { projectId: string; updateId: string; token: string; submitted?: (job: DevelopmentJob) => void }) {
  const [record, setRecord] = useState<UpdateInstallation | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false), [refresh, setRefresh] = useState(0), [jobId, setJobId] = useState<string | null>(null);
  const base = `/${projectId}/update-packages`, path = `${base}/installations/${updateId}`;
  useEffect(() => {
    const controller = new AbortController();
    void projectRequest<{ update: UpdateInstallation }>(path, '', 'GET', undefined, controller.signal).then(value => { if (!controller.signal.aborted) { setRecord(value.update); setError(''); } }).catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [path, refresh]);
  async function action(kind: Action) {
    if (!record || busy) return; setBusy(true); setError('');
    try {
      const current = (await projectRequest<{ update: UpdateInstallation }>(path)).update;
      if (current.revision !== record.revision) { setRecord(current); throw new Error('Update changed. Review the current record before acting.'); }
      const reboot = ['commit', 'resume-batch', 'rollback-last'].includes(kind);
      if (kind !== 'verify' && !window.confirm(`${labels[kind]}?\nVM: ${current.vmId}\nTarget release: ${current.targetRelease}\nBatch: ${current.batchId ?? 'live transaction'}\nUpdate: ${current.id}\n${reboot ? 'This action may install or restore files and reboot the guest.' : kind === 'cleanup' ? 'Only complete matching original Inbox package files are removed.' : kind === 'abort-batch' ? 'The prepared own batch will be aborted.' : 'The original own native transaction will be resumed.'}`)) return;
      const common = { requestId: projectRequestId(), projectRevision: (await projectRequest<{ project: { revision: number } }>(`/${projectId}`)).project.revision, updateId, updateRevision: current.revision };
      const body = kind === 'verify' ? { ...common, deadlineSeconds: 120, fullArtifactHashes: true } : { ...common, vmRevision: current.vmRevision, targetRelease: current.targetRelease, confirmReboot: reboot, ...(kind === 'commit' ? { batchId: current.batchId } : { action: kind }) };
      const result = await projectRequest<{ job: DevelopmentJob }>(base + '/' + (kind === 'verify' ? 'verifications' : kind === 'commit' ? 'commits' : 'recovery'), token, 'POST', body);
      setJobId(result.job.id); submitted?.(result.job);
    } catch (e) { setError((e as Error).message + ' No write was repeated. Read the original job before another action.'); }
    finally { setBusy(false); }
  }
  return <section className="update-record" aria-label="Native update record">
    {record ? <><h3>Native update · {record.phase.replaceAll('_', ' ')}</h3><dl className="development-target"><div><dt>Update</dt><dd><code>{record.id}</code> · revision {record.revision}</dd></div><div><dt>VM</dt><dd><code>{record.vmId}</code></dd></div><div><dt>Target release</dt><dd>{record.targetRelease}</dd></div><div><dt>Base image</dt><dd>{record.imageId}</dd></div><div><dt>Batch / transactions</dt><dd>{record.batchId ?? '—'} / {record.transactions.join(', ') || '—'}</dd></div></dl>
      <p role="status">{record.installationConfirmed ? 'Installation confirmed' : record.rollbackConfirmed ? 'Rollback confirmed · installation is not active' : record.abortConfirmed ? 'Prepared batch abort confirmed' : 'Installation unconfirmed'}</p>
      {record.cleanupConfirmed && <p>Own transport cleanup confirmed.</p>}{record.proof && <p>Observed release {record.proof.installedRelease} · Kernel {record.proof.activeKernel} · Full artifact hashes {record.proof.fullArtifactHashesComplete ? 'confirmed' : 'incomplete'} · {new Date(record.proof.confirmedAt).toLocaleString()}</p>}
      {record.error && <p className="project-error">{record.error}</p>}
      <div className="update-actions">{updateActions(record).map(kind => <button key={kind} type="button" disabled={busy || !token} onClick={() => void action(kind)}>{labels[kind]}</button>)}</div>
      <details><summary>Saved native responses and proof</summary><CodeBlock text={JSON.stringify(record, null, 2)} label="Copy update record" language="json" /></details>
    </> : !error && <p role="status">Loading update…</p>}
    {jobId && <p>Action submitted · <code>{jobId}</code>. Refresh the record after its original job ends.</p>}
    <button type="button" disabled={busy} onClick={() => setRefresh(value => value + 1)}>Refresh update record</button>
    {error && <p className="project-error" role="alert">{error}</p>}
  </section>;
}
