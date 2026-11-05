import { useEffect, useId, useRef, useState, useSyncExternalStore } from 'react';
import { createPortal } from 'react-dom';
import { acquireImage, releaseImage, currentImage, watchImages, imageRevision } from './imageResources';
import type { ImageResource } from './imageResources';
import { useImageVisibility } from './useImageVisibility';

const uuid = '[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}';
const reference = new RegExp(`^studio-image:(${uuid})/(${uuid})$`);
export function replyImageReference(value: string) {
  const match = reference.exec(value);
  return match ? { jobId: match[1], evidenceId: match[2] } : null;
}

type ImageState = { endpoint: string; resource?: ImageResource; url?: string; failed?: boolean; revision: number };
export function useStoredImage(endpoint: string | null) {
  const revision = useSyncExternalStore(watchImages, imageRevision, imageRevision);
  const [state, setState] = useState<ImageState | null>(null), previous = useRef<string | null>(null);
  useEffect(() => {
    if (!endpoint) return;
    let active = true;
    let resource: ImageResource | undefined;
    void Promise.resolve().then(() => {
      if (!active) return;
      const retry = previous.current !== endpoint && endpoint.includes('?retry='); previous.current = endpoint;
      resource = acquireImage(endpoint, retry); return resource.promise;
    }).then(url => { if (active && url) setState({ endpoint, resource, url, revision }); },
      () => { if (active) setState({ endpoint, resource, failed: true, revision }); });
    return () => { active = false; if (resource) releaseImage(resource); };
  }, [endpoint, revision]);
  return endpoint && state?.endpoint === endpoint && state.revision === revision
    && (!state.url || !!state.resource && currentImage(state.resource, state.url)) ? state : null;
}

export function ImageDialog({ url, alt, filename, download, close }: { url: string; alt: string; filename: string; download?: string; close: () => void }) {
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
      <a href={download ?? url} download={download ? undefined : filename}>{download ? 'Download original image' : 'Download PNG'}</a><button type="button" onClick={close} autoFocus>Close</button>
    </div>
    <div className={`agent-image-dialog-content${actual ? ' actual' : ''}`}><img src={url} alt={alt} /></div>
  </dialog>, document.body);
}

export function ReplyImage({ projectId, sessionId, jobId, evidenceId, alt }: {
  projectId: string; sessionId: string; jobId: string; evidenceId: string; alt: string;
}) {
  const { ref: previewRef, visible } = useImageVisibility();
  const endpoint = `/api/projects/${projectId}/sessions/${sessionId}/images/${jobId}/${evidenceId}`;
  const [opened, setOpen] = useState<string | null>(null), [attempt, setAttempt] = useState(0), [failed, setFailed] = useState<string | null>(null);
  const open = opened === endpoint, unavailable = failed === endpoint;
  const [height, setHeight] = useState(180);
  const image = useStoredImage(!unavailable && (visible || open) ? endpoint + (attempt ? '?retry=' + attempt : '') : null);
  const label = alt.trim().slice(0, 512) || 'VM screenshot', filename = `screenshot-${evidenceId}.png`;
  return <span ref={previewRef} className="agent-reply-image" role="figure" aria-label={label} style={{ minHeight: height }}>
    {image?.url && !unavailable ? <>
      <button className="agent-image-preview" type="button" aria-label="Enlarge screenshot" aria-haspopup="dialog" onClick={() => setOpen(endpoint)}>
        <img src={image.url} alt={label} onLoad={event => setHeight(Math.max(80, previewRef.current?.clientHeight ?? event.currentTarget.clientHeight))} onError={() => { setFailed(endpoint); setOpen(null); }} />
      </button>
      <span className="agent-image-actions"><button type="button" onClick={() => setOpen(endpoint)}>Enlarge</button>
        <a href={image.url} download={filename}>Download PNG</a></span>
    </> : <span className="agent-image-loading" role="status">{image?.failed || unavailable ? <>Screenshot unavailable. <button type="button" onClick={() => { setFailed(null); setAttempt(value => value + 1); }}>Reload screenshot</button></> : visible ? 'Loading screenshot…' : 'Screenshot preview'}</span>}
    {open && image?.url && !unavailable && <ImageDialog url={image.url} alt={label} filename={filename} close={() => setOpen(null)} />}
  </span>;
}
