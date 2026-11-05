import { useState } from 'react';
import type { GeneratedAsset, GeneratedImage } from '../../../../shared/generated-images';
import { sessionPath, useSessionApi } from './api';
import { ImageDialog, useStoredImage } from './ReplyImage';
import { useImageVisibility } from './useImageVisibility';
const uuid = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;
export function generatedReference(value: string) {
  const prefix = 'studio-generated-image:';
  return value.startsWith(prefix) && uuid.test(value.slice(prefix.length)) ? value.slice(prefix.length) : null;
}
function imageRecord(value: unknown, sessionId: string): GeneratedImage | null {
  if (!value || typeof value !== 'object') return null;
  const image = value as GeneratedImage;
  return uuid.test(image.id) && image.sessionId === sessionId && ['image/png','image/jpeg','image/webp'].includes(image.mediaType)
    && /^[a-f0-9]{64}$/.test(image.sha256) && Number.isSafeInteger(image.size) && image.size > 0 && image.size <= 16 * 1024 * 1024
    && [image.width, image.height].every(v => Number.isSafeInteger(v) && v > 0 && v <= 16384) && image.width * image.height <= 40_000_000 ? image : null;
}
export function GeneratedPreview({ projectId, sessionId, imageId, alt = 'Generated image' }: { projectId: string; sessionId: string; imageId: string; alt?: string }) {
  const { base } = useSessionApi();
  const endpoint = base + sessionPath(projectId, sessionId) + '/generated-images/' + imageId;
  const { ref: previewRef, visible } = useImageVisibility(uuid.test(imageId));
  const [attempt, setAttempt] = useState(0), [opened, setOpen] = useState<string | null>(null), [failed, setFailed] = useState<string | null>(null), [height, setHeight] = useState(180);
  const open = opened === endpoint, unavailable = failed === endpoint;
  const preview = endpoint + '/preview' + (attempt ? '?retry=' + attempt : '');
  const current = useStoredImage(uuid.test(imageId) && !unavailable && (visible || open) ? preview : null);
  const label = alt.trim().slice(0, 512) || 'Generated image';
  if (!uuid.test(imageId)) return null;
  return <span ref={previewRef} className="agent-generated-preview" role="figure" aria-label={label} style={{ minHeight: height }}>
    {current?.url && !unavailable ? <button type="button" className="agent-image-preview" aria-label="Enlarge generated image" onClick={() => setOpen(endpoint)}>
      <img src={current.url} alt={label} onLoad={event => setHeight(Math.max(80, previewRef.current?.clientHeight ?? event.currentTarget.clientHeight))} onError={() => { setOpen(null); setFailed(endpoint); }} />
    </button> : <span role="status">{current?.failed || unavailable ? 'Original image preview is unavailable.' : visible ? 'Loading generated image…' : 'Generated image preview'}</span>}
    <span className="agent-image-actions">
      {current?.url && !unavailable && <button type="button" onClick={() => setOpen(endpoint)}>Enlarge</button>}
      {(current?.failed || unavailable) && <button type="button" onClick={() => { setFailed(null); setAttempt(value => value + 1); }}>Reload preview</button>}
      <a href={endpoint + '/download'}>Download original image</a>
    </span>
    {open && current?.url && !unavailable && <ImageDialog url={current.url} alt={label} filename={`image-${imageId}.png`} download={endpoint + '/download'} close={() => setOpen(null)} />}
  </span>;
}
export function GeneratedCard({ value, asset, projectId, sessionId, status }: { value: unknown; asset: unknown; projectId: string; sessionId: string; status?: string }) {
  const image = imageRecord(value, sessionId);
  const imported = asset && typeof asset === 'object' ? asset as GeneratedAsset : null;
  const validAsset = imported && imported.stage === 'Imported' && typeof imported.path === 'string' && /^assets\//i.test(imported.path)
    && !imported.path.split('/').some(part => part === '..' || part === '.') && /^[a-f0-9]{64}$/.test(imported.sha256);
  if (!image && !validAsset) return status === 'running' || status === 'pending' ? <p role="status">Generating an image…</p> : null;
  return <section className="agent-generated-card" aria-label={validAsset ? 'Imported image asset' : 'Generated image output'}>
    {image && <><strong>{image.source ? 'Tool image' : 'Generated'}</strong><GeneratedPreview projectId={projectId} sessionId={sessionId} imageId={image.id} alt={image.source ? 'Tool image' : 'Generated image'} />
      <p>{image.width} × {image.height} · {image.mediaType.slice(6).toUpperCase()} · {Math.ceil(image.size / 1024)} KiB · {image.transparent ? 'Transparency' : 'Opaque'}</p>
      <p>Studio image <code>{image.id}</code> · SHA-256 <code>{image.sha256}</code></p></>}
    {validAsset && <><strong>Imported · <code>{imported.path}</code></strong><p>{imported.format} · {imported.width} × {imported.height}{imported.stride ? ` · Stride ${imported.stride}` : ''}</p>
      <p>SHA-256 <code>{imported.sha256}</code></p><p>Register the resource and its consuming code, then check the finished R4X resource report. Guest verification is separate.</p></>}
  </section>;
}
