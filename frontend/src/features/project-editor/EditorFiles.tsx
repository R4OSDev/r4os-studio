import { useState } from 'react';
import type { ReactNode } from 'react';
import type { EditorNode, EditorMutation } from '../../../../shared/project-editor';
import { editorRegistry, dirty } from './registry';
import { useEditorProject } from './useEditorProject';
import { EditorDialog } from './EditorDialog';
import './styles.css';

type Action = { kind: 'create' | 'mkdir' | 'rename' | 'delete'; entry?: EditorNode };
const parentPath = (path: string) => path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '';
export default function EditorFiles({ id, token }: { id: string; token: string }) {
  const p = useEditorProject(id, token);
  const [action, setAction] = useState<Action | null>(null), [name, setName] = useState('');
  const [error, setError] = useState('');
  const blocked = !p.status?.writable || p.working || !!p.pending;
  function begin(kind: Action['kind']) {
    const entry = p.selection;
    setAction({ kind, entry }); setError('');
    const prefix = entry ? (entry.kind === 'directory' ? entry.path : parentPath(entry.path)) : '';
    setName(kind === 'rename' ? entry?.path ?? '' : prefix ? prefix + '/' : '');
  }
  async function submit() {
    if (!action || blocked) return;
    const { kind, entry } = action;
    const model = p.docs.find((doc) => doc.path === entry?.path);
    const expected = model?.file.revision ?? entry?.revision;
    let body: Omit<EditorMutation, 'requestId'>;
    if (kind === 'create' || kind === 'mkdir') body = { kind, path: name, ...(kind === 'create' ? { text: '' } : {}) };
    else {
      if (!entry || !expected) return;
      body = { kind, path: entry.path, expected: { revision: expected }, ...(kind === 'rename' ? { target: name } : { confirm: true }) };
    }
    if (await editorRegistry.mutate(id, body)) setAction(null);
    else setError(p.error || 'The operation could not be completed.');
  }
  function children(path: string, depth = 0): ReactNode {
    const tree = p.trees.get(path);
    if (!tree) return <p className="editor-tree-message">{p.loading.has('tree:' + path) ? 'Loading…' : 'No files loaded.'}</p>;
    return <ul className="editor-tree-list">{tree.entries.map((entry) => <li key={entry.path}>
      <button type="button" className={`editor-tree-entry ${p.selection?.path === entry.path ? 'selected' : ''}`} style={{ paddingLeft: 10 + depth * 10 }}
        aria-expanded={entry.kind === 'directory' ? p.expanded.has(entry.path) : undefined} title={entry.reason ?? entry.path}
        disabled={entry.kind !== 'file' && entry.kind !== 'directory'} onClick={() => {
          if (entry.kind === 'directory') editorRegistry.toggle(id, entry);
          else { editorRegistry.select(id, entry); void editorRegistry.open(id, entry.path); }
        }}><span aria-hidden="true">{entry.kind === 'directory' ? p.expanded.has(entry.path) ? '▾' : '▸' : '·'}</span><span>{entry.name}</span></button>
      {entry.kind === 'directory' && p.expanded.has(entry.path) && children(entry.path, depth + 1)}
    </li>)}{tree.nextOffset != null && <li><button type="button" className="editor-tree-more" disabled={p.loading.has('tree:' + path)} onClick={() => void editorRegistry.loadTree(id, path, true)}>Load more</button></li>}</ul>;
  }
  return <nav className="nav-column editor-files" aria-label="Workspace files">
    <div className="column-heading">Files</div>
    <div className="editor-file-actions"><button type="button" disabled={blocked} onClick={() => begin('create')}>New file</button><button type="button" disabled={blocked} onClick={() => begin('mkdir')}>New folder</button>
      <button type="button" disabled={blocked || !p.selection} onClick={() => begin('rename')}>Rename</button><button type="button" disabled={blocked || !p.selection} onClick={() => begin('delete')}>Delete</button>
      <button type="button" onClick={() => editorRegistry.refresh(id)}>Refresh</button></div>
    <div className="editor-tree" onKeyDown={(event) => {
      if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return;
      const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));
      const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
      if (index < 0) return;
      event.preventDefault(); buttons[(index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length]?.focus();
    }}>{children('')}</div>
    {action && <EditorDialog label="Workspace file operation" busy={p.working} close={() => setAction(null)}>
      <form onSubmit={(event) => { event.preventDefault(); void submit(); }}>
        <h2>{({ create: 'New file', mkdir: 'New folder', rename: 'Rename', delete: 'Delete' })[action.kind]}</h2>
        {action.kind === 'delete' ? <p>Delete “{action.entry?.path}”?{p.docs.some((doc) => doc.path === action.entry?.path && dirty(doc)) ? ' Its unsaved editor draft will also be discarded.' : ''} Folders must be empty.</p>
          : <label>Workspace path<input required maxLength={1024} value={name} onChange={(event) => setName(event.target.value)} /></label>}
        {(error || p.error) && <p className="editor-message error" role="alert">{error || p.error}</p>}
        <div className="editor-dialog-actions"><button type="button" disabled={p.working} onClick={() => setAction(null)}>Cancel</button>
          <button type="submit" disabled={blocked}>{p.working ? 'Working…' : action.kind === 'delete' ? 'Delete' : 'Save'}</button></div>
      </form>
    </EditorDialog>}
  </nav>;
}
