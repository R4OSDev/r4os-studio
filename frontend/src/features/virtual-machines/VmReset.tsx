import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { VirtualMachine, VmResetInput, VmResetReceipt } from '../../../../shared/virtual-machines';
import type { VmApi } from './useVms';
import { VmRequestError, vmRequestId } from './api';

function preserved(key: string): VmResetInput | null {
  try {
    const input = JSON.parse(sessionStorage.getItem(key) ?? 'null') as VmResetInput | null;
    return input && ['exchange', 'system'].includes(input.kind) && input.confirm === true
      && /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(input.requestId)
      && typeof input.expectedRevision === 'string' && input.expectedRevision.length <= 64 ? input : null;
  } catch { return null; }
}

/** One reset path for Settings and Exchange; uncertain writes keep their exact original ID. */
export function useVmReset(api: VmApi, vm?: VirtualMachine) {
  const key = 'studio.vm-reset:' + vm?.id, id = vm?.id;
  const [review, setReview] = useState<VmResetInput | null>(null), [pending, setPending] = useState(() => preserved(key));
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [completed, setCompleted] = useState(0);
  const [aborted, setAborted] = useState(false);
  const apiRef = useRef(api), epoch = useRef(0), inflight = useRef(false), mounted = useRef(true);
  useLayoutEffect(() => { apiRef.current = api; }, [api]);
  useLayoutEffect(() => { epoch.current++; }, [api.csrfToken]);
  const unmount=useCallback(()=>{mounted.current=false;epoch.current++;},[]);
  useEffect(() => { mounted.current = true; return unmount; }, [unmount]);
  const perform = useCallback(async (input: VmResetInput, write: boolean, fresh = false) => {
    if (!id || inflight.current) return;
    const generation = epoch.current, current = () => mounted.current && epoch.current === generation;
    inflight.current = true; setBusy(true); setError(''); setAborted(false);
    const original = () => apiRef.current.request<{ receipt: VmResetReceipt }>(`/${id}/reset/requests/${input.requestId}`);
    const accept = async (receipt: VmResetReceipt) => {
      if (!current()) return;
      if (receipt.vmId !== id || receipt.requestId !== input.requestId || receipt.kind !== input.kind || receipt.expectedRevision !== input.expectedRevision)
        throw new Error('The reset receipt belongs to another original request.');
      if (receipt.state !== 'complete') {
        setAborted(receipt.state === 'aborted');
        setError(receipt.state === 'aborted' ? 'The reset did not complete. You may retry this same request.' : 'The original reset is still being prepared. Check its receipt.');
        return;
      }
      if (preserved(key)?.requestId === input.requestId) sessionStorage.removeItem(key);
      setPending(null); setReview(null);
      setNotice(input.kind === 'exchange' ? 'Exchange emptied.' : 'System disks reset.');
      setCompleted(value => value + 1);
      await apiRef.current.reload();
    };
    try {
      if (write) await apiRef.current.request(`/${id}/reset`, 'POST', input);
      if (!current()) return;
      await accept((await original()).receipt);
    } catch (cause) {
      if (!current()) return;
      try { await accept((await original()).receipt); }
      catch (readError) {
        if (!current()) return;
        const status = (cause as VmRequestError).status;
        if (fresh && (readError as VmRequestError).status === 404 && status && status >= 400 && status < 500 && status !== 408) {
          if (preserved(key)?.requestId === input.requestId) sessionStorage.removeItem(key);
          setPending(null);
        }
        setError(cause instanceof Error ? cause.message : 'The original reset is unconfirmed. Check its receipt.');
      }
    } finally {
      inflight.current = false;
      if (mounted.current) { setBusy(false); setReview(null); }
    }
  }, [id, key]);
  useEffect(() => {
    const original = preserved(key);
    let cancelled=false;
    queueMicrotask(()=>{if (!cancelled && original && api.csrfToken) void perform(original, false);});
    return()=>{cancelled=true;};
  }, [key, api.csrfToken, perform]);
  function open(kind: VmResetInput['kind']) {
    if (!vm || busy || pending) return;
    setError(''); setNotice('');
    setReview({ kind, requestId: vmRequestId(), expectedRevision: vm.revision ?? vm.imageSha256, confirm: true });
  }
  async function confirm() {
    if (!review || inflight.current || pending) return;
    try { sessionStorage.setItem(key, JSON.stringify(review)); }
    catch { setError('Enable session storage to preserve the original reset request before confirming.'); return; }
    setPending(review); await perform(review, true, true);
  }
  return { review, pending, busy, error, notice, completed, open, confirm, aborted,
    dismiss: () => {
      if (!aborted || busy || !pending) return;
      if (preserved(key)?.requestId === pending.requestId) sessionStorage.removeItem(key);
      setPending(null); setAborted(false); setError('');
    },
    close: () => { if (!busy) setReview(null); },
    read: () => pending ? perform(pending, false) : Promise.resolve(),
    retry: () => pending ? perform(pending, true) : Promise.resolve() };
}
export type VmResetControl = ReturnType<typeof useVmReset>;

export function VmResetDialog({ control, vm }: { control: VmResetControl; vm: VirtualMachine }) {
  const dialog = useRef<HTMLDialogElement>(null), cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const element = dialog.current, opener = document.activeElement;
    if (!control.review || !element) return;
    element.showModal(); cancel.current?.focus();
    return () => { element.close(); if (opener instanceof HTMLElement && opener.isConnected) opener.focus(); };
  }, [control.review]);
  if (!control.review) return null;
  const exchange = control.review.kind === 'exchange', stale = control.review.expectedRevision !== (vm.revision ?? vm.imageSha256);
  return createPortal(<dialog className="vm-reset-dialog" ref={dialog} aria-labelledby="vm-reset-title" onCancel={event => { event.preventDefault(); control.close(); }}>
    <h2 id="vm-reset-title">{exchange ? 'Empty Exchange?' : 'Reset system disks?'}</h2>
    <p>{exchange ? <>Delete all shared files, folders, guest exchange files, conflicts and pending sync data of <strong>{vm.name}</strong>, including every folder?</>
      : <>Delete all C: and D: changes and installed programs of <strong>{vm.name}</strong>?</>}</p>
    <p>{exchange ? 'System disks, VM settings, project assignments and saved access will be kept.' : 'Exchange and VM settings will be kept.'} The VM will remain stopped.</p>
    {stale && <p role="alert">The VM changed. Cancel and review its current state.</p>}
    {control.error && <p role="alert">{control.error}</p>}
    <footer><button ref={cancel} type="button" className="button-secondary" disabled={control.busy} onClick={control.close}>Cancel</button>
      <button type="button" className="button-danger" disabled={control.busy || stale || !['stopped', 'failed'].includes(vm.state)} onClick={() => void control.confirm()}>
        {control.busy ? 'Resetting…' : exchange ? 'Empty Exchange' : 'Reset system disks'}</button></footer>
  </dialog>, document.body);
}
