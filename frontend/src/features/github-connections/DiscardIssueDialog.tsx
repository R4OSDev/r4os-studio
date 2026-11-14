import { useEffect, useRef, useState } from 'react';
import type { GitHubIssue, GitHubIssueOutcome, GitHubIssuePage } from '../../../../shared/project-github-issues';
import { projectRequest, projectRequestId, ProjectRequestError } from '../projects/api';

type Receipt = GitHubIssueOutcome & { text?: string };

export function DiscardIssueDialog({ issue, scope, token, close, changed, busyChanged }: {
  issue: GitHubIssue; scope: GitHubIssuePage['scope']; token: string; close: () => void;
  changed: (completed: boolean) => void; busyChanged: (busy: boolean) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const reason = useRef<HTMLTextAreaElement>(null);
  const path = `/${scope.projectId}/github/issues/${issue.number}/discard`;
  const key = 'studio.github.discard.' + [scope.projectId, scope.repositoryId, issue.number].join('.');
  const [pending, setPending] = useState<{ requestId: string; text: string } | null>(() => {
    try { return JSON.parse(sessionStorage.getItem(key) ?? 'null'); } catch { return null; }
  });
  const [text, setText] = useState(pending?.text ?? '');
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [loading, setLoading] = useState(!!issue.id), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const closed = receipt?.state === 'complete';
  const original = !!pending || !!receipt;
  const scopeRevision = { bindingRevision: scope.bindingRevision, credentialRevision: scope.credentialRevision };
  const query = '?' + new URLSearchParams({bindingRevision:String(scope.bindingRevision),credentialRevision:String(scope.credentialRevision),
    ...(issue.id?{issueId:issue.id}:{})});

  useEffect(() => {
    const element = dialog.current!, opener = document.activeElement;
    element.showModal(); reason.current?.focus();
    return () => {
      element.close();
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
      else document.querySelector<HTMLButtonElement>('.project-issues header button')?.focus();
    };
  }, []);
  useEffect(() => { busyChanged(busy); return () => busyChanged(false); }, [busy, busyChanged]);
  useEffect(() => {
    const controller = new AbortController();
    // The local draft points at an original operation. Its status read never
    // posts a comment or sends a close request.
    if (!issue.id) return;
    void projectRequest<{ receipt: Receipt | null }>(path + query, '', 'GET', undefined, controller.signal)
      .then(({ receipt: observed }) => {
        if (controller.signal.aborted || !observed) return;
        setReceipt(observed);
        if (observed.text) setText(observed.text);
      }).catch((cause: Error) => { if (!controller.signal.aborted) setError(cause.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [path, query, issue.id]);

  async function submit() {
    if (busy || loading || closed) return;
    const value = text.trim();
    if (!value || new TextEncoder().encode(value).byteLength > 4000) { setError('Enter a reason within 4,000 bytes.'); return; }
    setBusy(true); setError('');
    const original = { requestId: receipt?.requestId ?? pending?.requestId ?? projectRequestId(), text: value };
    try {
      sessionStorage.setItem(key, JSON.stringify(original)); setPending(original);
      const { receipt: result } = await projectRequest<{ receipt: Receipt }>(path, token, 'POST', {
        ...original, ...scopeRevision, ...((issue.id??issue.roadmap?.issueId) ? { issueId: issue.id??issue.roadmap?.issueId } : {}),
      });
      if (!result) throw new Error('The original issue action is unconfirmed.');
      setReceipt(result);
      if (result.state === 'complete') sessionStorage.removeItem(key);
      if (result.syncError) setError(result.syncError);
      if (result.closedAt) changed(result.state === 'complete');
    } catch (cause) {
      if (!receipt && cause instanceof ProjectRequestError && [400,401,403,404,422,429].includes(cause.status)) {
        sessionStorage.removeItem(key); setPending(null);
      }
      setError((cause as Error).message);
    } finally { setBusy(false); }
  }

  return <dialog ref={dialog} className="project-dialog github-discard-dialog" aria-labelledby="issue-discard-title"
    onCancel={event => { event.preventDefault(); if (!busy) close(); }}>
    <header className="project-dialog-header"><h2 id="issue-discard-title">Discard GitHub issue?</h2></header>
    <form onSubmit={event => { event.preventDefault(); void submit(); }}>
      <p><strong>#{issue.number} {issue.title}</strong></p>
      <p>Studio posts your reason on GitHub and closes the issue as Not planned.{issue.roadmap && ' The linked Roadmap subversion will also be marked Discarded.'}</p>
      <label htmlFor="github-discard-reason">Reason</label>
      <textarea ref={reason} id="github-discard-reason" required rows={4} maxLength={4000} value={text} readOnly={original} disabled={busy || loading}
        onChange={event => setText(event.target.value)} />
      {receipt?.comment && <p><a href={receipt.comment.url} target="_blank" rel="noreferrer">View GitHub comment</a>{receipt.closedAt && ' · Closed on GitHub'}</p>}
      {error && <p className="project-dialog-error" role="alert">{error}</p>}
      {(busy || loading) && <p role="status">{busy ? 'Checking the GitHub action…' : 'Loading the original action…'}</p>}
      <footer className="project-actions">
        <button type="button" disabled={busy} onClick={close}>{closed ? 'Close' : 'Cancel'}</button>
        {!closed && <button className="project-danger" type="submit" disabled={!text.trim() || loading || busy}>{original ? 'Resume discard' : 'Discard'}</button>}
      </footer>
    </form>
  </dialog>;
}
