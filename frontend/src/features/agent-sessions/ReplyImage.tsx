import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

const uuid = '[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}';
const reference = new RegExp(`^studio-image:(${uuid})/(${uuid})$`);
export function replyImageReference(value: string) {
  const match = reference.exec(value);
  return match ? { jobId: match[1], evidenceId: match[2] } : null;
}

type Resource = { controller: AbortController; users: number; promise: Promise<string>; url?: string };
const images = new Map<string, Resource>();

function acquireImage(endpoint: string): Resource {
  const existing = images.get(endpoint);
  if (existing) { existing.users++; return existing; }
  const controller = new AbortController();
  const resource: Resource = { controller, users: 1, promise: Promise.resolve('') };
  resource.promise = fetch(endpoint, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
    headers: { Accept: 'image/png' } }).then(async (response) => {
    if (!response.ok || response.headers.get('content-type')?.split(';')[0] !== 'image/png') throw new Error('Screenshot unavailable.');
    const blob = await response.blob();
    if (controller.signal.aborted || blob.size < 1 || blob.size > 393216) throw new Error('Screenshot unavailable.');
    resource.url = URL.createObjectURL(blob);
    return resource.url;
  });
  images.set(endpoint, resource);
  return resource;
}

function releaseImage(endpoint: string, resource: Resource) {
  if (--resource.users > 0) return;
  resource.controller.abort();
  if (resource.url) URL.revokeObjectURL(resource.url);
  if (images.get(endpoint) === resource) images.delete(endpoint);
}

type ImageState = { endpoint: string; url?: string; failed?: boolean };
function useImage(endpoint: string) {
  const [state, setState] = useState<ImageState | null>(null);
  useEffect(() => {
    let active = true;
    const resource = acquireImage(endpoint);
    void resource.promise.then((url) => { if (active) setState({ endpoint, url }); },
      () => { if (active) setState({ endpoint, failed: true }); });
    return () => { active = false; releaseImage(endpoint, resource); };
  }, [endpoint]);
  return state?.endpoint === endpoint ? state : null;
}

export function ImageDialog({ url, alt, filename, close }: { url: string; alt: string; filename: string; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null), title = useId();
  const [actual, setActual] = useState(false);
  useEffect(() => {
    const element = dialog.current!, opener = document.activeElement;
    element.showModal();
    return () => { element.close(); if (opener instanceof HTMLElement && opener.isConnected) opener.focus({ preventScroll: true }); };
  }, []);
  return createPortal(<dialog ref={dialog} className="agent-image-dialog" aria-labelledby={title}
    onCancel={(event) => { event.preventDefault(); close(); }}>
    <div className="agent-image-dialog-bar"><h2 id={title}>{alt}</h2>
      <button type="button" aria-pressed={actual} onClick={() => setActual(!actual)}>{actual ? 'Fit to view' : 'Actual size'}</button>
      <a href={url} download={filename}>Download PNG</a><button type="button" onClick={close} autoFocus>Close</button>
    </div>
    <div className={`agent-image-dialog-content${actual ? ' actual' : ''}`}><img src={url} alt={alt} /></div>
  </dialog>, document.body);
}

export function ReplyImage({ projectId, sessionId, jobId, evidenceId, alt }: {
  projectId: string; sessionId: string; jobId: string; evidenceId: string; alt: string;
}) {
  const endpoint = `/api/projects/${projectId}/sessions/${sessionId}/images/${jobId}/${evidenceId}`;
  const image = useImage(endpoint), [open, setOpen] = useState(false), [failed, setFailed] = useState<string | null>(null);
  const label = alt.trim().slice(0, 512) || 'VM screenshot', filename = `screenshot-${evidenceId}.png`;
  if (image?.failed || failed === endpoint) return <span className="agent-image-unavailable" role="status">Screenshot unavailable.</span>;
  if (!image?.url) return <span className="agent-image-loading" role="status">Loading screenshot…</span>;
  return <span className="agent-reply-image" role="figure" aria-label={label}>
    <button className="agent-image-preview" type="button" aria-label="Enlarge screenshot" aria-haspopup="dialog" onClick={() => setOpen(true)}>
      <img src={image.url} alt={label} onError={() => { setFailed(endpoint); setOpen(false); }} />
    </button>
    <span className="agent-image-actions"><button type="button" onClick={() => setOpen(true)}>Enlarge</button>
      <a href={image.url} download={filename}>Download PNG</a></span>
    {open && <ImageDialog url={image.url} alt={label} filename={filename} close={() => setOpen(false)} />}
  </span>;
}
