import { useEffect, useRef } from 'react';
import type { GitHubProjectStatus } from '../../../../shared/project-github';
import { editorRegistry } from '../project-editor/registry';

export function UpdateProjectDialog({ id, name, status, busy, error, update, ignore }: {
  id: string; name: string; status: GitHubProjectStatus; busy: boolean; error?: string; update: () => void; ignore: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const reason = status.state !== 'behind' ? 'Histories have diverged. Resolve them before updating.' : status.changes.length ? 'Saved local changes must be committed or preserved before updating.' : editorRegistry.hasUnsavedFor(id) ? 'Save or close this project’s editor drafts before updating.' : '';
  useEffect(() => {
    const element = dialog.current!, opener = document.activeElement; element.showModal();
    element.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus();
    return () => { element.close(); if (opener instanceof HTMLElement && opener.isConnected) opener.focus(); };
  }, []);
  return <dialog ref={dialog} className="project-dialog project-delete-dialog" aria-labelledby="github-update-title" aria-describedby="github-update-description" onCancel={(e) => e.preventDefault()}>
    <header className="project-dialog-header"><h2 id="github-update-title">GitHub update available</h2></header>
    <div id="github-update-description" className="project-delete-description">
      <p><strong>{name}</strong> has {status.behind} remote commit{status.behind === 1 ? '' : 's'} missing locally.</p>
      <p>{status.binding?.repository.fullName} · {status.binding?.branch}</p>
      <p>Update applies the checked fast-forward. Ignore keeps your local sources for this opening; Studio checks again when you reopen the project.</p>
      {reason && <p role="status">{reason}</p>}{error && <p className="project-error" role="alert">{error}</p>}{busy && <p role="status">Updating from the original pull request…</p>}
    </div>
    <footer className="project-actions"><button type="button" className="project-primary" disabled={busy || !!reason} onClick={update}>Update</button><button type="button" disabled={busy} onClick={ignore}>Ignore</button></footer>
  </dialog>;
}
