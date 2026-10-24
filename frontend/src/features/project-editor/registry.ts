import type { EditorState } from '@codemirror/state';
import type { EditorMutation, EditorNode, EditorReceipt, EditorStatus, EditorTree, EditorSearchInput, EditorSearchResult } from '../../../../shared/project-editor';
import type { EditorDocument } from './model';
import { projectRequest, projectRequestId, ProjectRequestError } from '../projects/api';

interface Pending { body: EditorMutation; documents?: { path: string; revision?: string }[]; initialRejection?: string }
export interface EditorProject {
  id: string; token: string; docs: EditorDocument[]; active: string; selection?: EditorNode;
  trees: Map<string, EditorTree>; expanded: Set<string>; loading: Set<string>; status?: EditorStatus;
  pending?: Pending; working: boolean; error: string; notice: string; initialized: boolean; deleted: boolean;
  generation: number; accessError?: string;
}
export const dirty = (doc: EditorDocument) => !doc.state.doc.eq(doc.baseText);
const pendingKey = (id: string) => 'studio.editor.request.' + id;
function remembered(id: string): Pending | undefined {
  try {
    const raw = sessionStorage.getItem(pendingKey(id));
    if (!raw || raw.length > 2 * 1024 * 1024) return;
    const value = JSON.parse(raw) as Pending;
    if (value.body && /^[a-f0-9-]{36}$/.test(value.body.requestId) && typeof value.body.path === 'string') return value;
  } catch { /* Server receipts remain authoritative. */ }
}
export class EditorRegistry {
  private projects = new Map<string, EditorProject>();
  private listeners = new Set<() => void>();
  private epoch = 0;
  private searches = new Map<string, Promise<unknown>>();
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => this.listeners.delete(listener); };
  snapshot = () => this.epoch;
  changed = () => { this.epoch++; this.listeners.forEach((listener) => listener()); };
  project(id: string) {
    let value = this.projects.get(id);
    if (!value) {
      value = { id, token: '', docs: [], active: '', trees: new Map(), expanded: new Set(['']), loading: new Set(),
        pending: remembered(id), working: false, error: '', notice: '', initialized: false, deleted: false, generation: 0 };
      this.projects.set(id, value);
    }
    return value;
  }
  hasUnsaved = () => [...this.projects.values()].some((p) => p.pending || p.docs.some(dirty));
  hasWorking = () => [...this.projects.values()].some((p) => p.working);
  private request<T>(p: EditorProject, path: string, method = 'GET', body?: unknown) {
    return projectRequest<T>(`/${p.id}/editor${path}`, p.token, method, body);
  }
  search(id: string, input: EditorSearchInput, active: () => boolean) {
    const previous = this.searches.get(id) ?? Promise.resolve();
    const next = previous.catch(() => undefined).then(() => active() ? this.request<EditorSearchResult>(this.project(id), '/search', 'POST', input) : undefined);
    this.searches.set(id, next);
    void next.finally(() => { if (this.searches.get(id) === next) this.searches.delete(id); }).catch(() => undefined);
    return next;
  }
  activate(id: string, token: string) {
    const p = this.project(id); p.token = token;
    if (!token || p.initialized) return;
    p.initialized = true;
    void this.loadTree(id, ''); void this.refreshStatus(id);
  }
  refresh(id: string) {
    const p = this.project(id); p.error = ''; this.changed();
    for (const path of p.expanded) void this.loadTree(id, path);
    void this.refreshStatus(id);
  }
  async refreshStatus(id: string) {
    const p = this.project(id);
    if (!p.token || p.deleted || p.working || p.loading.has('status')) return;
    p.loading.add('status');
    const generation = p.generation, docs = p.docs.map((doc) => ({ doc, file: doc.file }));
    try {
      const status = await this.request<EditorStatus>(p, '/status', 'POST', { paths: docs.map(({ doc }) => doc.path) });
      if (p.deleted || p.working || p.generation !== generation) return;
      p.status = status; p.accessError = '';
      for (const { doc, file } of docs) {
        if (!p.docs.includes(doc) || doc.file !== file) continue;
        const current = status.files.find((entry) => entry.path === doc.path);
        if (current) doc.external = current.revision !== file.revision || current.kind !== file.kind ? current : undefined;
      }
    } catch (error) { if (p.generation === generation && !p.deleted) { p.status = undefined; p.accessError = (error as Error).message; } }
    finally { p.loading.delete('status'); this.changed(); }
  }
  async loadTree(id: string, path: string, more = false) {
    const p = this.project(id);
    if (p.loading.has('tree:' + path) || p.deleted) return;
    p.loading.add('tree:' + path); this.changed();
    try {
      const old = p.trees.get(path);
      const query = new URLSearchParams({ path });
      if (more && old?.nextOffset != null) { query.set('offset', String(old.nextOffset)); query.set('revision', old.revision); }
      const result = await this.request<EditorTree>(p, '/tree?' + query);
      if (p.deleted) return;
      p.trees.set(path, more && old ? { ...result, entries: [...old.entries, ...result.entries] } : result);
    } catch (error) { p.error = (error as Error).message; }
    finally { p.loading.delete('tree:' + path); this.changed(); }
  }
  select(id: string, entry: EditorNode) { this.project(id).selection = entry; this.changed(); }
  toggle(id: string, entry: EditorNode) {
    const p = this.project(id); p.selection = entry;
    if (p.expanded.has(entry.path)) p.expanded.delete(entry.path);
    else { p.expanded.add(entry.path); if (!p.trees.has(entry.path)) void this.loadTree(id, entry.path); }
    this.changed();
  }
  async open(id: string, path: string, line?: number, expectedRevision?: string) {
    const p = this.project(id);
    const existing = p.docs.find((doc) => doc.path === path);
    if (existing) {
      p.active = path;
      if (expectedRevision) {
        try {
          const current = await this.current(id, path);
          if (p.deleted || !p.docs.includes(existing)) return;
          existing.external = current.revision !== existing.file.revision || current.kind !== existing.file.kind ? current : undefined;
          if (dirty(existing) || existing.external || expectedRevision !== current.revision) {
            p.notice = 'Search uses saved files. The open draft is kept; review its current contents.'; this.goto(existing);
          } else this.goto(existing, line);
        } catch (error) { p.error = (error as Error).message; }
      } else this.goto(existing, line);
      this.changed(); return;
    }
    if (p.loading.has('file:' + path) || p.deleted) return;
    if ([...this.projects.values()].reduce((n, item) => n + item.docs.length + [...item.loading].filter((key) => key.startsWith('file:')).length, 0) >= 20) { p.error = 'Close a file before opening more than 20 documents.'; this.changed(); return; }
    p.loading.add('file:' + path); p.error = ''; this.changed();
    try {
      const file = await this.request<EditorNode>(p, '/file?' + new URLSearchParams({ path }));
      if (file.kind === 'missing') throw new Error(file.reason);
      const { createDocument } = await import('./model');
      const doc = await createDocument(id, file);
      if (p.deleted) return;
      if (!p.docs.some((item) => item.path === path)) p.docs.push(doc);
      p.active = path; p.selection = file;
      if (expectedRevision && expectedRevision !== file.revision) { p.notice = 'This file changed since the search. Showing its current version.'; this.goto(doc); }
      else this.goto(doc, line);
    } catch (error) { p.error = (error as Error).message; }
    finally { p.loading.delete('file:' + path); this.changed(); }
  }
  private goto(doc: EditorDocument, line?: number) {
    doc.navigation = { line };
  }
  navigated(doc: EditorDocument, navigation: EditorDocument['navigation']) {
    if (doc.navigation === navigation) doc.navigation = undefined;
  }
  state(doc: EditorDocument, state: EditorState) { doc.state = state; this.changed(); }
  focus(id: string, path: string) { this.project(id).active = path; this.changed(); }
  close(id: string, path: string) {
    const p = this.project(id); p.docs = p.docs.filter((doc) => doc.path !== path);
    if (p.active === path) p.active = p.docs.at(-1)?.path ?? '';
    this.changed();
  }
  async reload(id: string, path: string) {
    const p = this.project(id), old = p.docs.find((doc) => doc.path === path);
    if (!old || p.working || p.pending || p.loading.has('reload:' + path)) return;
    const draft = old.state.doc;
    p.loading.add('reload:' + path); this.changed();
    try {
      const file = await this.request<EditorNode>(p, '/file?' + new URLSearchParams({ path }));
      if (file.kind === 'missing') { old.external = file; throw new Error(file.reason); }
      const { createDocument } = await import('./model');
      const doc = await createDocument(id, file);
      if (p.deleted || !p.docs.includes(old)) return;
      if (!old.state.doc.eq(draft)) { old.external = file; throw new Error('The draft changed while reloading. Its text was preserved.'); }
      p.docs = p.docs.map((item) => item === old ? doc : item);
      p.error = '';
    } catch (error) { p.error = (error as Error).message; }
    finally { p.loading.delete('reload:' + path); this.changed(); }
  }
  async current(id: string, path: string) {
    return this.request<EditorNode>(this.project(id), '/file?' + new URLSearchParams({ path }));
  }
  async saveAs(id: string, doc: EditorDocument, path: string) {
    if (!doc.file.editable || !doc.file.format || doc.file.format.eol === 'mixed') return false;
    return this.mutate(id, { kind: 'create', path, text: doc.state.doc.toString(), format: doc.file.format });
  }
  async save(id: string, doc: EditorDocument) {
    if (doc.external || !dirty(doc) || !doc.file.editable || !doc.file.revision || !doc.file.sha256 || !doc.file.format) return false;
    return this.mutate(id, { kind: 'save', path: doc.path, text: doc.state.doc.toString(), format: doc.file.format,
      expected: { revision: doc.file.revision, sha256: doc.file.sha256 } });
  }
  async mutate(id: string, input: Omit<EditorMutation, 'requestId'>) {
    const p = this.project(id);
    if (p.working || p.pending || !p.status?.writable || p.deleted) return false;
    if (input.kind === 'create' && p.docs.some((doc) => doc.path === input.path)) {
      p.error = 'Close the existing editor draft for this path before creating a file there.'; this.changed(); return false;
    }
    if (input.kind === 'rename' && input.target) {
      const moved = p.docs.filter((doc) => doc.path === input.path || doc.path.startsWith(input.path + '/'));
      if (moved.some((doc) => p.docs.some((other) => !moved.includes(other) && other.path === input.target + doc.path.slice(input.path.length)))) {
        p.error = 'Close the editor draft at the destination before renaming this entry.'; this.changed(); return false;
      }
    }
    if (input.text !== undefined) {
      const encoded = (input.format?.bom ? '\ufeff' : '') + (input.format?.eol === 'crlf' ? input.text.replaceAll('\n', '\r\n') : input.text);
      if (new TextEncoder().encode(encoded).length > 524288) { p.error = 'The document exceeds the 512 KiB UTF-8 limit.'; this.changed(); return false; }
    }
    const value: Pending = { body: { ...input, requestId: projectRequestId() },
      documents: p.docs.map((doc) => ({ path: doc.path, revision: doc.file.revision })) };
    try { sessionStorage.setItem(pendingKey(id), JSON.stringify(value)); }
    catch { p.error = 'The operation could not be retained. Enable browser session storage and retry.'; this.changed(); return false; }
    p.pending = value;
    return this.send(p);
  }
  async retry(id: string) {
    const p = this.project(id);
    if (!p.pending || p.working) return false;
    return this.send(p, true);
  }
  private async send(p: EditorProject, reconcile = false) {
    const pending = p.pending;
    if (!pending) return false;
    p.working = true; p.generation++; p.error = ''; p.notice = ''; this.changed();
    try {
      let result: EditorReceipt | undefined;
      if (reconcile) result = await this.request<EditorReceipt>(p, '/operations/' + pending.body.requestId);
      if (result?.state === 'missing' && result.requestId === pending.body.requestId && pending.initialRejection) {
        this.clearPending(p); throw new Error(pending.initialRejection);
      }
      if (!result || result.state === 'missing' || result.state === 'unknown')
        result = await this.request<EditorReceipt>(p, '/mutations', 'POST', pending.body);
      if (result.requestId !== pending.body.requestId) throw new Error('The operation receipt identity changed.');
      if (result.state === 'unknown' || result.state === 'missing') throw new Error(result.message ?? 'The operation result is unknown. Retry the retained request.');
      this.clearPending(p);
      if (result.state === 'rejected') throw new Error(result.message ?? 'The entry changed. Reload or compare its current version.');
      await this.applied(p, pending, result, reconcile);
      p.notice = pending.body.kind === 'save' ? 'Saved.' : 'Done.';
      return true;
    } catch (error) {
      // An explicit initial 4xx response plus a missing journal proves this
      // request ended before publication. Lost responses remain pending.
      if (!reconcile && error instanceof ProjectRequestError && error.status >= 400 && error.status < 500) {
        pending.initialRejection = error.message;
        try { sessionStorage.setItem(pendingKey(p.id), JSON.stringify(pending)); } catch { /* Keep the original request in memory. */ }
        try {
          const receipt = await this.request<EditorReceipt>(p, '/operations/' + pending.body.requestId);
          if (receipt.requestId === pending.body.requestId && (receipt.state === 'missing' || receipt.state === 'rejected')) this.clearPending(p);
        } catch { /* An unavailable receipt cannot prove rejection. */ }
      }
      p.error = (error as Error).message; return false;
    }
    finally {
      p.working = false; p.generation++; this.changed();
      if (!p.deleted) { void this.refreshStatus(p.id); for (const path of p.expanded) void this.loadTree(p.id, path); }
    }
  }
  private clearPending(p: EditorProject) {
    p.pending = undefined;
    try { sessionStorage.removeItem(pendingKey(p.id)); } catch { /* Completed server receipts remain idempotent. */ }
  }
  private async applied(p: EditorProject, pending: Pending, result: EditorReceipt, reconcile: boolean) {
    const input = pending.body;
    if (input.kind === 'save') {
      const doc = p.docs.find((item) => item.path === input.path);
      if (doc) {
        if (reconcile) {
          const current = await this.request<EditorNode>(p, '/file?' + new URLSearchParams({ path: input.path }));
          if (current.text !== input.text || current.format?.bom !== input.format?.bom || current.format?.eol !== input.format?.eol) { doc.external = current; return; }
          doc.file = current;
        } else doc.file = { ...doc.file, ...result.node, text: input.text };
        const { EditorState } = await import('@codemirror/state');
        doc.baseText = EditorState.create({ doc: input.text ?? '' }).doc; doc.external = undefined;
      }
    } else if (input.kind === 'rename' && input.target) {
      const target = input.target;
      for (const doc of p.docs) if (doc.path === input.path || doc.path.startsWith(input.path + '/')) {
        const recorded = pending.documents?.find((item) => item.path === doc.path);
        if (reconcile && (!recorded || recorded.revision !== doc.file.revision)) continue;
        const destination = target + doc.path.slice(input.path.length);
        if (p.docs.some((other) => other !== doc && other.path === destination)) continue;
        const exact = doc.path === input.path;
        const oldPath = doc.path;
        doc.path = target + doc.path.slice(input.path.length); doc.file = { ...doc.file, path: doc.path, name: doc.path.split('/').at(-1)! };
        if (exact && result.node) doc.file.revision = result.node.revision;
        const { languageFor } = await import('./languages');
        doc.state = doc.state.update({ effects: doc.language.reconfigure(await languageFor(doc.path)) }).state;
        if (p.active === oldPath) p.active = doc.path;
      }
      p.trees.clear(); p.expanded = new Set(['']); p.selection = undefined;
    } else if (input.kind === 'delete') {
      p.docs = p.docs.filter((doc) => {
        if (doc.path !== input.path && !doc.path.startsWith(input.path + '/')) return true;
        const recorded = pending.documents?.find((item) => item.path === doc.path);
        return reconcile && (!recorded || recorded.revision !== doc.file.revision);
      });
      if (!p.docs.some((doc) => doc.path === p.active)) p.active = p.docs.at(-1)?.path ?? '';
      p.trees.delete(input.path); p.expanded.delete(input.path); p.selection = undefined;
    } else if (input.kind === 'create') await this.open(p.id, input.path);
  }
  forget(id: string) {
    const p = this.projects.get(id);
    if (p) { p.deleted = true; p.docs = []; p.pending = undefined; }
    try { sessionStorage.removeItem(pendingKey(id)); } catch { /* Deletion does not depend on browser storage. */ }
    this.projects.delete(id); this.changed();
  }
}
export const editorRegistry = new EditorRegistry();
