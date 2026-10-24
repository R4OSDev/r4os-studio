import { useState } from 'react';
import { EditorCore } from './EditorCore';
import { dirty, editorRegistry } from './registry';
import type { EditorDocument } from './model';
import { useEditorProject } from './useEditorProject';
import { EditorDialog } from './EditorDialog';

export default function EditorPanel({ id, token }: { id: string; token: string }) {
  const p = useEditorProject(id, token);
  const doc = p.docs.find((item) => item.path === p.active);
  const [closing, setClosing] = useState<EditorDocument | null>(null);
  const writable = !!p.status?.writable && !p.pending && !p.working;
  function close(item: EditorDocument) {
    if (p.working || p.pending) return;
    if (dirty(item)) setClosing(item); else editorRegistry.close(id, item.path);
  }
  return <section className="editor-panel" aria-label="Project source editor">
    <div className="editor-tabs" role="tablist" aria-label="Open files">{p.docs.map((item) => <div className="editor-tab-group" key={item.path}>
      <button type="button" role="tab" aria-selected={doc === item} className={doc === item ? 'selected' : ''} title={item.path}
        onClick={() => editorRegistry.focus(id, item.path)}>{item.path}{dirty(item) && <span aria-label="Unsaved changes"> ●</span>}</button>
      <button type="button" aria-label={`Close ${item.path}`} disabled={p.working || !!p.pending} onClick={() => close(item)}>×</button>
    </div>)}</div>
    <div className="editor-toolbar"><span>{doc?.path ?? 'Editor'}</span>
      {doc && <><button type="button" disabled={p.working || !!p.pending} onClick={() => {
        if (!dirty(doc) || window.confirm('Reload this file and discard its unsaved changes?')) void editorRegistry.reload(id, doc.path);
      }}>Reload</button><button type="button" disabled={!writable || !doc.file.editable || !dirty(doc)} onClick={() => void editorRegistry.save(id, doc)}>Save</button></>}
    </div>
    {(p.error || p.notice || p.status?.reason) && <div className={p.error ? 'editor-message error' : 'editor-message'} role={p.error ? 'alert' : 'status'}>{p.error || p.status?.reason || p.notice}</div>}
    {p.pending && <div className="editor-message" role="status">{p.working ? 'Saving operation…' : `Unconfirmed ${p.pending.body.kind}: ${p.pending.body.path}`}
      {!p.working && <button type="button" onClick={() => void editorRegistry.retry(id)}>Retry operation</button>}</div>}
    {doc ? 'text' in doc.file ? <EditorCore key={id + ':' + doc.path} doc={doc} readOnly={!writable || !doc.file.editable}
      onState={(state) => editorRegistry.state(doc, state)} save={() => { if (writable) void editorRegistry.save(id, doc); }} />
      : <div className="editor-empty">{doc.file.reason ?? 'This file is unavailable for text editing.'}</div>
      : <div className="editor-empty">{p.loading.size ? 'Loading…' : 'Open a file from Files.'}</div>}
    {closing && <EditorDialog label="Unsaved file changes" busy={p.working} close={() => setClosing(null)}>
        <h2>Save changes?</h2><p>{closing.path}</p><div className="editor-dialog-actions">
          <button type="button" disabled={p.working} onClick={() => setClosing(null)}>Cancel</button>
          <button type="button" disabled={p.working} onClick={() => { editorRegistry.close(id, closing.path); setClosing(null); }}>Discard</button>
          <button type="button" disabled={!writable} onClick={async () => { if (await editorRegistry.save(id, closing)) { editorRegistry.close(id, closing.path); setClosing(null); } }}>Save</button>
        </div>
    </EditorDialog>}
  </section>;
}
