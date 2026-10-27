import { useEffect, useRef, useState } from 'react';
import type { GitHubAccount, GitHubImportPreview, GitHubJob } from '../../../../shared/project-github';
import type { Project, ProjectLanguage, ProjectOptions, ProjectTemplate } from '../../../../shared/projects';
import { ConnectionSelect } from '../github-connections/ConnectionSelect';
import { RepositorySelect } from '../github-connections/RepositorySelect';
import type { RepositoryChoice } from '../github-connections/RepositorySelect';
import { waitGitJob } from '../github-connections/projectApi';
import { projectRequest, projectRequestId } from './api';
import { ProjectField } from './ProjectField';
import { HostSelect } from '../remote-hosts/HostSelect';

const key = 'studio.project.pendingImport';
interface ImportInput { requestId: string; connectionId: string; tokenRevision: number; userId: number; repository: { id: number; owner: string; name: string }; branch: string }
function retained(): { input: ImportInput; finish?: Record<string, unknown> } | null {
  try { const value = JSON.parse(sessionStorage.getItem(key) ?? 'null'); return typeof value?.input?.requestId === 'string' ? value : null; } catch { return null; }
}
export function hasPendingImport() { return !!retained(); }

export function ImportProjectDialog({ token, close, created, back }: { token: string; close: () => void; created: (project: Project) => Promise<void>; back: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [account, setAccount] = useState<GitHubAccount | null>(null), [choice, setChoice] = useState<RepositoryChoice | null>(null);
  const [pending, setPending] = useState(retained), [preview, setPreview] = useState<GitHubImportPreview | null>(null);
  const [job, setJob] = useState<GitHubJob>(), [busy, setBusy] = useState(false), [accountBusy, setAccountBusy] = useState(false), [error, setError] = useState('');
  const [name, setName] = useState(String(pending?.finish?.name ?? '')), [description, setDescription] = useState(String(pending?.finish?.description ?? ''));
  const [vmId, setVmId] = useState(String(pending?.finish?.vmId ?? '')), [remoteHostId, setRemoteHostId] = useState(String(pending?.finish?.remoteHostId ?? ''));
  const [vms, setVms] = useState<Pick<ProjectOptions, 'vms' | 'vmsAvailable'>>({ vms: [], vmsAvailable: true });
  const [options, setOptions] = useState<ProjectOptions>(), [language, setLanguage] = useState<ProjectLanguage>('Zig'), [template, setTemplate] = useState<ProjectTemplate>('terminal'), [acceptProfile, setAcceptProfile] = useState(false);
  useEffect(() => { const element = dialog.current!, opener = document.activeElement; element.showModal(); return () => { element.close(); if (opener instanceof HTMLElement && opener.isConnected) opener.focus(); }; }, []);
  useEffect(() => { const controller = new AbortController(); void projectRequest<Pick<ProjectOptions, 'vms' | 'vmsAvailable'>>('/vms', '', 'GET', undefined, controller.signal)
    .then((value) => { if (!controller.signal.aborted) setVms(value); }).catch(() => { if (!controller.signal.aborted) setVms({ vms: [], vmsAvailable: false }); }); return () => controller.abort(); }, []);
  async function fetchImport() {
    if (busy || (!pending && (!account || !choice))) return;
    const input = pending?.input ?? { requestId: projectRequestId(), connectionId: account!.connectionId, tokenRevision: account!.tokenRevision, userId: account!.userId, repository: { id: choice!.repository.id, owner: choice!.repository.owner, name: choice!.repository.name }, branch: choice!.branch };
    const retainedInput = pending ?? { input };
    try { sessionStorage.setItem(key, JSON.stringify(retainedInput)); } catch { setError('Enable session storage to retain this import request.'); return; }
    setPending(retainedInput); setBusy(true); setError('');
    try {
      const accepted = await projectRequest<GitHubJob>('/github/imports', token, 'POST', input);
      const result = await waitGitJob(input.requestId, input.requestId, accepted, setJob);
      if (result.state !== 'completed' || !result.result || !('import' in result.result) || !result.result.import) throw new Error(result.error ?? 'Reconcile the original import before continuing.');
      const value = result.result.import; setPreview(value); if (!name) setName(value.binding.repository.name);
      if (!value.metadata) setOptions(await projectRequest<ProjectOptions>('/options'));
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function finishImport() {
    if (!preview || !pending || busy) return;
    const completion = pending.finish ?? { name: name.trim(), description, snapshot: preview.snapshot, vmId: vmId || null, remoteHostId: remoteHostId || null,
      ...(!preview.metadata && options ? { fallback: { optionsRevision: options.revision, language, template } } : {}) };
    const saved = { ...pending, finish: completion };
    try { sessionStorage.setItem(key, JSON.stringify(saved)); } catch { setError('The browser could not retain this completion.'); return; }
    setPending(saved); setBusy(true); setError('');
    try { const project = await projectRequest<Project>('/github/imports/' + pending.input.requestId + '/finish', token, 'POST', completion); sessionStorage.removeItem(key); await created(project); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  const selectedType = options?.moduleTypes.find((v) => v.id === template);
  const fallbackAvailable = acceptProfile && options?.languages.some((v) => v.id === language && v.available) && selectedType?.languages.includes(language);
  return <dialog ref={dialog} className="project-dialog" aria-labelledby="import-project-title" onCancel={(e) => { e.preventDefault(); if (!busy) close(); }}>
    <form onSubmit={(e) => { e.preventDefault(); void (preview ? finishImport() : fetchImport()); }}>
      <header className="project-dialog-header"><h2 id="import-project-title">New Project</h2><button type="button" className="project-close" aria-label="Close" disabled={busy} onClick={close}>×</button></header>
      <div className="project-form-row" aria-label="Project source"><button type="button" aria-pressed="false" disabled={busy || !!pending} onClick={back}>Create new</button><button type="button" aria-pressed="true">Import from GitHub</button></div>
      <p>Import one R4OS app from a repository root, including its branch history. Studio creates a new local project with your chosen local targets.</p>
      {!pending && <fieldset className="project-fields" disabled={busy}><ConnectionSelect value={account} busyChanged={setAccountBusy} changed={(value) => { setAccount(value); setChoice(null); }} />
        {account && <RepositorySelect key={account.connectionId + ':' + account.tokenRevision} account={account} changed={setChoice} disabled={busy} />}</fieldset>}
      {pending && <p>Repository: {pending.input.repository.owner}/{pending.input.repository.name} · {pending.input.branch}</p>}
      {job && <p role="status">Import: {job.phase} · {job.state}</p>}
      {preview && <>
        <p>{preview.files} files · Commit {preview.commit.slice(0, 12)}</p>
        <fieldset className="project-fields" disabled={busy || !!pending?.finish}>
          <ProjectField id="import-name" label="Project name"><input id="import-name" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></ProjectField>
          <ProjectField id="import-description" label="Description"><textarea id="import-description" maxLength={4000} value={description} onChange={(e) => setDescription(e.target.value)} /></ProjectField>
          <ProjectField id="import-vm" label="Virtual machine"><select id="import-vm" value={vmId} onChange={(event) => setVmId(event.target.value)}>
            <option value="">None</option>{vmId && !vms.vms.some((vm) => vm.id === vmId) && <option value={vmId}>Unavailable virtual machine</option>}{vms.vms.map((vm) => <option key={vm.id} value={vm.id}>{vm.name}</option>)}
          </select></ProjectField>{!vms.vmsAvailable && <p className="project-message">Virtual machines could not be loaded.</p>}
          <HostSelect value={remoteHostId} changed={setRemoteHostId} disabled={busy || !!pending?.finish} />
          {preview.metadata ? <p>Keep original pins: {preview.metadata.language} · {preview.metadata.template} · SDK {preview.metadata.pins.sdk.version} · Contract {preview.metadata.pins.contract.version} · Zig {preview.metadata.pins.zig.version}</p> : <>
            <p>This repository has no portable Studio pins. Explicitly assign the installed profile below; repository files will be preserved.</p>
            <ProjectField id="import-language" label="Language"><select id="import-language" value={language} onChange={(e) => setLanguage(e.target.value as ProjectLanguage)}>{options?.languages.map((v) => <option key={v.id} value={v.id} disabled={!v.available}>{v.id}</option>)}</select></ProjectField>
            <ProjectField id="import-template" label="Module type"><select id="import-template" value={template} onChange={(e) => setTemplate(e.target.value as ProjectTemplate)}>{options?.moduleTypes.map((v) => <option key={v.id} value={v.id} disabled={!v.languages.includes(language)}>{v.label}</option>)}</select></ProjectField>
            <label><input type="checkbox" checked={acceptProfile} onChange={(e) => setAcceptProfile(e.target.checked)} /> Assign SDK {options?.profile.sdk.version}, Contract {options?.profile.contract.version} and Zig {options?.profile.zig.version} to this import</label>
          </>}
        </fieldset>
      </>}
      {error && <p className="project-dialog-error" role="alert">{error}</p>}
      <footer className="project-actions"><button type="button" disabled={busy} onClick={close}>Cancel</button>
        {job?.state === 'failed' && <button type="button" disabled={busy} onClick={() => { sessionStorage.removeItem(key); setPending(null); setJob(undefined); setError(''); }}>Start a new import</button>}
        {job?.state === 'unknown' && pending && <button type="button" disabled={busy} onClick={() => { setBusy(true); void projectRequest<GitHubJob>(`/${pending.input.requestId}/github/jobs/${pending.input.requestId}/reconcile`, token, 'POST', {}).then(setJob).catch((e: Error) => setError(e.message)).finally(() => setBusy(false)); }}>Reconcile original import</button>}
        <button type="submit" className="project-primary" disabled={busy || accountBusy || !token || (preview ? !name.trim() || (!preview.metadata && !fallbackAvailable && !pending?.finish) : !pending && (!account || !choice))}>{busy ? 'Importing…' : preview ? pending?.finish ? 'Retry original completion' : 'Import Project' : pending ? 'Resume original import' : 'Fetch repository'}</button>
      </footer>
    </form>
  </dialog>;
}
