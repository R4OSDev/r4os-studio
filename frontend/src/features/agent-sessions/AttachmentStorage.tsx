import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { AttachmentListing } from '../../../../shared/agent-inputs';
import type { useAttachments } from './useAttachments';

export function AttachmentStorage({ control, disabled }: { control: ReturnType<typeof useAttachments>; disabled: boolean }) {
  const [open, setOpen] = useState(false);
  return <><button type="button" className="agent-stored-uploads" disabled={disabled} onClick={() => setOpen(true)}>Stored uploads</button>
    {open && <StorageDialog control={control} close={() => setOpen(false)} />}</>;
}
function StorageDialog({ control, close }: { control: ReturnType<typeof useAttachments>; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null), [listing, setListing] = useState<AttachmentListing | null>(null);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  useEffect(() => {
    dialog.current?.showModal(); let alive = true;
    void control.listStored().then(value => { if (alive) setListing(value); }).catch((failure: Error) => { if (alive) setError(failure.message); });
    return () => { alive = false; };
    // The keyed session owns this dialog. Refresh uses the latest control below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  async function remove(id: string) {
    setBusy(true); setError('');
    try { await control.removeStored(id); setListing(await control.listStored()); }
    catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  }
  return createPortal(<dialog className="project-dialog agent-goal-dialog agent-storage-dialog" ref={dialog} aria-label="Stored uploads" onCancel={close}>
    <header className="project-dialog-header"><h2>Stored uploads</h2></header>
    <p>Remove unused uploads to free space. Sent files stay available in the conversation.</p>
    {listing ? <><p>Session: {Math.ceil(listing.usage.sessionBytes / 1048576)} / {listing.limits.maxSessionBytes / 1048576} MiB · {listing.usage.sessionFiles} {listing.usage.sessionFiles === 1 ? 'file' : 'files'}</p>
      <ul className="agent-storage-files">{listing.attachments.map(file => <li key={file.id}>
        <span title={file.name}>{file.name}<small>{file.referenced ? 'Sent' : 'Unused'} · {Math.ceil(file.size / 1024)} KiB</small></span>
        {!file.referenced && <button type="button" disabled={busy} onClick={() => void remove(file.id)}>Remove unused</button>}
      </li>)}
      {listing.cleanupPending?.map(file => <li key={file.id}><span>{file.name}<small>Cleanup pending</small></span><button type="button" disabled={busy} onClick={() => void remove(file.id)}>Retry cleanup</button></li>)}
      {!listing.attachments.length && !listing.cleanupPending?.length && <li>No stored uploads.</li>}</ul></> : <p>Loading uploads…</p>}
    {error && <p role="alert">{error}</p>}
    <footer className="project-actions"><button type="button" onClick={close}>Close</button></footer>
  </dialog>, document.body);
}
