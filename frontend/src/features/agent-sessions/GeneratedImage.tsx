import { useEffect, useState } from 'react';
import type { GeneratedAsset, GeneratedImage } from '../../../../shared/generated-images';
import { sessionPath, useSessionApi } from './api';
import { ImageDialog } from './ReplyImage';
const uuid = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;
export function generatedReference(value: string) {
  const prefix = 'studio-generated-image:';
  return value.startsWith(prefix) && uuid.test(value.slice(prefix.length)) ? value.slice(prefix.length) : null;
}
function imageRecord(value: unknown, sessionId: string): GeneratedImage | null {
  if (!value || typeof value !== 'object') return null;
  const image = value as GeneratedImage;
  return uuid.test(image.id) && image.sessionId === sessionId && image.mediaType === 'image/png'
    && /^[a-f0-9]{64}$/.test(image.sha256) && Number.isSafeInteger(image.size) && image.size > 0 && image.size <= 16 * 1024 * 1024
    && [image.width, image.height].every(v => Number.isSafeInteger(v) && v > 0 && v <= 16384) && image.width * image.height <= 40_000_000 ? image : null;
}
export function GeneratedPreview({ projectId, sessionId, imageId, alt = 'Generated image' }: { projectId: string; sessionId: string; imageId: string; alt?: string }) {
  const { base } = useSessionApi();
  const endpoint = base + sessionPath(projectId, sessionId) + '/generated-images/' + imageId;
  const [image, setImage] = useState<{ endpoint: string; url?: string; failed?: boolean } | null>(null), [retry, setRetry] = useState(0), [open, setOpen] = useState(false);
  useEffect(() => {
    if (!uuid.test(imageId)) return;
    const controller = new AbortController(); let url: string | undefined;
    void fetch(endpoint + '/preview', { credentials: 'same-origin', cache: 'no-store', signal: controller.signal, headers: { Accept: 'image/png' } })
      .then(async response => {
        if (!response.ok || response.headers.get('content-type')?.split(';')[0] !== 'image/png') throw new Error('Preview unavailable.');
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        if (!blob.size || blob.size > 16 * 1024 * 1024) throw new Error('Preview unavailable.');
        url = URL.createObjectURL(blob); setImage({ endpoint, url });
      }).catch(() => { if (!controller.signal.aborted) setImage({ endpoint, failed: true }); });
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [endpoint, imageId, retry]);
  const current = image?.endpoint === endpoint ? image : null, label = alt.trim().slice(0, 512) || 'Generated image';
  if (!uuid.test(imageId)) return null;
  return <span className="agent-generated-preview" role="figure" aria-label={label}>
    {current?.url ? <button type="button" className="agent-image-preview" aria-label="Enlarge generated image" onClick={() => setOpen(true)}>
      <img src={current.url} alt={label} onError={() => { setOpen(false); setImage({ endpoint, failed: true }); }} />
    </button> : <span role="status">{current?.failed ? 'Original image preview is unavailable.' : 'Loading generated image…'}</span>}
    <span className="agent-image-actions">
      {current?.url && <button type="button" onClick={() => setOpen(true)}>Enlarge</button>}
      {current?.failed && <button type="button" onClick={() => { setImage(null); setRetry(value => value + 1); }}>Reload preview</button>}
      <a href={endpoint + '/download'} download={`generated-image-${imageId}.png`}>Download original PNG</a>
    </span>
    {open && current?.url && <ImageDialog url={current.url} alt={label} filename={`generated-image-${imageId}.png`} close={() => setOpen(false)} />}
  </span>;
}
export function GeneratedCard({ value, asset, projectId, sessionId, status }: { value: unknown; asset: unknown; projectId: string; sessionId: string; status?: string }) {
  const image = imageRecord(value, sessionId);
  const imported = asset && typeof asset === 'object' ? asset as GeneratedAsset : null;
  const validAsset = imported && imported.stage === 'Imported' && typeof imported.path === 'string' && /^assets\//i.test(imported.path)
    && !imported.path.split('/').some(part => part === '..' || part === '.') && /^[a-f0-9]{64}$/.test(imported.sha256);
  if (!image && !validAsset) return status === 'running' || status === 'pending' ? <p role="status">Generating an image…</p> : null;
  return <section className="agent-generated-card" aria-label={validAsset ? 'Imported image asset' : 'Generated image output'}>
    {image && <><strong>Generated</strong><GeneratedPreview projectId={projectId} sessionId={sessionId} imageId={image.id} />
      <p>{image.width} × {image.height} · PNG · {Math.ceil(image.size / 1024)} KiB · {image.transparent ? 'Transparency' : 'Opaque'}</p>
      <p>Studio image <code>{image.id}</code> · SHA-256 <code>{image.sha256}</code></p></>}
    {validAsset && <><strong>Imported · <code>{imported.path}</code></strong><p>{imported.format} · {imported.width} × {imported.height}{imported.stride ? ` · Stride ${imported.stride}` : ''}</p>
      <p>SHA-256 <code>{imported.sha256}</code></p><p>Register the resource and its consuming code, then check the finished R4X resource report. Guest verification is separate.</p></>}
  </section>;
}
