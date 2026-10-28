import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentSession, SessionOptions } from '../../../../shared/agent-sessions';
import type { AttachmentListing, AttachmentReceipt, SessionAttachment } from '../../../../shared/agent-inputs';
import { ProjectRequestError, projectRequestId, sessionPath, useSessionApi } from './api';

export interface AttachmentDraft {
  requestId: string; name: string; size: number; mediaType: string;
  state: 'queued' | 'uploading' | 'checking' | 'ready' | 'error'; progress: number;
  attachment?: SessionAttachment; error?: string; retryable?: boolean;
}
const files = new Map<string, File>();
const uuid = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;
function read(key: string): AttachmentDraft[] {
  try {
    const value: AttachmentDraft[] = JSON.parse(sessionStorage.getItem(key) ?? '[]');
    return Array.isArray(value) ? value.filter(item => uuid.test(item.requestId) && typeof item.name === 'string'
      && item.name.length <= 255 && Number.isSafeInteger(item.size) && item.size > 0 && item.size <= 16777216).slice(0, 8)
      .map(item => ({ ...item, state: item.state === 'ready' && item.attachment ? 'ready' : 'checking', progress: 0 })) : [];
  } catch { return []; }
}

export function useAttachments(projectId: string, sessionId: string, session: AgentSession | null, token: string, refreshAuth: () => Promise<void>) {
  const { request, base: apiBase, scope } = useSessionApi();
  const base = sessionPath(projectId, sessionId) + '/attachments', key = `studio.attachments.${scope}.${projectId}.${sessionId}`;
  const [drafts, setDrafts] = useState(() => read(key));
  const current = useRef(drafts), mounted = useRef(true), transports = useRef(new Map<string, XMLHttpRequest>());
  const queue = useRef(Promise.resolve()), [error, setError] = useState(''), [check, setCheck] = useState(0);
  const [options, setOptions] = useState<SessionOptions | null>(null);
  const store = useCallback((update: (old: AttachmentDraft[]) => AttachmentDraft[]) => {
    const next = update(current.current);
    try { sessionStorage.setItem(key, JSON.stringify(next)); }
    catch { if (mounted.current) setError('Enable session storage before adding attachments.'); return false; }
    current.current = next; if (mounted.current) setDrafts(next); return true;
  }, [key]);
  useEffect(() => {
    mounted.current = true;
    const active = transports.current;
    return () => {
      mounted.current = false;
      // A reply can be lost after the server commits. Keep the original ID and
      // reconcile by reads when this exact owner/session returns.
      const next = current.current.map(item => item.state === 'uploading' || item.state === 'queued'
        ? { ...item, state: 'checking' as const } : item);
      try { sessionStorage.setItem(key, JSON.stringify(next)); } catch { /* Original IDs were stored before POST. */ }
      for (const transport of active.values()) transport.abort();
    };
  }, [key]);
  useEffect(() => {
    const controller = new AbortController();
    void request<SessionOptions>(sessionPath(projectId) + '/options', '', 'GET', undefined, controller.signal)
      .then(value => { if (!controller.signal.aborted) setOptions(value); }).catch(() => { if (!controller.signal.aborted) setOptions(null); });
    return () => controller.abort();
  }, [projectId, request, session?.providerId, session?.model]);

  const observe = useCallback((receipt: AttachmentReceipt, original: AttachmentDraft) => {
    if (receipt.requestId !== original.requestId) throw new Error('The upload receipt does not match the original file.');
    let next: Partial<AttachmentDraft>;
    if (receipt.state === 'ready' && receipt.attachment) {
      const value = receipt.attachment;
      if (value.sessionId !== sessionId || value.name !== original.name || value.size !== original.size || !uuid.test(value.id))
        throw new Error('This upload belongs to another file or session.');
      next = { state: 'ready', attachment: value, progress: 100, error: undefined, retryable: false };
      files.delete(key + ':' + original.requestId);
    } else if (receipt.state === 'pending') next = { state: 'checking', error: undefined };
    else {
      files.delete(key + ':' + original.requestId);
      next = { state: 'error', error: receipt.reason ?? 'This upload is unavailable. Select a new file or remove this draft.', retryable: false };
    }
    store(old => old.map(item => item.requestId === original.requestId ? { ...item, ...next } : item));
  }, [key, sessionId, store]);
  useEffect(() => {
    const controller = new AbortController(); let timer: number | undefined, attempt = 0;
    const reconcile = async () => {
      const pending = current.current.filter(item => item.state === 'checking');
      for (const item of pending) {
        try {
          const receipt = await request<AttachmentReceipt>(base + '/uploads/' + item.requestId, '', 'GET', undefined, controller.signal);
          if (!controller.signal.aborted) observe(receipt, item);
        } catch (failure) {
          if (controller.signal.aborted) return;
          const issue = failure as ProjectRequestError;
          if (issue.status === 403) await refreshAuth().catch(() => undefined);
          store(old => old.map(value => value.requestId === item.requestId ? { ...value, state: 'error', retryable: issue.status === 404,
            error: issue.status === 404 ? 'Upload was not accepted. Retry this file or select it again.' : 'Upload status is unconfirmed. Check its original status.' } : value));
        }
      }
      if (!controller.signal.aborted && ++attempt < 16 && current.current.some(item => item.state === 'checking'))
        timer = window.setTimeout(() => { void reconcile(); }, 1000);
    };
    void reconcile();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [base, request, observe, refreshAuth, store, check]);

  async function upload(item: AttachmentDraft, file: File) {
    if (!mounted.current || !current.current.some(value => value.requestId === item.requestId)) return;
    store(old => old.map(value => value.requestId === item.requestId ? { ...value, state: 'uploading', progress: 0, error: undefined } : value));
    await new Promise<void>(resolve => {
      const xhr = new XMLHttpRequest(); transports.current.set(item.requestId, xhr);
      xhr.open('POST', apiBase + base + '/uploads/' + item.requestId + '?' + new URLSearchParams({ name: item.name, mediaType: item.mediaType }));
      xhr.setRequestHeader('Content-Type', 'application/octet-stream'); xhr.setRequestHeader('X-CSRF-Token', token);
      xhr.withCredentials = true; xhr.timeout = 25000;
      xhr.upload.onprogress = event => {
        if (mounted.current) store(old => old.map(value => value.requestId === item.requestId ? { ...value, progress: Math.min(100, Math.round(100 * event.loaded / file.size)) } : value));
      };
      const finish = () => { transports.current.delete(item.requestId); resolve(); };
      const uncertain = () => {
        if (mounted.current) { store(old => old.map(value => value.requestId === item.requestId ? { ...value, state: 'checking' } : value)); setCheck(value => value + 1); }
        finish();
      };
      xhr.onerror = uncertain; xhr.ontimeout = uncertain; xhr.onabort = uncertain;
      xhr.onload = () => {
        if (!mounted.current) { finish(); return; }
        try {
          const value = JSON.parse(xhr.responseText);
          if (value.requestId) { observe(value as AttachmentReceipt, item); if (value.state === 'pending') setCheck(value => value + 1); }
          else {
            if (xhr.status >= 500) {
              store(old => old.map(value2 => value2.requestId === item.requestId ? { ...value2, state: 'checking' } : value2));
              setCheck(value2 => value2 + 1); finish(); return;
            }
            store(old => old.map(value2 => value2.requestId === item.requestId ? { ...value2, state: 'error', retryable: xhr.status < 500,
              error: value.message ?? 'Upload failed. Check its original status before retrying.' } : value2));
            if (xhr.status === 403) void refreshAuth();
          }
        } catch { store(old => old.map(value => value.requestId === item.requestId ? { ...value, state: 'checking' } : value)); setCheck(value => value + 1); }
        finish();
      };
      xhr.send(file);
    });
  }
  function add(chosen: File[]) {
    if (!chosen.length) return;
    if (current.current.length + chosen.length > 8 || current.current.reduce((sum, item) => sum + item.size, 0) + chosen.reduce((sum, file) => sum + file.size, 0) > 33554432) {
      setError('Choose up to 8 files and 32 MiB in total. Existing drafts were preserved.'); return;
    }
    if (chosen.some(file => file.size < 1 || file.size > 16777216)) { setError('Each attachment must contain between 1 byte and 16 MiB.'); return; }
    if ([...files.values()].reduce((sum, file) => sum + file.size, 0) + chosen.reduce((sum, file) => sum + file.size, 0) > 67108864) {
      setError('Finish or remove earlier pending uploads before adding more files.'); return;
    }
    const rows = chosen.map(file => ({ requestId: projectRequestId(), name: file.name || 'pasted-image.png', size: file.size,
      mediaType: file.type || 'application/octet-stream', state: 'queued' as const, progress: 0 }));
    if (!store(old => [...old, ...rows])) return;
    setError(''); rows.forEach((item, index) => {
      files.set(key + ':' + item.requestId, chosen[index]);
      queue.current = queue.current.then(() => upload(item, chosen[index])).catch(() => undefined);
    });
  }
  async function checkStatus(item: AttachmentDraft, retry = false) {
    try {
      const receipt = await request<AttachmentReceipt>(base + '/uploads/' + item.requestId);
      if (mounted.current) { observe(receipt, item); if (receipt.state === 'pending') setCheck(value => value + 1); }
    } catch (failure) {
      if (!mounted.current) return;
      const issue = failure as ProjectRequestError, original = files.get(key + ':' + item.requestId);
      if (issue.status === 403) await refreshAuth().catch(() => undefined);
      if (retry && issue.status === 404 && original) await upload(item, original);
      else store(old => old.map(value => value.requestId === item.requestId ? { ...value, state: 'error', retryable: issue.status === 404,
        error: issue.status === 404 ? 'Select the file again to upload it.' : 'The original upload is still unconfirmed.' } : value));
    }
  }
  async function remove(item: AttachmentDraft) {
    // Removal changes the local selection immediately. A concurrent explicit
    // Send cannot still capture a card the user already removed.
    if (!store(old => old.filter(value => value.requestId !== item.requestId))) return;
    files.delete(key + ':' + item.requestId); transports.current.get(item.requestId)?.abort();
    if (item.attachment) {
      try { await request(base + '/' + item.attachment.id, token, 'DELETE'); }
      catch { if (mounted.current) setError('The attachment was removed from this draft. Stored upload cleanup is unconfirmed.'); }
    }
  }
  const model = options?.providers.find(value => value.id === session?.providerId)?.models.find(value => value.id === session?.model);
  const selected = drafts.flatMap(value => value.attachment ? [value.attachment] : []);
  const issue = drafts.some(value => value.state !== 'ready') ? 'Wait for every selected upload to be ready, or remove it.'
    : selected.some(value => value.readable === false) ? selected.find(value => value.readable === false)!.limitation ?? 'This document has no readable text.'
      : selected.some(value => value.mode === 'localImage') && model?.imageInputs !== 'supported' ? (model?.imageInputs === 'unsupported' ? 'This model does not support images. Choose another model; your files are preserved.' : 'Image support is unavailable. Reload the model choices before sending images.')
        : selected.some(value => value.mode !== 'localImage' && (value.extractedBytes ?? 0) > 8192)
          && (!session?.permissions['studio.read_attachment'] || !session.permissions['studio.read_file']) ? 'Enable Read attachment and Read file for long documents, or use a new session.' : '';
  const accepted = useCallback((ids: string[]) => { store(old => old.filter(value => !value.attachment || !ids.includes(value.attachment.id))); }, [store]);
  return { drafts, selected, issue, error, add, remove, checkStatus,
    listStored: () => request<AttachmentListing>(base),
    removeStored: async (id: string) => {
      setError('');
      const draft = current.current.find(value => value.attachment?.id === id);
      if (draft) { await remove(draft); return; }
      await request(base + '/' + id, token, 'DELETE');
    },
    preview: (id: string) => apiBase + base + '/' + id + '/preview',
    accepted,
    hasFiles: drafts.length > 0, ready: !!drafts.length && !issue };
}
