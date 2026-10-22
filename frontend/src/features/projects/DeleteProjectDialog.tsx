import { useEffect, useRef, useState } from 'react';
import type { Project, ProjectDeleted } from '../../../../shared/projects';
import { projectRequest } from './api';

export function DeleteProjectDialog({ project, token, close, deleted, busyChanged, changed }: {
  project: Project; token: string; close: () => void; deleted: (id: string) => void;
  busyChanged: (busy: boolean) => void; changed: () => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => {
    const element = dialog.current!, opener = document.activeElement;
    element.showModal(); cancel.current?.focus();
    return () => { element.close(); if (opener instanceof HTMLElement && opener.isConnected) opener.focus(); };
  }, []);
  useEffect(() => { busyChanged(busy); return () => busyChanged(false); }, [busy, busyChanged]);

  async function remove() {
    if (busy) return;
    setBusy(true); setError('');
    try {
      await projectRequest<ProjectDeleted>('/' + project.id, token, 'DELETE', { revision: project.revision, confirm: true });
      deleted(project.id);
    } catch (cause) {
      setError((cause as Error).message || 'Deletion could not be confirmed. Retry this deletion.');
      await changed();
    } finally { setBusy(false); }
  }
  return <dialog ref={dialog} className="project-dialog project-delete-dialog" aria-labelledby="delete-project-title"
    aria-describedby="delete-project-description" onCancel={(event) => { event.preventDefault(); if (!busy) close(); }}>
    <header className="project-dialog-header"><h2 id="delete-project-title">Delete project?</h2></header>
    <div className="project-delete-description" id="delete-project-description">
      <p><strong>{project.name}</strong></p>
      <p>Permanently deletes all project files, sessions and build data. This cannot be undone.</p>
      {project.vmId && <p>The assigned VM and files already deployed to it are kept.</p>}
    </div>
    {error && <p className="project-dialog-error" role="alert">{error}</p>}
    {busy && <p className="project-dialog-status" role="status">Deleting project…</p>}
    <div className="project-actions">
      <button type="button" ref={cancel} disabled={busy} onClick={close}>Cancel</button>
      <button type="button" className="project-danger" disabled={busy} onClick={() => void remove()}>{busy ? 'Deleting…' : 'Delete project'}</button>
    </div>
  </dialog>;
}
