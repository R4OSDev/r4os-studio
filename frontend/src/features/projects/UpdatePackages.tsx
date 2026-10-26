import { useEffect, useRef, useState } from 'react';
import type { DevelopmentJob, DevelopmentOptions, DevelopmentSettings } from '../../../../shared/project-development';
import type { UpdateInstallation, UpdatePackageArtifact, UpdatePackageMetadata, UpdatePackageOptions, UpdatePackagePlan, UpdateRequirement } from '../../../../shared/update-packages';
import { busyRun, projectRequest, projectRequestId } from '../agent-sessions/api';
import { DevelopmentCard } from '../agent-sessions/DevelopmentCard';
import { ProjectField } from './ProjectField';
import { UpdateRecord } from './UpdateRecord';
const empty: UpdatePackageMetadata = { packageId: '', packageVersion: '', targetRelease: '', title: '', description: '' };
type Summary = Pick<UpdateInstallation, 'id' | 'phase' | 'updatedAt'>;
export function UpdatePackages({ id, token, dirtyChanged, busyChanged }: { id: string; token: string; dirtyChanged: (value: boolean) => void; busyChanged: (value: boolean) => void }) {
  const [options, setOptions] = useState<UpdatePackageOptions | null>(null), [target, setTarget] = useState<DevelopmentOptions | null>(null);
  const [metadata, setMetadata] = useState(empty), [requirements, setRequirements] = useState<UpdateRequirement[]>([]), [selected, setSelected] = useState<string[]>([]);
  const [saved, setSaved] = useState(''), [jobs, setJobs] = useState<DevelopmentJob[]>([]), [updates, setUpdates] = useState<Summary[]>([]);
  const [plan, setPlan] = useState<UpdatePackagePlan | null>(null), [planId, setPlanId] = useState(''), [packageId, setPackageId] = useState(''), [transfers, setTransfers] = useState<string[]>([]), [updateId, setUpdateId] = useState(''), [jobId, setJobId] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState(''), [epoch, setEpoch] = useState(0);
  const initialized = useRef(false), packageBase = `/${id}/update-packages`, developmentBase = `/${id}/development`;
  const dirty = saved !== '' && JSON.stringify({ metadata, requirements }) !== saved;
  useEffect(() => { dirtyChanged(dirty); return () => dirtyChanged(false); }, [dirty, dirtyChanged]);
  useEffect(() => { busyChanged(busy); return () => busyChanged(false); }, [busy, busyChanged]);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      projectRequest<UpdatePackageOptions>(packageBase, '', 'GET', undefined, controller.signal),
      projectRequest<DevelopmentJob[]>(developmentBase + '/jobs', '', 'GET', undefined, controller.signal),
      projectRequest<{ updates: Summary[] }>(packageBase + '/installations', '', 'GET', undefined, controller.signal),
      projectRequest<DevelopmentOptions>(developmentBase + '/options', '', 'GET', undefined, controller.signal),
    ]).then(([o, j, u, t]) => {
      if (controller.signal.aborted) return;
      setOptions(o); setJobs(j); setUpdates(u.updates); setTarget(t);
      if (!initialized.current) { const m = o.settings.metadata ?? empty; setMetadata(m); setRequirements(o.settings.requirements); setSaved(JSON.stringify({ metadata: m, requirements: o.settings.requirements })); initialized.current = true; }
      setError('');
    }).catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [packageBase, developmentBase, epoch]);
  useEffect(() => {
    if (!planId) return;
    const controller = new AbortController();
    void projectRequest<{ plan: UpdatePackagePlan }>(packageBase + '/plans/' + planId, '', 'GET', undefined, controller.signal).then(value => { if (!controller.signal.aborted) setPlan(value.plan); }).catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [packageBase, planId]);
  useEffect(() => {
    if (!jobs.some(job => busyRun(job.state))) return;
    const timer = window.setTimeout(() => setEpoch(value => value + 1), 3000); return () => window.clearTimeout(timer);
  }, [jobs]);
  const admitted = (job: DevelopmentJob) => { setJobId(job.id); setJobs(old => [job, ...old.filter(value => value.id !== job.id)]); setEpoch(value => value + 1); };
  async function createPlan() {
    if (!options) return; setBusy(true); setError(''); setNotice('');
    try {
      const result = await projectRequest<{ plan: UpdatePackagePlan }>(packageBase + '/plans', token, 'POST', { requestId: projectRequestId(), projectRevision: options.projectRevision, configurationRevision: options.settings.revision, metadata, artifactIds: selected, requirements: requirements.map(({ kind, name, target, minVersion, state }) => ({ kind, name, target, minVersion, state })) });
      setPlanId(result.plan.id); setPlan(result.plan); setSaved(JSON.stringify({ metadata, requirements })); setNotice('Immutable plan created. Review its targets before building.'); setEpoch(value => value + 1);
    } catch (e) { setError((e as Error).message + ' No request was repeated. Refresh and inspect existing plans before creating another.'); }
    finally { setBusy(false); }
  }
  async function submit(kind: 'build' | 'package' | 'probe' | 'transfer' | 'install') {
    if (!options) return; setBusy(true); setError(''); setNotice('');
    try {
      let path = packageBase, input: Record<string, unknown> = { requestId: projectRequestId(), projectRevision: options.projectRevision };
      if (kind === 'build') { path = developmentBase + '/builds'; input.settingsRevision = (await projectRequest<DevelopmentSettings>(developmentBase + '/settings')).revision; }
      if (kind === 'package') { if (!plan) return; path += '/builds'; input = { ...input, planId: plan.id, planSha256: plan.sha256 }; }
      if (kind === 'probe' || kind === 'transfer') { path += kind === 'probe' ? '/probes' : '/transfers'; input.packageArtifactId = packageId; }
      if (kind === 'install') { path += '/installs'; input.transferJobIds = transfers; }
      if (kind === 'transfer' || kind === 'install') {
        const selectedPackages = kind === 'install' ? jobs.filter(job => transfers.includes(job.id)).map(job => job.updateTransfer?.packageArtifactId ?? '') : [packageId];
        const packages = await Promise.all(selectedPackages.map(ident => projectRequest<{ artifact: UpdatePackageArtifact }>(packageBase + '/artifacts/' + ident)));
        const review = packages.map(({ artifact }) => `${artifact.plan.metadata.packageId} ${artifact.plan.metadata.packageVersion} → OS ${artifact.plan.metadata.targetRelease}\n${artifact.plan.payloads.map(payload => payload.component.name + ' ' + payload.component.version + ' → ' + payload.target).join('\n')}`).join('\n\n');
        if (!window.confirm(`${kind === 'install' ? 'Verify and install/stage these packages? STAGE can apply files immediately.' : 'Upload this package to the assigned VM Inbox?'}\nVM: ${target?.assignedVm?.name ?? 'Unavailable'} (${target?.assignedVm?.id ?? '—'})\nPackages:\n${review}\n${kind === 'install' ? 'Each package retains its explicit target release. Commit/reboot is a separate action.' : 'Original bytes will be read back and hashed.'}`)) return;
      }
      admitted((await projectRequest<{ job: DevelopmentJob }>(path, token, 'POST', input)).job);
    } catch (e) { setError((e as Error).message + ' No action was repeated. Refresh existing jobs before another submission.'); }
    finally { setBusy(false); }
  }
  const patchRequirement = (index: number, change: Partial<UpdateRequirement>) => setRequirements(old => old.map((item, i) => i === index ? { ...item, ...change } : item));
  const packageJobs = jobs.filter(job => job.kind === 'package' && job.state === 'completed' && job.packageArtifactId);
  const transferJobs = jobs.filter(job => job.kind === 'update_transfer' && job.state === 'completed' && job.updateTransfer?.published);
  const unavailable = busy || !options || !token || jobs.some(job => busyRun(job.state));
  return <section className="project-settings update-packages" aria-label="Update packages">
    <h2>Update packages</h2><p className="project-message">Build a persistent native R4OS update for the assigned VM. Start the VM explicitly before checking or transferring.</p>
    <div className="project-fields"><dl className="development-target"><div><dt>Assigned VM</dt><dd>{target?.assignedVm?.name ?? 'No VM assigned'} · {target?.assignedVm?.imageId ?? '—'}</dd></div><div><dt>Packer</dt><dd>{options?.packer?.available && options.packer.pin ? `${options.packer.pin.id} · SHA-256 ${options.packer.pin.sha256}` : options?.packer?.reason ?? (options ? 'The development host must adopt this release to report packer qualification.' : 'Loading qualification…')}</dd></div></dl>
      <button type="button" disabled={unavailable} onClick={() => void submit('build')}>Build current project</button>
      <form aria-label="Update package plan" onSubmit={event => { event.preventDefault(); void createPlan(); }}><fieldset className="update-fields" disabled={unavailable}>
        {(['packageId', 'packageVersion', 'targetRelease', 'title', 'description'] as const).map(key => <ProjectField key={key} id={`update-${key}`} label={({ packageId: 'Package ID', packageVersion: 'Package version', targetRelease: 'Target OS release', title: 'Title', description: 'Description' })[key]}><input id={`update-${key}`} required maxLength={key === 'description' ? 2048 : key === 'title' ? 96 : key === 'packageId' ? 48 : 24} value={metadata[key]} onChange={event => setMetadata(old => ({ ...old, [key]: event.target.value }))} placeholder={key === 'packageVersion' || key === 'targetRelease' ? '0.0.0' : undefined} /></ProjectField>)}
        <fieldset className="update-choices"><legend>Confirmed build artifacts ({selected.length}/32)</legend>{options?.artifacts.map(artifact => <label key={artifact.id}><input type="checkbox" checked={selected.includes(artifact.id)} disabled={!artifact.updateMetadata?.available || !selected.includes(artifact.id) && selected.length >= 32} onChange={event => setSelected(old => event.target.checked ? [...old, artifact.id] : old.filter(value => value !== artifact.id))} /><span>{artifact.entry} · {artifact.updateMetadata?.identity?.version ?? artifact.updateMetadata?.reason ?? 'Native metadata unavailable'}<small>{artifact.updateMetadata?.identity?.target} · {artifact.id}</small></span></label>)}{!options?.artifacts.length && <p>Build the project to capture a payload.</p>}</fieldset>
        <h3>Explicit requirements ({requirements.length}/32)</h3><p>Use actual installed component identities and minimum versions. Only the kernel may require active state.</p>
        {requirements.map((item, index) => <fieldset className="update-fields" key={index}><legend>Requirement {index + 1}</legend><ProjectField id={`require-kind-${index}`} label="Kind"><select id={`require-kind-${index}`} value={item.kind} onChange={event => patchRequirement(index, { kind: event.target.value as UpdateRequirement['kind'], state: 'installed' })}>{['KERNEL', 'R4X', 'R4L', 'R4D', 'R4P'].map(kind => <option key={kind}>{kind}</option>)}</select></ProjectField>{(['name', 'target', 'minVersion'] as const).map(key => <ProjectField key={key} id={`require-${key}-${index}`} label={key === 'minVersion' ? 'Minimum version' : key === 'target' ? 'Installation target' : 'Component name'}><input id={`require-${key}-${index}`} required value={item[key]} onChange={event => patchRequirement(index, { [key]: event.target.value })} /></ProjectField>)}<ProjectField id={`require-state-${index}`} label="Required state"><select id={`require-state-${index}`} value={item.state} onChange={event => patchRequirement(index, { state: event.target.value as UpdateRequirement['state'] })}><option value="installed">Installed</option>{item.kind === 'KERNEL' && <option value="active">Active</option>}</select></ProjectField><button type="button" onClick={() => setRequirements(old => old.filter((_, i) => i !== index))}>Remove requirement</button></fieldset>)}
        <button type="button" disabled={requirements.length >= 32} onClick={() => setRequirements(old => [...old, { kind: 'R4X', name: '', target: '', minVersion: '', state: 'installed' }])}>Add requirement</button>
        <button type="submit" disabled={!selected.length || !options?.packer?.available}>Create immutable plan</button><button type="button" disabled={!dirty} onClick={() => { if (saved) { const value = JSON.parse(saved); setMetadata(value.metadata); setRequirements(value.requirements); } }}>Discard metadata changes</button>
      </fieldset></form>
      <ProjectField id="update-plan" label="Saved plan"><select id="update-plan" value={planId} disabled={busy} onChange={event => { setPlan(null); setPlanId(event.target.value); }}><option value="">Choose a plan</option>{options?.plans.map(value => <option key={value.id} value={value.id}>{value.metadata.packageId} {value.metadata.packageVersion} → {value.metadata.targetRelease} · {value.id}</option>)}</select></ProjectField>
      {plan && <><p>Target release {plan.metadata.targetRelease} · {plan.activation} · {plan.priority}</p><ul>{plan.payloads.map(payload => <li key={payload.artifactId}>{payload.component.name} {payload.component.version} → <code>{payload.target}</code></li>)}</ul><p>{plan.requirements.length} requirements · up to {plan.containerByteUpperBound.toLocaleString()} bytes · Packer {plan.packer.id}</p><button type="button" disabled={unavailable} onClick={() => void submit('package')}>Build selected package</button></>}
      <ProjectField id="update-package" label="Built package"><select id="update-package" value={packageId} disabled={busy} onChange={event => setPackageId(event.target.value)}><option value="">Choose a package</option>{packageJobs.map(job => <option key={job.id} value={job.packageArtifactId ?? ''}>{job.updatePlan?.metadata.packageId ?? 'Package'} · target {job.updatePlan?.metadata.targetRelease ?? '—'} · {job.packageArtifactId}</option>)}</select></ProjectField>
      <div className="update-actions"><button type="button" disabled={unavailable || !packageId || !target?.assignedVm} onClick={() => void submit('probe')}>Check assigned VM</button><button type="button" disabled={unavailable || !packageId || !target?.assignedVm} onClick={() => void submit('transfer')}>Upload and verify bytes</button></div>
      <fieldset className="update-choices" disabled={unavailable}><legend>Published transfers ({transfers.length}/16)</legend>{transferJobs.map(job => <label key={job.id}><input type="checkbox" checked={transfers.includes(job.id)} disabled={!transfers.includes(job.id) && transfers.length >= 16} onChange={event => setTransfers(old => event.target.checked ? [...old, job.id] : old.filter(value => value !== job.id))} /><span>{job.updateTransfer?.guestPath}<small>{job.updateTransfer?.sha256} · {job.id}</small></span></label>)}</fieldset>
      <button type="button" disabled={unavailable || !transfers.length} onClick={() => void submit('install')}>Verify and install / stage selected transfers</button>
      <ProjectField id="native-update" label="Saved native update"><select id="native-update" value={updateId} disabled={busy} onChange={event => setUpdateId(event.target.value)}><option value="">Choose an update</option>{updates.map(value => <option key={value.id} value={value.id}>{value.phase} · {value.id}</option>)}</select></ProjectField>
      {updateId && <UpdateRecord key={updateId} projectId={id} updateId={updateId} token={token} submitted={admitted} />}
      <ProjectField id="update-job" label="Original jobs"><select id="update-job" value={jobId} onChange={event => setJobId(event.target.value)}><option value="">Choose a job</option>{jobs.map(job => <option key={job.id} value={job.id}>{job.kind.replaceAll('_', ' ')} · {job.state} · {job.id}</option>)}</select></ProjectField>
      {jobId && <DevelopmentCard key={jobId} projectId={id} jobId={jobId} token={token} />}
      <button type="button" disabled={busy} onClick={() => setEpoch(value => value + 1)}>Refresh packages and jobs</button>
      {notice && <p role="status">{notice}</p>}{error && <p className="project-error" role="alert">{error}</p>}
    </div>
  </section>;
}
