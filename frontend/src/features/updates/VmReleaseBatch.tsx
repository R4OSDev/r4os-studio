import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { VmImage, VmReleaseBatchView } from '../../../../shared/virtual-machines';
import { vmRequest, vmRequestId, VmRequestError } from '../virtual-machines/api';

interface Choice { id: string; version: string; sha256?: string }
interface Consent { previewDigest: string; confirm: true; stopRunning: true; resetSystem: true; forceStopRunning?: true }
interface Ticket { requestId: string; imageId: string; imageSha256: string; intent?: 'confirm' | 'resume'; consent?: Consent }
interface Inventory { batches: VmReleaseBatchView[]; images: VmImage[]; available: boolean; csrfToken: string }
interface Driver { preview: () => Promise<void>; submit: (resume?: boolean) => Promise<void>; read: (inventory?: boolean) => Promise<void>; cancel: () => void }
const storageKey = 'studio.vm-release-batch';
function saved(): Ticket | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(storageKey) ?? 'null') as Ticket | null;
    return value && /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(value.requestId)
      && typeof value.imageId === 'string' && /^[a-f0-9]{64}$/.test(value.imageSha256)
      && (!value.intent || ['confirm', 'resume'].includes(value.intent) && value.consent?.confirm === true
        && value.consent.stopRunning === true && value.consent.resetSystem === true
        && (value.consent.forceStopRunning === undefined || value.consent.forceStopRunning === true)
        && /^[a-f0-9]{64}$/.test(value.consent.previewDigest)) ? value : null;
  } catch { return null; }
}
function preserve(ticket: Ticket | null) {
  if (ticket) sessionStorage.setItem(storageKey, JSON.stringify(ticket)); else sessionStorage.removeItem(storageKey);
}
function useReleaseBatch(choice?: Choice) {
  const [inventory, setInventory] = useState<Inventory | null>(null), [batch, setBatch] = useState<VmReleaseBatchView | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [review, setReview] = useState(false), [uncertain, setUncertain] = useState(false);
  const driver = useRef<Driver | null>(null), selected = useRef(choice);
  useLayoutEffect(() => { selected.current = choice; }, [choice]);
  useEffect(() => {
    let live = true, writing = false, reading = false, generation = 0, timer = 0;
    let data: Inventory | null = null, current: VmReleaseBatchView | null = null, ticket = saved();
    let controller: AbortController | undefined;
    const updateTicket = (value: Ticket | null) => { preserve(value); ticket = value; if (live) setUncertain(!!value?.intent); };
    function accept(next: VmReleaseBatchView) {
      if (!ticket || next.requestId !== ticket.requestId || next.imageId !== ticket.imageId || next.imageSha256 !== ticket.imageSha256)
        throw new Error('The batch response belongs to another original request.');
      if (current && next.updatedAt < current.updatedAt) return;
      if (next.counts.updated !== current?.counts.updated && next.counts.updated > 0) window.dispatchEvent(new Event('studio:vms-changed'));
      current = next; setBatch(next);
      if (ticket.intent && (ticket.intent === 'confirm' ? next.state !== 'preview' : next.state !== 'paused'))
        updateTicket({ requestId: ticket.requestId, imageId: ticket.imageId, imageSha256: ticket.imageSha256 });
    }
    function schedule() {
      window.clearTimeout(timer);
      if (live && current?.state === 'running') timer = window.setTimeout(() => { if (document.hidden) schedule(); else void read(); }, 2000);
    }
    async function loadInventory() {
      const next = await vmRequest<Inventory>('/release-batches');
      if (!live) return; data = next; setInventory(next);
    }
    async function read(refreshInventory = false) {
      if (!live || reading || writing) return;
      reading = true; const epoch = generation;
      controller = new AbortController();
      try {
        if (!data || !data.available || refreshInventory) await loadInventory();
        if (!ticket && data) {
          const original = data.batches.find(value => value.state !== 'preview');
          if (original) updateTicket({ requestId: original.requestId, imageId: original.imageId, imageSha256: original.imageSha256 });
        }
        if (ticket) {
          const response = await vmRequest<{ batch: VmReleaseBatchView }>('/release-batches/' + ticket.requestId, '', 'GET', undefined, controller.signal);
          if (live && epoch === generation) { accept(response.batch); setError(''); }
        }
      } catch (cause) {
        if (live && epoch === generation && !controller.signal.aborted) {
          setError((cause as Error).message);
          if (cause instanceof VmRequestError && cause.status === 403) { data = null; setInventory(null); }
        }
      } finally { reading = false; if (live) schedule(); }
    }
    async function mutate(work: () => Promise<void>) {
      if (!live || writing) return;
      writing = true; generation++; controller?.abort(); window.clearTimeout(timer); setBusy(true); setError('');
      try { await work(); }
      catch (cause) { if (live) setError((cause as Error).message); }
      finally { writing = false; if (live) { setBusy(false); schedule(); } }
    }
    const actions: Driver = {
      read,
      async preview() {
        if (ticket?.intent || current?.state === 'running') return;
        await mutate(async () => {
          if (!data) await loadInventory();
          const option = selected.current, image = data?.images.find(value => value.id === option?.id && value.sha256 === option.sha256);
          if (!data?.available || !image) throw new Error('The selected local Full release and VM batch support are required.');
          const original: Ticket = { requestId: vmRequestId(), imageId: image.id, imageSha256: image.sha256 };
          updateTicket(original); current = null; setBatch(null);
          try {
            const result = await vmRequest<{ batch: VmReleaseBatchView }>('/release-batches/preview', data.csrfToken, 'POST', original);
            if (live && ticket?.requestId === original.requestId) { accept(result.batch); setReview(true); }
          } catch (cause) {
            // A preview has no VM effect. Recover its exact saved snapshot by GET.
            try {
              const result = await vmRequest<{ batch: VmReleaseBatchView }>('/release-batches/' + original.requestId);
              if (live) { accept(result.batch); setReview(true); }
            } catch { throw cause; }
          }
        });
      },
      async submit(resume = false) {
        await mutate(async () => {
          if (!ticket || !current || !data) return;
          if (!ticket.intent) {
            if (!resume && (selected.current?.id !== current.imageId || selected.current.sha256 !== current.imageSha256))
              throw new Error('The selected release changed. Cancel and prepare a new preview.');
            const consent: Consent = { previewDigest: current.previewDigest, confirm: true, stopRunning: true, resetSystem: true,
              ...(current.stopMode === 'force' ? { forceStopRunning: true as const } : {}) };
            updateTicket({ ...ticket, intent: resume ? 'resume' : 'confirm', consent });
          }
          const original = ticket; setReview(false);
          let rejected: unknown;
          try {
            const response = await vmRequest<{ batch: VmReleaseBatchView }>(`/release-batches/${original.requestId}/${original.intent}`, data.csrfToken, 'POST', original.consent);
            if (live && ticket?.requestId === original.requestId) accept(response.batch);
          } catch (cause) { rejected = cause; }
          if (!live) return;
          try {
            const response = await vmRequest<{ batch: VmReleaseBatchView }>('/release-batches/' + original.requestId);
            if (!live) return; accept(response.batch);
            if (rejected instanceof VmRequestError && [400, 409].includes(rejected.status) && response.batch.state === 'preview') {
              updateTicket({ requestId: original.requestId, imageId: original.imageId, imageSha256: original.imageSha256 });
              throw rejected;
            }
          } catch (cause) { throw rejected ?? cause; }
          if (rejected && ticket?.intent) throw rejected;
        });
      },
      cancel() {
        if (writing || ticket?.intent) return;
        setReview(false);
        if (current?.state === 'preview') { updateTicket(null); current = null; setBatch(null); }
      },
    };
    driver.current = actions;
    const initial = window.setTimeout(() => { setUncertain(!!ticket?.intent); void read(); }, 0);
    const wake = () => { if (!document.hidden) void read(); };
    window.addEventListener('focus', wake); document.addEventListener('visibilitychange', wake);
    return () => {
      live = false; generation++; controller?.abort(); window.clearTimeout(initial); window.clearTimeout(timer);
      if (driver.current === actions) driver.current = null;
      window.removeEventListener('focus', wake); document.removeEventListener('visibilitychange', wake);
    };
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => void driver.current?.read(true), 0);
    return () => window.clearTimeout(timer);
  }, [choice?.id, choice?.sha256]);
  return { inventory, batch, busy, error, review, uncertain,
    preview: () => driver.current?.preview(), confirm: () => driver.current?.submit(), resume: () => driver.current?.submit(true),
    read: () => driver.current?.read(true), cancel: () => driver.current?.cancel(),
    reopen: () => { if (batch?.state === 'preview' && !uncertain) setReview(true); } };
}

function Targets({ batch, images }: { batch: VmReleaseBatchView; images: VmImage[] }) {
  return <ul className="vm-batch-targets">{batch.targets.map(target => <li key={target.id}>
    <strong>{target.name}</strong><span>{images.find(image => image.id === target.expectedImageId)?.version ?? target.expectedImageId} → {batch.version}</span>
    <span className="vm-batch-state">{target.state.replaceAll('-', ' ')}</span>{target.reason && <small>{target.reason}</small>}
  </li>)}</ul>;
}
export function useVmReleaseBatch(choice?: Choice) { return useReleaseBatch(choice); }
export type VmBatchControl = ReturnType<typeof useVmReleaseBatch>;
export function VmReleaseBatchActions({ choice, disabled, older }: { choice?: Choice; disabled: boolean; older: boolean }) {
  const control = useVmReleaseBatch(choice);
  const ready = control.inventory?.available && control.inventory.images.some(image => image.id === choice?.id && image.sha256 === choice.sha256);
  return <><button type="button" disabled={disabled || !ready || control.busy || control.uncertain || control.batch?.state === 'running'} onClick={() => void control.preview()}>Update VMs</button>
    {control.inventory && !control.inventory.available && <p className="vm-batch-error">VM updates are unavailable. <button type="button" onClick={() => void control.read()}>Refresh VM support</button></p>}
    <VmReleaseBatchStatus control={control} choice={choice} older={older} /></>;
}
export function VmReleaseBatchStatus({ control, choice, older = false }: { control: VmBatchControl; choice?: Choice; older?: boolean }) {
  const { batch, inventory } = control, dialog = useRef<HTMLDialogElement>(null), cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const element = dialog.current, opener = document.activeElement;
    if (!control.review || !element) return;
    element.showModal(); cancel.current?.focus();
    return () => { element.close(); if (opener instanceof HTMLElement && opener.isConnected) opener.focus(); };
  }, [control.review]);
  const stale = !!batch && (choice?.id !== batch.imageId || choice.sha256 !== batch.imageSha256);
  const images = inventory?.images ?? [];
  return <>
    {control.error && <p className="updates-alert vm-batch-error" role="alert">{control.error}</p>}
    {control.uncertain && !batch && <div className="vm-batch-progress" role="status">Original acceptance is unconfirmed. Reloading never repeats an update.
      <button type="button" disabled={control.busy} onClick={() => void control.read()}>Check original batch</button></div>}
    {batch && !control.review && <section className="vm-batch-progress" aria-label="VM release batch" aria-live="polite">
      <h3>VM update · {batch.version}</h3><p>{batch.state === 'preview' ? 'Preview only. No VM update has been accepted.'
        : batch.state === 'complete' && (batch.counts.blocked || batch.counts.failed || batch.counts.unknown) ? 'Batch finished with unresolved targets.' : `Batch ${batch.state}.`}</p>
      <p>{batch.counts.updated} updated · {batch.counts['already-current']} already current · {batch.counts.blocked} blocked · {batch.counts.failed} failed · {batch.counts.unknown} unknown · {batch.counts.pending} pending</p>
      {control.uncertain && <p role="status">Acceptance is unconfirmed. Check the original batch or explicitly retry the same request.</p>}
      <Targets batch={batch} images={images} />
      <div className="updates-actions"><button type="button" disabled={control.busy} onClick={() => void control.read()}>Check original batch</button>
        {control.uncertain ? <button type="button" disabled={control.busy} onClick={() => void control.confirm()}>Retry same request</button>
          : batch.state === 'preview' ? <button type="button" onClick={control.reopen}>Review preview</button>
            : batch.state === 'paused' && batch.counts.pending > 0 ? <button type="button" disabled={control.busy} onClick={() => void control.resume()}>Continue pending VMs</button> : null}</div>
    </section>}
    {control.review && batch && createPortal(<dialog ref={dialog} className="vm-batch-dialog" aria-labelledby="vm-batch-title" onCancel={event => { event.preventDefault(); control.cancel(); }}>
      <h2 id="vm-batch-title">Update VMs to {batch.version}?</h2>
      <p>Target release: <strong>{batch.version}</strong> · {batch.imageId}</p>
      {older && <p>An older release is selected.</p>}
      {batch.stopMode === 'force'
        ? <p>Running VMs will be force-stopped before updating. Unsaved guest changes may be lost.</p>
        : <p>This original preview uses graceful shutdown. Cancel and prepare a new preview to use force stop.</p>}
      <p>All C:/D: files and installed programs on changed VMs will be deleted.</p>
      <p>Exchange, VM settings, project assignments and saved access will be kept. VMs remain stopped. Already current VMs keep their disks.</p>
      <p>{batch.targets.length} VMs in this snapshot. Status is checked again before each update. No new VMs will be added to this batch.</p>
      {!batch.targets.length && <p>No VMs to update.</p>}
      <Targets batch={batch} images={images} />
      {stale && <p role="alert">The selection changed. Cancel and prepare a new preview.</p>}
      <footer><button type="button" ref={cancel} disabled={control.busy} onClick={control.cancel}>Cancel</button>
        <button type="button" className="vm-batch-confirm" disabled={control.busy || stale || !batch.targets.length} onClick={() => void control.confirm()}>{batch.stopMode === 'force' ? 'Force stop and update VMs' : 'Shut down and update VMs'}</button></footer>
    </dialog>, document.body)}
  </>;
}
