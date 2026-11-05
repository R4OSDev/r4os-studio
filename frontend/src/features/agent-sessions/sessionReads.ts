/** Small, scoped GET sharing. Mutations and original-request receipts bypass it. */
type Entry = { controller: AbortController; promise: Promise<unknown>; users: number; expires: number; kind: 'options' | 'capabilities' | 'pending' };
const entries = new Map<string, Entry>(), identities = new Map<string, string>(), metadata = new Map<string, string>();
let release: string | undefined;
const invalidated = 'studio-session-reads-invalidated';

export function invalidateSessionReads(kind?: 'options' | 'capabilities', notify = true) {
  for (const [key, entry] of entries) if (!kind || entry.kind === kind) {
    entry.controller.abort(); entries.delete(key);
  }
  if (notify && typeof window !== 'undefined') window.dispatchEvent(new CustomEvent(invalidated, { detail: kind }));
}

export function watchSessionReads(refresh: () => void, kind: 'options' | 'capabilities') {
  const listen = (event: Event) => { const changed = (event as CustomEvent).detail; if (!changed || changed === kind) refresh(); };
  window.addEventListener(invalidated, listen);
  return () => window.removeEventListener(invalidated, listen);
}

export function sessionReadIdentity(scope: string, identity: string) {
  if (identities.get(scope) === identity) return;
  identities.set(scope, identity); invalidateSessionReads();
}

export function invalidateSessionPending(base: string, path: string) {
  const session = /^\/[^/]+\/sessions\/[^/?]+/.exec(path)?.[0];
  if (!session) return;
  for (const [key, entry] of entries) if (entry.kind === 'pending' && key.startsWith(base + session + '/')) {
    entry.controller.abort(); entries.delete(key);
  }
}

export function sessionReadMetadata(key: string, value: unknown) {
  const next = JSON.stringify(value);
  if (metadata.get(key) === next) return;
  metadata.delete(key); metadata.set(key, next);
  while (metadata.size > 32) metadata.delete(metadata.keys().next().value!);
  invalidateSessionReads('options');
}

export function sharedSessionRead<T>(base: string, path: string, load: (signal: AbortSignal) => Promise<T>, signal?: AbortSignal): Promise<T> {
  const kind = path === '/agent-capabilities' ? 'capabilities' : path.endsWith('/options') ? 'options' : 'pending';
  const key = base + path;
  if (signal?.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'));
  let entry = entries.get(key);
  if (entry && entry.expires <= Date.now()) { entries.delete(key); entry = undefined; }
  if (!entry) {
    // Active callers remain bounded too; never evict a live transport merely
    // to conceal an unbounded queue. These are optional read requests only.
    if (entries.size >= 64) for (const [oldKey, old] of entries) if (!old.users) entries.delete(oldKey);
    if (entries.size >= 64) return Promise.reject(new Error('Session reads are busy. Try again shortly.'));
    const controller = new AbortController();
    const created: Entry = { controller, users: 0, expires: Infinity, kind, promise: Promise.resolve() };
    created.promise = Promise.resolve().then(() => load(controller.signal)).then(value => {
      if (controller.signal.aborted || entries.get(key) !== created) throw new DOMException('Superseded', 'AbortError');
      const facts = value as { version?: string; enabled?: boolean };
      if (kind === 'capabilities' && facts.version) {
        if (release && release !== facts.version) invalidateSessionReads('options');
        release = facts.version;
      }
      created.expires = Date.now() + (kind === 'options' ? 5000 : kind === 'capabilities' && facts.enabled !== false ? 30000 : 0);
      return value;
    }).catch(error => {
      if (entries.get(key) === created) entries.delete(key);
      throw error;
    });
    entry = created; entries.set(key, entry);
  }
  const current = entry; current.users++;
  return new Promise<T>((resolve, reject) => {
    let done = false;
    const finish = (error?: unknown, value?: T) => {
      if (done) return; done = true; signal?.removeEventListener('abort', abort);
      if (--current.users === 0 && current.expires === Infinity) {
        current.controller.abort(); if (entries.get(key) === current) entries.delete(key);
      }
      if (error) reject(error); else resolve(value!);
    };
    const abort = () => finish(new DOMException('Aborted', 'AbortError'));
    signal?.addEventListener('abort', abort, { once: true });
    current.promise.then(value => finish(undefined, value as T), error => finish(error));
  });
}

export function shareSessionPath(path: string) {
  return path === '/agent-capabilities' || path.endsWith('/options') || /\/goal\/clock$|\/messages\?view=pending|\/environment-notes(?:\/summary)?(?:\?|$)/.test(path)
    && !path.includes('/requests/');
}
