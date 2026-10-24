import { useEffect, useState } from 'react';
import { EditorCore } from './EditorCore';
import { dirty, editorRegistry } from './registry';
import type { EditorDocument } from './model';
import { useEditorProject } from './useEditorProject';
import { EditorDialog } from './EditorDialog';
import { EditorCompare, EditorSaveAs } from './EditorConflict';

export default function EditorPanel({ id, token }: { id: string; token: string }) {
  const p = useEditorProject(id, token);
  const doc = p.docs.find((item) => item.path === p.active);
  const [closing, setClosing] = useState<EditorDocument | null>(null);
  const [modal, setModal] = useState<'compare' | 'saveAs' | null>(null);
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible') void editorRegistry.refreshStatus(id); };
    refresh();
    const timer = window.setInterval(refresh, 5000);
    window.addEventListener('focus', refresh); document.addEventListener('visibilitychange', refresh);
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh); document.removeEventListener('visibilitychange', refresh); };
  }, [id, token]);
  const writable = !!p.status?.writable && !p.pending && !p.working;
  function close(item: EditorDocument) {
    if (p.working || p.pending || p.loading.has('reload:' + item.path)) return;
    if (dirty(item)) setClosing(item); else editorRegistry.close(id, item.path);
  }
  return <section className="editor-panel" aria-label="Project source editor">
    <div className="editor-tabs" role="tablist" aria-label="Open files" onKeyDown={(event) => {
      if (!(event.target instanceof HTMLElement) || event.target.getAttribute('role') !== 'tab' || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      const tabs = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
      const index = tabs.indexOf(event.target as HTMLButtonElement);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      event.preventDefault(); tabs[next]?.click(); tabs[next]?.focus();
    }}>{p.docs.map((item) => <div className="editor-tab-group" key={item.path} role="presentation">
      <button type="button" role="tab" tabIndex={doc === item ? 0 : -1} aria-selected={doc === item} className={doc === item ? 'selected' : ''} title={item.path}
        onClick={() => editorRegistry.focus(id, item.path)}>{item.path}{dirty(item) && <span aria-label="Unsaved changes"> ●</span>}</button>
      <button type="button" aria-label={`Close ${item.path}`} disabled={p.working || !!p.pending || p.loading.has('reload:' + item.path)} onClick={() => close(item)}>×</button>
    </div>)}</div>
    <div className="editor-toolbar"><span>{doc?.path ?? 'Editor'}</span>
      {doc && <><button type="button" disabled={p.working || !!p.pending || p.loading.has('reload:' + doc.path)} onClick={() => {
        if (!dirty(doc) || window.confirm('Reload this file and discard its unsaved changes?')) void editorRegistry.reload(id, doc.path);
      }}>Reload</button><button type="button" disabled={!writable || !doc.file.editable} onClick={() => setModal('saveAs')}>Save as</button>
        <button type="button" disabled={!writable || !doc.file.editable || !!doc.external || !dirty(doc)} onClick={() => void editorRegistry.save(id, doc)}>Save</button></>}
    </div>
    {(p.error || p.accessError || p.notice || p.status?.reason) && <div className={p.error || p.accessError ? 'editor-message error' : 'editor-message'} role={p.error || p.accessError ? 'alert' : 'status'}>{p.error || p.accessError || p.status?.reason || p.notice}</div>}
    {doc?.external && <div className="editor-message editor-conflict" role="status">{doc.external.kind === 'missing' ? 'This file is no longer on disk. Your draft is kept.' : 'This file changed on disk. Your editor text is kept.'}
      <button type="button" onClick={() => setModal('compare')}>Compare</button></div>}
    {p.pending && <div className="editor-message" role="status">{p.working ? 'Saving operation…' : `Unconfirmed ${p.pending.body.kind}: ${p.pending.body.path}`}
      {!p.working && <button type="button" onClick={() => void editorRegistry.retry(id)}>Retry operation</button>}</div>}
    {doc ? 'text' in doc.file ? <EditorCore key={id + ':' + doc.path} doc={doc} readOnly={!doc.file.editable || p.loading.has('reload:' + doc.path)}
      onState={(state) => editorRegistry.state(doc, state)} save={() => { if (writable) void editorRegistry.save(id, doc); }} />
      : <div className="editor-empty">{doc.file.reason ?? 'This file is unavailable for text editing.'}</div>
      : <div className="editor-empty">{p.loading.size ? 'Loading…' : 'Open a file from Files.'}</div>}
    {closing && <EditorDialog label="Unsaved file changes" busy={p.working} close={() => setClosing(null)}>
        <h2>Save changes?</h2><p>{closing.path}</p><div className="editor-dialog-actions">
          <button type="button" disabled={p.working} onClick={() => setClosing(null)}>Cancel</button>
          <button type="button" disabled={p.working} onClick={() => { editorRegistry.close(id, closing.path); setClosing(null); }}>Discard</button>
          <button type="button" disabled={!writable || !!closing.external || !closing.file.editable} onClick={async () => { if (await editorRegistry.save(id, closing) && !dirty(closing)) { editorRegistry.close(id, closing.path); setClosing(null); } }}>Save</button>
        </div>
    </EditorDialog>}
    {modal === 'compare' && doc && <EditorCompare id={id} doc={doc} close={() => setModal(null)} />}
    {modal === 'saveAs' && doc && <EditorSaveAs id={id} doc={doc} close={() => setModal(null)} />}
  </section>;
}
