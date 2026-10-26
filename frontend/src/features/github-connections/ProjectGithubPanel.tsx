import { useEffect, useState } from 'react';
import type { GitHubAccount, GitHubDiff, GitHubJob, GitHubProjectBinding, GitHubProjectStatus } from '../../../../shared/project-github';
import type { GitHubConnection } from '../../../../shared/github-connections';
import { projectRequest } from '../projects/api';
import { ConnectionSelect } from './ConnectionSelect';
import { RepositorySelect } from './RepositorySelect';
import type { RepositoryChoice } from './RepositorySelect';
import { clearGit, clearPull, pendingGit, pendingPull, pullProject, runGitJob, waitGitJob } from './projectApi';
import { loadConnections } from './api';
import './project.css';

const labels: Record<string, string> = { not_connected: 'Local project', unknown: 'Remote state unknown', not_pushed: 'Not pushed yet', remote_only: 'Remote history requires import', branch_missing: 'Remote branch missing', diverged: 'Local and remote history diverged', ahead: 'Local commits ready to push', behind: 'Remote commits available', up_to_date: 'Up to date at last check' };
export function ProjectGithubPanel({ id, token, dirtyChanged, busyChanged }: { id: string; token: string; dirtyChanged?: (value: boolean) => void; busyChanged?: (value: boolean) => void }) {
  const [binding, setBinding] = useState<GitHubProjectBinding | null>(null), [job, setJob] = useState<GitHubJob | null>(null), [status, setStatus] = useState<GitHubProjectStatus>();
  const [connections, setConnections] = useState<GitHubConnection[]>([]), [kinds, setKinds] = useState<string[]>([]);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [editing, setEditing] = useState(false), [diff, setDiff] = useState<GitHubDiff>();
  const [commitMessage, setCommitMessage] = useState(''), [allFiles, setAllFiles] = useState(true), [files, setFiles] = useState<string[]>([]);
  useEffect(() => { busyChanged?.(busy); return () => busyChanged?.(false); }, [busy, busyChanged]);
  useEffect(() => { dirtyChanged?.(editing || !!commitMessage.trim()); return () => dirtyChanged?.(false); }, [editing, commitMessage, dirtyChanged]);
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const [value, capabilities, root] = await Promise.all([projectRequest<{ binding: GitHubProjectBinding | null; job: GitHubJob | null }>(`/${id}/github`, '', 'GET', undefined, controller.signal), projectRequest<{ kinds?: string[] }>('/github/capabilities', '', 'GET', undefined, controller.signal), loadConnections()]);
        if (controller.signal.aborted) return;
        setBinding(value.binding); setJob(value.job); setKinds(capabilities.kinds ?? []); setConnections(root.connections);
        if (value.job && ['running', 'queued'].includes(value.job.state)) { setBusy(true); await waitGitJob(id, value.job.id, value.job, setJob, controller.signal); }
        const read = await runGitJob(id, token, 'status', {});
        if (!controller.signal.aborted && read.result && 'snapshot' in read.result) setStatus(read.result);
      } catch (e) { if (!controller.signal.aborted) setError((e as Error).message); }
      finally { if (!controller.signal.aborted) { setLoading(false); setBusy(false); } }
    })();
    return () => controller.abort();
  }, [id, token]);
  async function update(kind: string, input: Record<string, unknown> = {}, original = false) {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const result = await runGitJob(id, token, kind, input, ['status', 'check', 'diff'].includes(kind) ? undefined : setJob, original ? pendingGit(id) ?? undefined : undefined);
      if (result.result && 'snapshot' in result.result) { setStatus(result.result); setBinding(result.result.binding); }
      if (result.result && 'diff' in result.result) setDiff(result.result.diff);
      if (!['status', 'check', 'diff'].includes(kind)) {
        const read = await runGitJob(id, token, 'status', {}); if (read.result && 'snapshot' in read.result) { setStatus(read.result); setBinding(read.result.binding); }
        setEditing(false);
        if (kind === 'push') { setCommitMessage(''); setFiles([]); setAllFiles(true); }
      }
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function reconcile() {
    if (!job) return;
    setBusy(true); setError('');
    try {
      const result = await projectRequest<GitHubJob>(`/${id}/github/jobs/${job.id}/reconcile`, token, 'POST', {}); setJob(result);
      if (result.state === 'completed') { clearGit(id); const read = await runGitJob(id, token, 'status', {}); if (read.result && 'snapshot' in read.result) { setStatus(read.result); setBinding(read.result.binding); } }
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function pull() {
    if (!status || busy) return;
    setBusy(true); setError('');
    try {
      await pullProject(id, token, status, setJob);
      const read = await runGitJob(id, token, 'status', {}); if (read.result && 'snapshot' in read.result) setStatus(read.result);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  const connection = connections.find((v) => v.id === binding?.connectionId);
  const retained = pendingGit(id), pullRequest = pendingPull(id), unresolved = job?.state === 'unknown' || !!retained || !!pullRequest;
  return <section className="project-github" aria-label="Project GitHub">
    <header><h2>GitHub</h2><div className="github-actions"><button type="button" disabled={busy || loading} onClick={() => { setDiff(undefined); void update('check'); }}>Refresh</button>
      {kinds.includes('pull') && binding && <button type="button" disabled={busy || loading || !status || editing || !!commitMessage.trim() || (!pullRequest && (unresolved || !!status.changes.length || !['behind', 'up_to_date'].includes(status.state)))} onClick={() => void pull()}>{pullRequest ? 'Resume original pull' : 'Pull'}</button>}
    </div></header>
    {loading && <p role="status">Loading GitHub status…</p>}
    {binding ? <dl className="github-summary">
      <div><dt>Repository</dt><dd><a href={binding.repository.url} target="_blank" rel="noreferrer">{binding.repository.fullName}</a></dd></div>
      <div><dt>Connection</dt><dd>{connection?.name ?? 'Connection unavailable'} · {connection?.lastTest?.userId === binding.userId && connection.lastTest.login ? '@' + connection.lastTest.login : 'Account #' + binding.userId}</dd></div>
      <div><dt>Branch</dt><dd>{binding.branch}</dd></div><div><dt>Commit author</dt><dd>{binding.author.name} &lt;{binding.author.email}&gt;</dd></div>
      <div><dt>Local commit</dt><dd>{status?.head?.slice(0, 12) ?? 'No local commit'}</dd></div><div><dt>Remote commit</dt><dd>{status?.remoteHead?.slice(0, 12) ?? 'Unknown / no branch'}</dd></div>
      <div><dt>Synchronization</dt><dd>{labels[status?.state ?? 'unknown']} · {status?.ahead ?? 0} ahead · {status?.behind ?? 0} behind</dd></div>
      <div><dt>Last remote check</dt><dd>{status?.checkedAt ? new Date(status.checkedAt).toLocaleString() + (status.fresh ? '' : ' · Cached') : 'Not checked'}</dd></div>
    </dl> : !loading && <p>No GitHub repository connected. Your sources remain local.</p>}
    {binding && <p className="github-hint">{binding.repository.archived ? 'Archived repository. Push is unavailable.' : 'Token contents permissions and branch rules are checked again for each transfer.'}</p>}
    {!editing && <button type="button" disabled={busy || loading || unresolved} onClick={() => setEditing(true)}>{binding ? 'Edit connection or author' : 'Connect repository'}</button>}
    {editing && <BindingForm key={binding?.revision ?? 0} binding={binding} busy={busy} cancel={() => setEditing(false)} submit={(kind, input) => void update(kind, input)} />}
    {status && <section aria-label="Saved source changes"><h3>Saved source changes ({status.changes.length})</h3><p className="github-hint">Unsaved editor drafts are excluded.</p>
      {kinds.includes('push') && <label><input type="checkbox" checked={allFiles} disabled={busy} onChange={(e) => { setAllFiles(e.target.checked); setFiles([]); }} /> All saved changes</label>}
      {status.changes.length ? <ul className="github-files">{status.changes.map((file) => <li key={file.path}>{kinds.includes('push') && !allFiles && <input type="checkbox" aria-label={'Include ' + file.path} disabled={busy} checked={files.includes(file.path)} onChange={(e) => setFiles((old) => e.target.checked ? [...old, file.path] : old.filter((v) => v !== file.path))} />}<span>{file.status}</span><button type="button" disabled={busy} onClick={() => void update('diff', { path: file.path, snapshot: status.snapshot })}>{file.path}</button></li>)}</ul> : <p>No saved source changes.</p>}
      {diff && <div className="github-diff"><h4>{diff.path}</h4><pre>{diff.text || 'No text diff available.'}</pre>{diff.truncated && <p>Preview limited to 128 KiB.</p>}</div>}
    </section>}
    {binding && status && kinds.includes('push') && <form className="github-binding" onSubmit={(e) => { e.preventDefault(); if (commitMessage.trim()) void update('push', { bindingRevision: binding.revision, snapshot: status.snapshot, commitMessage, ...(!allFiles ? { files: files.filter((path) => status.changes.some((v) => v.path === path)) } : {}) }); }}>
      <div className="project-field"><label htmlFor="github-commit-message">Commit description</label><textarea id="github-commit-message" required maxLength={4000} rows={3} disabled={busy} value={commitMessage} onChange={(e) => setCommitMessage(e.target.value)} /></div>
      <p className="github-hint">Commit selected saved changes, then push pending local commits. Existing commits keep their descriptions. No force push. Editor drafts are kept.</p><button type="submit" disabled={busy || loading || unresolved || !commitMessage.trim() || binding.repository.archived}>Commit &amp; Push</button>
    </form>}
    {job && <section className="github-job" aria-label="Last GitHub operation"><h3>Last operation</h3><p role="status">{job.kind} · {job.state} · {job.phase}</p><p>Request: {job.id}</p>{job.error && <p role="alert">{job.error}</p>}
      {job.state === 'unknown' && <button type="button" disabled={busy} onClick={() => void reconcile()}>Reconcile original operation</button>}
      {job.result && 'pushed' in job.result && <p>{job.result.pushed ? 'Push confirmed' : job.result.nothingToPush ? 'Nothing to push' : job.result.notPublished ? 'No commit or push was published. Review and retry explicitly.' : 'Local commit retained. Review the current state, then push explicitly.'}{job.result.commit ? ' · ' + job.result.commit.slice(0, 12) : ''}</p>}
      {job.result && 'pulled' in job.result && job.kind === 'pull' && <p>{job.result.pulled ? 'Pull confirmed' : 'No source update applied.'}</p>}
    </section>}
    {retained && job?.state !== 'unknown' && <button type="button" disabled={busy} onClick={() => void update(retained.kind, retained.input, true)}>Retry original operation</button>}
    {pullRequest && !pullRequest.apply && !retained && <button type="button" disabled={busy} onClick={() => { clearPull(id); setError('Prepared pull cancelled. Current sources were preserved.'); }}>Cancel prepared pull</button>}
    {!kinds.length && !loading && <p role="status">Git host support is unavailable.</p>}
    {busy && <p role="status">Git operation in progress…</p>}{error && <p role="alert">{error}</p>}
  </section>;
}

function BindingForm({ binding, busy, cancel, submit }: { binding: GitHubProjectBinding | null; busy: boolean; cancel: () => void; submit: (kind: string, input: Record<string, unknown>) => void }) {
  const [account, setAccount] = useState<GitHubAccount | null>(null), [choice, setChoice] = useState<RepositoryChoice | null>(null), [accountBusy, setAccountBusy] = useState(false);
  const [mode, setMode] = useState('existing'), [repositoryName, setRepositoryName] = useState(''), [owner, setOwner] = useState('');
  const [name, setName] = useState(binding?.author.name ?? ''), [email, setEmail] = useState(binding?.author.email ?? '');
  return <form className="github-binding" onSubmit={(e) => { e.preventDefault(); if (!account || busy || accountBusy) return;
    const base = { connectionId: account.connectionId, tokenRevision: account.tokenRevision, userId: account.userId };
    if (mode === 'new') submit('create_repository', { ...base, repositoryName, private: true, ...(owner.trim() ? { owner: owner.trim() } : {}) });
    else if (choice) submit('bind', { ...base, expectedRevision: binding?.revision ?? null, repository: { id: choice.repository.id, owner: choice.repository.owner, name: choice.repository.name }, branch: choice.branch, author: { name: name.trim() || account.login, email: email.trim() || `${account.userId}+${account.login}@users.noreply.github.com` } });
  }}><fieldset className="project-fields" disabled={busy}>
    <ConnectionSelect value={account} busyChanged={setAccountBusy} changed={(value) => { setAccount(value); setChoice(null); }} />
    {!binding && <div className="project-field"><label htmlFor="github-bind-mode">Repository source</label><select id="github-bind-mode" value={mode} onChange={(e) => setMode(e.target.value)}><option value="existing">Use existing repository</option><option value="new">Create private repository</option></select></div>}
    {account && mode === 'existing' && <RepositorySelect key={account.connectionId + ':' + account.tokenRevision} account={account} changed={setChoice} />}
    {account && mode === 'new' && <><div className="project-field"><label htmlFor="github-bind-name">Repository name</label><input id="github-bind-name" required pattern="[A-Za-z0-9_.-]{1,100}" maxLength={100} value={repositoryName} onChange={(e) => setRepositoryName(e.target.value)} /></div><div className="project-field"><label htmlFor="github-bind-owner">Repository owner</label><input id="github-bind-owner" maxLength={39} placeholder={account.login} value={owner} onChange={(e) => setOwner(e.target.value)} /></div></>}
    {mode === 'existing' && <><div className="project-field"><label htmlFor="github-author-name">Commit author name</label><input id="github-author-name" maxLength={120} placeholder={account?.login} value={name} onChange={(e) => setName(e.target.value)} /></div><div className="project-field"><label htmlFor="github-author-email">Commit author email</label><input id="github-author-email" type="email" maxLength={254} placeholder={account ? `${account.userId}+${account.login}@users.noreply.github.com` : ''} value={email} onChange={(e) => setEmail(e.target.value)} /></div><p>Empty author fields use the verified GitHub noreply identity. Existing nonempty repositories require compatible local history. Other branches require a new import.</p></>}
    <div className="github-actions"><button type="button" onClick={cancel}>Cancel</button><button type="submit" disabled={!account || accountBusy || (mode === 'existing' && !choice) || (mode === 'new' && !repositoryName)}>Save repository connection</button></div>
  </fieldset></form>;
}
