import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { SessionDeletionInput, SessionDeletionPreview, SessionDeletionReceipt } from '../../../../shared/agent-sessions';
import { useSessionApi, sessionPath, projectRequestId, ProjectRequestError } from './api';
import { announceDeletedSession, clearDeletedSession, deletionKey, pendingDeletion } from './sessionDeletionStorage';

export function DeleteSessionDialog({ projectId, sessionId, token, reauth, close, deleted }: {
  projectId: string; sessionId: string; token: string; reauth: () => Promise<void>; close: () => void; deleted: () => void;
}) {
  const { request, scope } = useSessionApi(), base = sessionPath(projectId, sessionId) + '/deletion';
  const dialog = useRef<HTMLDialogElement>(null), field = useRef<HTMLInputElement>(null), done = useRef(false);
  const [pending, setPending] = useState<SessionDeletionInput | null>(() => pendingDeletion(scope, projectId, sessionId));
  const [preview, setPreview] = useState<SessionDeletionPreview | null>(null), [name, setName] = useState('');
  const [receipt, setReceipt] = useState<SessionDeletionReceipt | null>(null), [error, setError] = useState('');
  const [posting, setPosting] = useState(false), [epoch, setEpoch] = useState(0);
  useEffect(() => {
    const element = dialog.current!, opener = document.activeElement; element.showModal();
    return () => { element.close(); if (opener instanceof HTMLElement && opener.isConnected) opener.focus(); };
  }, []);
  useEffect(() => { if (preview?.allowed && !pending) field.current?.focus(); }, [preview, pending]);
  useEffect(() => {
    if (pending) return;
    const controller = new AbortController();
    void request<SessionDeletionPreview>(base, '', 'GET', undefined, controller.signal).then(value => { if (!controller.signal.aborted) { setPreview(value); field.current?.focus(); } })
      .catch((failure: Error) => { if (!controller.signal.aborted) { setError(failure.message); if ((failure as ProjectRequestError).status === 403) void reauth(); } });
    return () => controller.abort();
  }, [base, pending, epoch, request, reauth]);
  const accept = useCallback((value: SessionDeletionReceipt) => {
    if (value.sessionId !== sessionId || value.requestId !== pending?.requestId) throw Error('The receipt belongs to another session deletion.');
    setReceipt(value);
    if (value.state === 'deleted' && !done.current) {
      done.current = true;
      try { clearDeletedSession(scope, projectId, sessionId, value.creationRequestIds); } catch { /* Server confirmation remains authoritative. */ }
      announceDeletedSession(scope, projectId, sessionId); deleted();
    } else if (value.state === 'unknown') setError(value.reason ?? 'Cleanup is unconfirmed. Read the original receipt.');
  }, [sessionId, pending, scope, projectId, deleted]);
  useEffect(() => {
    if (!pending || posting) return;
    let cancelled = false, timer: number | undefined;
    const read = async () => {
      try {
        const value = await request<SessionDeletionReceipt>(base + '/' + pending.requestId);
        if (cancelled) return; accept(value);
        if (value.state === 'deleting') timer = window.setTimeout(() => void read(), 750);
      } catch (failure) {
        if (cancelled) return;
        const error = failure as ProjectRequestError;
        setError(error.status === 404 ? 'No original receipt was found. Retry this same request explicitly.' : error.message);
        if (error.status === 403) void reauth();
      }
    };
    void read(); return () => { cancelled = true; window.clearTimeout(timer); };
  }, [base, pending, posting, request, accept, epoch, reauth]);
  async function submit(original?: SessionDeletionInput) {
    if (posting || (!original && (!preview?.allowed || name !== preview.name))) return;
    const input = original ?? { requestId: projectRequestId(), revision: preview!.revision, scopeHash: preview!.scopeHash, confirmName: name };
    try { sessionStorage.setItem(deletionKey(scope, projectId, sessionId), JSON.stringify(input)); }
    catch { setError('Enable session storage before deleting a session.'); return; }
    setPending(input); setPosting(true); setError('');
    try { setReceipt(await request<SessionDeletionReceipt>(base, token, 'POST', input)); setEpoch(value => value + 1); }
    catch (failure) {
      const error = failure as ProjectRequestError; setError(error.message);
      if (error.status === 403) void reauth();
      if ([400, 403, 404, 409, 423, 429].includes(error.status)) {
        // A rejected retry can still have an earlier original reservation.
        try { setReceipt(await request<SessionDeletionReceipt>(base + '/' + input.requestId)); }
        catch (readFailure) {
          if ((readFailure as ProjectRequestError).status === 404) {
            sessionStorage.removeItem(deletionKey(scope, projectId, sessionId)); setPending(null); setPreview(null); setName(''); setEpoch(value => value + 1);
          }
        }
      }
    } finally { setPosting(false); }
  }
  return createPortal(<dialog className="project-dialog session-delete-dialog" ref={dialog} aria-labelledby="delete-session-title" onCancel={event => { event.preventDefault(); if (!posting) close(); }}>
    <header className="project-dialog-header"><h2 id="delete-session-title">Delete session</h2></header>
    <div className="session-delete-content">
      <p>Permanently delete <strong>{preview?.name ?? pending?.confirmName ?? 'this session'}</strong>?</p>
      <p>This removes its settings, Studio and native history, Goals, messages, uploads, images and environment notes. Unsaved settings and the composer draft for this session are discarded after deletion.</p>
      <p>Other sessions, project or skill sources, credentials and virtual machines remain. Project development artifacts and job receipts remain in the project. Confirmed numeric lifetime statistics are retained.</p>
      {preview && !preview.allowed && <div role="status"><p>Resolve this work using its normal controls, then check again:</p><ul>{preview.blockers.map(reason => <li key={reason}>{reason}</li>)}</ul></div>}
      {!pending && <label>Type the session name to confirm<input ref={field} autoComplete="off" maxLength={120} value={name} disabled={!preview?.allowed || posting} onChange={event => setName(event.target.value)} /></label>}
      {pending && <p role="status">{receipt?.state === 'unknown' ? 'Cleanup is unconfirmed.' : 'Checking the original deletion receipt…'}</p>}
      {error && <p className="project-dialog-error" role="alert">{error}</p>}
    </div>
    <footer className="project-actions"><button type="button" disabled={posting} onClick={close}>{pending ? 'Close' : 'Cancel'}</button><button type="button" disabled={posting} onClick={() => { setError(''); setEpoch(value => value + 1); }}>Check again</button>
      {pending ? <button type="button" disabled={posting} onClick={() => void submit(pending)}>Retry same request</button> : <button type="button" className="session-delete-action" disabled={posting || !preview?.allowed || name !== preview.name} onClick={() => void submit()}>Delete session</button>}
    </footer>
  </dialog>, document.body);
}
