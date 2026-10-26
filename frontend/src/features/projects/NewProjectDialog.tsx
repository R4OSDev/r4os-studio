import { ProjectField } from './ProjectField';
import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { Project, ProjectInput, ProjectLanguage, ProjectOptions, ProjectTemplate } from '../../../../shared/projects';
import { projectRequest, projectRequestId, ProjectRequestError } from './api';
import type { GitHubAccount, GitHubJob } from '../../../../shared/project-github';
import { ConnectionSelect } from '../github-connections/ConnectionSelect';
import { waitGitJob } from '../github-connections/projectApi';

const pendingKey = 'studio.project.pendingCreate';
function savedRequest(): ProjectInput | null {
  try {
    const saved = JSON.parse(sessionStorage.getItem(pendingKey) ?? 'null');
    return saved && typeof saved.name === 'string' && typeof saved.description === 'string'
      && typeof saved.requestId === 'string' && typeof saved.optionsRevision === 'string'
      && Array.isArray(saved.guestFormats) ? saved as ProjectInput : null;
  } catch { return null; }
}

export function NewProjectDialog({ token, close, created }: {
  token: string; close: () => void; created: (project: Project) => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [pending, setPending] = useState(savedRequest);
  const [name, setName] = useState(pending?.name ?? '');
  const [description, setDescription] = useState(pending?.description ?? '');
  const [language, setLanguage] = useState<ProjectLanguage>(pending?.language ?? 'Zig');
  const [template, setTemplate] = useState<ProjectTemplate>(pending?.template ?? 'terminal');
  const [vmId, setVmId] = useState(pending?.vmId ?? '');
  const [guestFormats, setGuestFormats] = useState(pending?.guestFormats.join(', ') ?? '');
  const [options, setOptions] = useState<ProjectOptions | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [optionsEpoch, setOptionsEpoch] = useState(0);
  const [account, setAccount] = useState<GitHubAccount | null>(() => {
    try { const value = JSON.parse(sessionStorage.getItem(pendingKey + '.account') ?? 'null'); return value?.connectionId === pending?.github?.connectionId ? value : null; } catch { return null; }
  });
  const [repositoryName, setRepositoryName] = useState(pending?.github?.repositoryName ?? '');
  const [visibility, setVisibility] = useState(pending?.github?.private === false ? 'public' : 'private');
  const [localProject, setLocalProject] = useState<Project>();
  const [gitJob, setGitJob] = useState<GitHubJob>();
  const [mode, setMode] = useState<'create' | 'import'>('create');
  const [accountBusy, setAccountBusy] = useState(false);
  useEffect(() => {
    const element = dialog.current!;
    const opener = document.activeElement;
    element.showModal();
    element.querySelector<HTMLInputElement>('#project-name')?.focus();
    return () => { element.close(); if (opener instanceof HTMLElement && opener.isConnected) opener.focus(); };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void projectRequest<ProjectOptions>('/options', '', 'GET', undefined, controller.signal)
      .then((result) => { if (!controller.signal.aborted) { setOptions(result); setLoading(false); } })
      .catch((cause: Error) => { if (!controller.signal.aborted) { setOptions(null); setError(cause.message); setLoading(false); } });
    return () => controller.abort();
  }, [optionsEpoch]);
  const module = options?.moduleTypes.find((value) => value.id === template);
  const languageOption = options?.languages.find((value) => value.id === language);
  const supported = !!languageOption?.available && !!module?.available && module.languages.includes(language);
  const capability = options && !supported ? languageOption?.reason ?? module?.reasons?.[language] ?? 'This language and module type are not supported.' : '';

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || accountBusy || (!pending && (!supported || !options))) return;
    setError('');
    if (account && (!/^[A-Za-z0-9_.-]{1,100}$/.test(repositoryName.trim()) || ['.', '..'].includes(repositoryName.trim()))) {
      setError('Enter a valid repository name.'); return;
    }
    const formats = guestFormats.split(',').map((value) => value.trim()).filter(Boolean);
    if (!pending && template === 'subsystem' && (!formats.length || formats.some((value) => !/^[a-z](?:[a-z0-9_.-]*[a-z0-9])?$/.test(value) || value.length > 63))) {
      setError('Enter valid comma-separated guest format IDs.'); return;
    }
    let input: ProjectInput = pending ?? { name: name.trim(), description, language, template, vmId: vmId || null,
      guestFormats: template === 'subsystem' ? formats : [], optionsRevision: options!.revision, requestId: projectRequestId(),
      ...(account ? { github: { requestId: projectRequestId(), connectionId: account.connectionId, userId: account.userId,
        tokenRevision: account.tokenRevision, repositoryName: repositoryName.trim(), private: visibility === 'private' } } : {}) };
    if (pending && localProject && gitJob?.state === 'failed' && account) input = { ...pending, github: {
      requestId: projectRequestId(), connectionId: account.connectionId, userId: account.userId, tokenRevision: account.tokenRevision,
      repositoryName: repositoryName.trim(), private: visibility === 'private' } };
    try { sessionStorage.setItem(pendingKey, JSON.stringify(input)); }
    catch { setError('The browser could not retain this request. Enable session storage and retry.'); return; }
    setPending(input); setBusy(true);
    try {
      const result = await projectRequest<{ project: Project; githubJob?: GitHubJob; githubError?: string }>('', token, 'POST', input);
      setLocalProject(result.project);
      if (input.github) {
        if (result.githubError) setError(result.githubError);
        const job = await waitGitJob(result.project.id, input.github.requestId, result.githubJob, setGitJob);
        if (job.state !== 'completed') { setError(job.error ?? 'GitHub setup could not be confirmed. Keep the local project or reconcile this original request.'); return; }
      }
      try { sessionStorage.removeItem(pendingKey); } catch { /* The completed server request remains idempotent. */ }
      sessionStorage.removeItem(pendingKey + '.account');
      await created(result.project);
    } catch (cause) {
      const failure = cause as ProjectRequestError;
      if (!input.github && failure.status && failure.status < 500) {
        sessionStorage.removeItem(pendingKey); setPending(null);
        if (failure.status === 409) { setLoading(true); setOptionsEpoch((value) => value + 1); }
      }
      setError(failure.message || 'The result could not be confirmed. Retry this request.');
    } finally { setBusy(false); }
  }

  return <dialog ref={dialog} className="project-dialog" aria-labelledby="new-project-title"
    onCancel={(event) => { event.preventDefault(); if (!busy) close(); }}>
    <form onSubmit={(event) => void submit(event)}>
      <header className="project-dialog-header"><h2 id="new-project-title">New Project</h2>
        <button type="button" className="project-close" aria-label="Close" disabled={busy} onClick={close}><span aria-hidden="true">×</span></button></header>
      <div className="project-form-row" aria-label="Project source">
        <button type="button" aria-pressed={mode === 'create'} disabled={busy || !!pending} onClick={() => setMode('create')}>Create new</button>
        <button type="button" aria-pressed={mode === 'import'} disabled title="Import becomes available with the next project update.">Import from GitHub</button>
      </div>
      <fieldset className="project-fields" disabled={busy || !!pending}>
        <ProjectField id="project-name" label="Name">
          <input id="project-name" required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} autoComplete="off" /></ProjectField>
        <ProjectField id="project-description" label="Description">
          <textarea id="project-description" rows={3} maxLength={4000} value={description} onChange={(event) => setDescription(event.target.value)} /></ProjectField>
        <div className="project-form-row">
          <fieldset className="project-language"><legend>Language</legend><div className="project-language-options">
            {(['Rust', 'Zig', 'C'] as const).map((value) => <label key={value} className={language === value ? 'checked' : ''}>
              <input type="radio" name="project-language" value={value} checked={language === value} onChange={() => setLanguage(value)} /><span>{value}</span></label>)}
          </div></fieldset>
          <ProjectField id="project-module-type" label="Module type">
            <select id="project-module-type" value={template} onChange={(event) => setTemplate(event.target.value as ProjectTemplate)}>
              {(options?.moduleTypes ?? [{ id: template, label: loading ? 'Loading…' : 'Unavailable', languages: [language], available: false }]).map((value) =>
                <option key={value.id} value={value.id} disabled={!value.available || !value.languages.includes(language)}>{value.label}</option>)}
            </select></ProjectField>
        </div>
        {capability && <p className="project-message" role="status">{capability}</p>}
        {template === 'subsystem' && <ProjectField id="project-formats" label="Guest formats">
          <input id="project-formats" required value={guestFormats} onChange={(event) => setGuestFormats(event.target.value)} autoComplete="off" /></ProjectField>}
        <ProjectField id="project-vm" label="Virtual machine">
          <select id="project-vm" value={vmId} onChange={(event) => setVmId(event.target.value)}>
            <option value="">None</option>{vmId && !options?.vms.some((vm) => vm.id === vmId) && <option value={vmId}>Unavailable virtual machine</option>}
            {options?.vms.map((vm) => <option key={vm.id} value={vm.id}>{vm.name}</option>)}
          </select></ProjectField>
        {options && !options.vmsAvailable && <p className="project-message" role="status">Virtual machines could not be loaded.</p>}
      </fieldset>
      <fieldset className="project-fields" disabled={busy || (!!pending && (!localProject || gitJob?.state !== 'failed'))}>
        <ConnectionSelect value={account} busyChanged={setAccountBusy} changed={(value) => { setAccount(value); if (value) sessionStorage.setItem(pendingKey + '.account', JSON.stringify(value)); else sessionStorage.removeItem(pendingKey + '.account'); }} />
        {(account || pending?.github) && <>
          <ProjectField id="github-repository-name" label="Repository name"><input id="github-repository-name" required pattern="[A-Za-z0-9_.-]{1,100}" maxLength={100} value={repositoryName} onChange={(e) => setRepositoryName(e.target.value)} /></ProjectField>
          <ProjectField id="github-visibility" label="Visibility"><select id="github-visibility" value={visibility} onChange={(e) => setVisibility(e.target.value)}><option value="private">Private</option><option value="public">Public</option></select></ProjectField>
          <p>Create an empty repository for {account ? '@' + account.login : 'the retained GitHub account'}. Your first upload will use Push with a commit message.</p>
        </>}
      </fieldset>
      {localProject && <p role="status">Local project created: {localProject.name}. GitHub setup keeps its original request.</p>}
      {gitJob && <p role="status">GitHub: {gitJob.phase} · {gitJob.state}</p>}
      {loading && <p className="project-dialog-status" role="status">Loading project options…</p>}
      {error && <p className="project-dialog-error" role="alert">{error}</p>}
      <footer className="project-actions"><button type="button" disabled={busy} onClick={close}>Cancel</button>
        {localProject && !busy && <button type="button" onClick={() => { sessionStorage.removeItem(pendingKey); sessionStorage.removeItem(pendingKey + '.account'); void created(localProject); }}>Open local project</button>}
        <button className="project-primary" type="submit" disabled={busy || accountBusy || !token || (!pending && (!supported || !name.trim() || loading))}>
          {busy ? 'Creating…' : pending ? 'Retry' : account ? 'Create project & repository' : 'Create Project'}</button></footer>
    </form>
  </dialog>;
}
