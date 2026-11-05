import { invalidateSessionReads, watchSessionIdentity } from './sessionReads';

const MAX_IMAGES = 32, MAX_BYTES = 8 * 1024 * 1024, MAX_IMAGE = 393216;
const uuid = '[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}';
const endpointPattern = new RegExp(`^/api/(?:projects|skills)/${uuid}/sessions/${uuid}/(?:images/${uuid}/${uuid}|screenshots/${uuid}/${uuid}|generated-images/${uuid}/preview)(?:\\?retry=\\d{1,6})?$`);
export type ImageResource = {
  endpoint: string; controller: AbortController; users: number; promise: Promise<string>;
  resolve: (url: string) => void; reject: (error: Error) => void; settled: boolean; url?: string; bytes: number;
};
const images = new Map<string, ImageResource>(), pending: ImageResource[] = [];
const listeners = new Set<() => void>();
let active = 0, generated = 0, bytes = 0, reserved = 0, revision = 0, blocked = false;
export const imageRevision = () => revision;
export const watchImages = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
function dispose(resource: ImageResource) {
  resource.controller.abort();
  const index = pending.indexOf(resource); if (index >= 0) pending.splice(index, 1);
  if (resource.url) { URL.revokeObjectURL(resource.url); resource.url = undefined; bytes -= resource.bytes; resource.bytes = 0; }
  if (!resource.settled) { resource.settled = true; resource.reject(new DOMException('Image read cancelled.', 'AbortError')); }
  if (images.get(resource.endpoint) === resource) images.delete(resource.endpoint);
}
watchSessionIdentity(reason => {
  blocked = reason !== 'renewed';
  for (const resource of images.values()) dispose(resource);
  revision++; listeners.forEach(listener => listener());
});
async function readBlob(response: Response, signal: AbortSignal) {
  const type = response.headers.get('content-type')?.split(';')[0];
  if (!response.ok || !type || !['image/png', 'image/jpeg', 'image/webp'].includes(type)
      || Number(response.headers.get('content-length')) > MAX_IMAGE || !response.body) {
    void response.body?.cancel(); throw Error('Image preview unavailable.');
  }
  const reader = response.body.getReader(), chunks: Uint8Array<ArrayBuffer>[] = [];
  let size = 0;
  try {
    for (;;) {
      const next = await reader.read(); if (next.done) break;
      if (signal.aborted || (size += next.value.byteLength) > MAX_IMAGE) throw Error('Image preview exceeds its limit.');
      chunks.push(new Uint8Array(next.value));
    }
    if (!size || signal.aborted) throw Error('Image preview unavailable.');
    return new Blob(chunks, { type });
  } finally { void reader.cancel().catch(() => undefined); }
}
function loadImages() {
  while (active < 3 && pending.length) {
    // Derived previews share the coordinator's single isolated decoder slot.
    // Screenshots can still use the other two transports while it is occupied.
    const index = pending.findIndex(resource => !generated || !resource.endpoint.includes('/generated-images/'));
    if (index < 0) break;
    const resource = pending.splice(index, 1)[0], isGenerated = resource.endpoint.includes('/generated-images/');
    if (resource.controller.signal.aborted) continue;
    // Reserve the full response bound before reading; in-flight candidate
    // Blobs count against the same budget as retained object URLs.
    if (bytes + reserved + MAX_IMAGE > MAX_BYTES) {
      resource.settled = true; resource.reject(Error('Image previews are full. Close another image and reload.')); continue;
    }
    reserved += MAX_IMAGE;
    let reservation = true;
    active++; if (isGenerated) generated++;
    void (async () => {
      try {
        const response = await fetch(resource.endpoint, { credentials: 'same-origin', cache: 'no-store', signal: resource.controller.signal,
          headers: { Accept: 'image/png,image/jpeg,image/webp' } });
        if ([401, 403].includes(response.status)) invalidateSessionReads(undefined, false);
        const blob = await readBlob(response, resource.controller.signal);
        if (resource.controller.signal.aborted || images.get(resource.endpoint) !== resource) return;
        if (bytes + blob.size > MAX_BYTES) throw Error('Image previews are full. Close another image and reload.');
        resource.url = URL.createObjectURL(blob); resource.bytes = blob.size; bytes += blob.size;
        reserved -= MAX_IMAGE; reservation = false;
        resource.settled = true; resource.resolve(resource.url);
      } catch (error) {
        if (!resource.settled) { resource.settled = true; resource.reject(error as Error); }
      } finally { if (reservation) reserved -= MAX_IMAGE; active--; if (isGenerated) generated--; loadImages(); }
    })();
  }
}
export function acquireImage(endpoint: string, retry = false) {
  const existing = images.get(endpoint);
  if (existing) { existing.users++; return existing; }
  if (blocked && !retry) throw Error('Sign-in expired. Refresh your session before reloading images.');
  if (!endpointPattern.test(endpoint)) throw Error('Image reference unavailable.');
  if (images.size >= MAX_IMAGES) throw Error('Too many image previews are open. Close another image and reload.');
  let resolve!: ImageResource['resolve'], reject!: ImageResource['reject'];
  const promise = new Promise<string>((done, fail) => { resolve = done; reject = fail; });
  const resource: ImageResource = { endpoint, controller: new AbortController(), users: 1, promise, resolve, reject, settled: false, bytes: 0 };
  images.set(endpoint, resource); pending.push(resource); loadImages();
  return resource;
}
export function releaseImage(resource: ImageResource) { if (--resource.users === 0) dispose(resource); }
export function currentImage(resource: ImageResource, url: string) { return images.get(resource.endpoint) === resource && resource.url === url; }
