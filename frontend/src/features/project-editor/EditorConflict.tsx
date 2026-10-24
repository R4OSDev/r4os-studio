import { useEffect, useState } from 'react';
import type { EditorNode } from '../../../../shared/project-editor';
import type { EditorDocument } from './model';
import { editorRegistry } from './registry';
import { EditorDialog } from './EditorDialog';

export function EditorCompare({ id, doc, close }: { id: string; doc: EditorDocument; close: () => void }) {
  const [disk, setDisk] = useState<EditorNode>(), [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    void editorRegistry.current(id, doc.path).then((file) => { if (active) setDisk(file); })
      .catch((cause: Error) => { if (active) setError(cause.message); });
    return () => { active = false; };
  }, [id, doc.path]);
  return <EditorDialog label="Compare file versions" close={close}>
    <h2>Compare versions</h2><p>{doc.path}</p>
    {error && <p role="alert">{error}</p>}
    <div className="editor-comparison"><section><h3>Editor draft</h3><pre tabIndex={0}>{doc.state.doc.toString()}</pre></section>
      <section><h3>On disk</h3>{disk ? 'text' in disk ? <pre tabIndex={0}>{disk.text}</pre> : <p>{disk.reason ?? 'This file cannot be displayed as text.'}</p> : !error && <p>Loading…</p>}</section></div>
    <div className="editor-dialog-actions"><button type="button" onClick={close}>Close</button></div>
  </EditorDialog>;
}

export function EditorSaveAs({ id, doc, close }: { id: string; doc: EditorDocument; close: () => void }) {
  const p = editorRegistry.project(id);
  const [path, setPath] = useState(doc.path), [error, setError] = useState('');
  return <EditorDialog label="Save file as" close={close} busy={p.working}>
    <form onSubmit={async (event) => {
      event.preventDefault(); setError('');
      if (path === doc.path) { setError('Choose a new Workspace path. Existing files will be kept.'); return; }
      if (await editorRegistry.saveAs(id, doc, path)) close(); else setError(p.error || 'The file could not be saved.');
    }}><h2>Save as</h2><label>Workspace path<input required maxLength={1024} value={path} onChange={(event) => setPath(event.target.value)} /></label>
      {error && <p role="alert" className="editor-message error">{error}</p>}
      <div className="editor-dialog-actions"><button type="button" disabled={p.working} onClick={close}>Cancel</button>
        <button type="submit" disabled={p.working || !!p.pending || !p.status?.writable}>Save</button></div>
    </form>
  </EditorDialog>;
}
