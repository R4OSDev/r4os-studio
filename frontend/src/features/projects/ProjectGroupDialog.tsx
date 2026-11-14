import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { createPortal } from 'react-dom';
import type { ProjectGroup } from '../../../../shared/projects';
import { projectRequestId } from './api';

export function ProjectGroupDialog({ group, change, close, fallbackFocus }: {
  group: ProjectGroup | null; change: (path: string, method: string, body: unknown) => Promise<void>;
  close: () => void; fallbackFocus: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const restore = useRef(fallbackFocus);
  const [id] = useState(() => group?.id ?? projectRequestId());
  const [name, setName] = useState(group?.name ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const title = group ? 'Edit group' : 'New Group';

  useEffect(() => {
    const element = dialog.current!, opener = document.activeElement;
    const fallback = restore.current;
    element.showModal();
    const input = element.querySelector('input');
    input?.focus();
    input?.select();
    return () => {
      element.close();
      if (opener instanceof HTMLElement && opener.isConnected && !opener.closest('[inert]')) opener.focus();
      else fallback();
    };
  }, []);

  async function submit(method: 'POST' | 'PATCH' | 'DELETE') {
    if (busy) return;
    const body = method === 'DELETE' ? { revision: group?.revision }
      : group ? { name: name.trim(), revision: group.revision } : { name: name.trim() };
    setBusy(true);
    setError('');
    try {
      await change('/groups/' + id, method, body);
      close();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The group could not be saved.');
    } finally { setBusy(false); }
  }

  function save(event: FormEvent) {
    event.preventDefault();
    if (name.trim()) void submit(group ? 'PATCH' : 'POST');
  }

  return createPortal(<dialog className="project-dialog project-group-dialog" ref={dialog} aria-labelledby="project-group-title"
    onCancel={event => { event.preventDefault(); if (!busy) close(); }}
    onKeyDown={event => { if (event.key === 'Escape') event.stopPropagation(); }}>
    <form onSubmit={save} aria-busy={busy}>
      <header className="project-dialog-header"><h2 id="project-group-title">{title}</h2></header>
      <fieldset className="project-fields" disabled={busy}>
        <label className="project-field"><span>Name</span>
          <input value={name} required maxLength={120} onChange={event => setName(event.target.value)} />
        </label>
      </fieldset>
      {error && <p className="project-dialog-error" role="alert">{error}</p>}
      <footer className="project-actions">
        {group && <button type="button" className="project-danger" disabled={busy} onClick={() => void submit('DELETE')}>Delete group</button>}
        <button type="button" disabled={busy} onClick={close}>Cancel</button>
        <button type="submit" className="project-primary" disabled={busy || !name.trim()}>{group ? 'Rename' : 'Create group'}</button>
      </footer>
    </form>
  </dialog>, document.body);
}
