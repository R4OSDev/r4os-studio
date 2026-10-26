import { useCallback, useEffect, useRef, useState } from 'react';
import type { GitHubAccount, GitHubBranchPage, GitHubRepository, GitHubRepositoryPage } from '../../../../shared/project-github';
import { loadConnections, request } from './api';

export interface RepositoryChoice { repository: GitHubRepository; branch: string }
// Mount with the account identity as key so account changes discard old choices.
export function RepositorySelect({ account, changed, disabled = false }: {
  account: GitHubAccount; changed: (value: RepositoryChoice | null) => void; disabled?: boolean;
}) {
  const [repositories, setRepositories] = useState<GitHubRepository[]>([]), [repoPage, setRepoPage] = useState(0), [more, setMore] = useState(false);
  const [repository, setRepository] = useState<GitHubRepository | null>(null), [branches, setBranches] = useState<string[]>([]), [branch, setBranch] = useState('');
  const [branchPage, setBranchPage] = useState(0), [moreBranches, setMoreBranches] = useState(false), [filter, setFilter] = useState('');
  const [csrf, setCsrf] = useState(''), [busy, setBusy] = useState(true), [error, setError] = useState('');
  const generation = useRef(0);
  const invalidate = useCallback(() => { generation.current++; }, []);
  useEffect(() => {
    let active = true;
    void loadConnections().then(async (root) => {
      const result = await request<GitHubRepositoryPage>('POST', '/' + account.connectionId + '/repositories', { tokenRevision: account.tokenRevision, page: 1 }, root.csrfToken);
      if (result.account.userId !== account.userId) throw new Error('GitHub account changed. Select the connection again.');
      if (active) { setCsrf(root.csrfToken); setRepositories(result.repositories); setRepoPage(1); setMore(result.hasMore); }
    }).catch((e: Error) => { if (active) setError(e.message); }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; invalidate(); };
  }, [account.connectionId, account.tokenRevision, account.userId, invalidate]);
  async function moreRepositories() {
    setBusy(true); setError(''); const current = ++generation.current;
    try {
      const result = await request<GitHubRepositoryPage>('POST', '/' + account.connectionId + '/repositories', { tokenRevision: account.tokenRevision, page: repoPage + 1 }, csrf);
      if (generation.current === current) { setRepositories((old) => [...old, ...result.repositories.filter((v) => !old.some((x) => x.id === v.id))]); setRepoPage(result.page); setMore(result.hasMore); }
    } catch (e) { if (generation.current === current) setError((e as Error).message); }
    finally { if (generation.current === current) setBusy(false); }
  }
  async function choose(id: string, next = false) {
    const selected = next ? repository : repositories.find((v) => String(v.id) === id) ?? null;
    const current = ++generation.current; changed(null); setError('');
    if (!next) { setRepository(selected); setBranches([]); setBranch(''); setBranchPage(0); setMoreBranches(false); }
    if (!selected) return;
    setBusy(true);
    try {
      const result = await request<GitHubBranchPage>('POST', '/' + account.connectionId + '/branches', { tokenRevision: account.tokenRevision, owner: selected.owner, name: selected.name, repositoryId: selected.id, page: next ? branchPage + 1 : 1 }, csrf);
      if (generation.current !== current) return;
      const choices = next ? [...branches, ...result.branches.map((v) => v.name)] : result.branches.map((v) => v.name);
      const selectedBranch = next ? branch : (choices.includes(selected.defaultBranch ?? '') ? selected.defaultBranch! : choices[0] ?? '');
      setBranches([...new Set(choices)]); setBranchPage(result.page); setMoreBranches(result.hasMore); setBranch(selectedBranch);
      changed(selectedBranch ? { repository: result.repository, branch: selectedBranch } : null);
      if (!choices.length) setError('This repository has no branch to import.');
    } catch (e) { if (generation.current === current) setError((e as Error).message); }
    finally { if (generation.current === current) setBusy(false); }
  }
  return <fieldset className="project-fields" disabled={disabled || busy || !csrf}>
    <div className="project-field"><label htmlFor="github-repo-filter">Filter loaded repositories</label><input id="github-repo-filter" value={filter} maxLength={100} onChange={(e) => setFilter(e.target.value)} /></div>
    <div className="project-field"><label htmlFor="github-repository">Repository</label><select id="github-repository" value={repository?.id ?? ''} onChange={(e) => void choose(e.target.value)}>
      <option value="">Select a repository</option>{repositories.filter((v) => v.id === repository?.id || v.fullName.toLowerCase().includes(filter.toLowerCase())).map((v) => <option key={v.id} value={v.id}>{v.fullName}{v.private ? ' · Private' : ''}{v.archived ? ' · Archived' : ''}</option>)}
    </select></div>
    {more && <button type="button" onClick={() => void moreRepositories()}>Load more repositories</button>}
    {repository && <div className="project-field"><label htmlFor="github-branch">Branch</label><select id="github-branch" value={branch} onChange={(e) => { setBranch(e.target.value); changed({ repository, branch: e.target.value }); }}>
      {branches.map((v) => <option key={v} value={v}>{v}</option>)}
    </select>{moreBranches && <button type="button" onClick={() => void choose(String(repository.id), true)}>Load more branches</button>}</div>}
    {busy && <p role="status">Loading GitHub repositories…</p>}{error && <p role="alert">{error}</p>}
  </fieldset>;
}
