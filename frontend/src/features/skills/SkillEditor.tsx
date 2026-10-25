import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import type { Skill, SkillDetail, SkillFileContent, SkillValidation } from '../../../../shared/skills';
import { EditorCore } from '../project-editor/EditorCore';
import { createDocument, isDirty } from '../project-editor/model';
import type { EditorDocument } from '../project-editor/model';
import { EditorDialog } from '../project-editor/EditorDialog';
import { MessageText } from '../agent-sessions/Transcript';
import { request } from './api';

type Action = 'new' | 'rename' | 'upload' | null;
export default function SkillEditor({ id, token, remembered, setLeaveGuard, refreshAuth }: {
  id: string; token: string; remembered: (skill: Skill) => void; setLeaveGuard: (guard: () => boolean) => void; refreshAuth: () => Promise<void>;
}) {
  const [detail, setDetail] = useState<SkillDetail>(), [documents, setDocuments] = useState<Record<string, EditorDocument>>({});
  const [active, setActive] = useState('SKILL.md'), [name, setName] = useState(''), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [validation, setValidation] = useState<SkillValidation>();
  const [preview, setPreview] = useState(false), [action, setAction] = useState<Action>(null), [path, setPath] = useState('');
  const [upload, setUpload] = useState<File | null>(null), [epoch, setEpoch] = useState(0);
  const [dialogDirty, setDialogDirty] = useState(false);
  const [executable, setExecutable] = useState<Record<string, boolean>>({});
  const [, changed] = useReducer((n: number) => n + 1, 0);
  const saveId = useRef<{ hash: string; revision: number; id: string } | undefined>(undefined);
  const opening = useRef('SKILL.md');
  const doc = documents[active];
  const textDirty = Object.values(documents).some(isDirty);
  const dirty = dialogDirty || textDirty || (!!detail && name !== detail.skill.name) || Object.entries(executable).some(([p, v]) => detail?.files.find(f => f.path === p)?.executable !== v);
  const guard = useCallback(() => !busy && (!dirty || window.confirm('Discard unsaved skill edits?')), [busy, dirty]);
  useEffect(() => { setLeaveGuard(guard); return () => setLeaveGuard(() => true); }, [guard, setLeaveGuard]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty || busy) event.preventDefault(); };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [dirty, busy]);
  useEffect(() => {
    let cancelled = false;
    void request<SkillDetail>('GET', '/' + id).then(async (value) => {
      const file = value.files.find(f => f.path === 'SKILL.md') ?? value.files[0];
      let initial: EditorDocument | undefined;
      if (file) initial = await documentFor(file.path);
      if (!cancelled) { setDetail(value); setName(value.skill.name); setDocuments(initial ? { [initial.path]: initial } : {});
        setActive(initial?.path ?? 'SKILL.md'); setExecutable({}); setError(''); setValidation(undefined); }
    }).catch((cause: Error) => { if (!cancelled) setError(cause.message); });
    return () => { cancelled = true; };
    // Selection lifetime is the skill id. The request uses no mutation credentials.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, epoch]);
  async function documentFor(filePath: string) {
    const file = await request<SkillFileContent>('GET', '/' + id + '/file?path=' + encodeURIComponent(filePath));
    const editable = file.encoding === 'utf8' && file.content.length <= 524288;
    return createDocument('skill:' + id, { path: file.path, name: file.path.split('/').at(-1)!, kind: 'file', editable,
      bytes: file.bytes, sha256: file.sha256, text: file.encoding === 'utf8' ? file.content : '', format: { bom: false, eol: 'lf' },
      ...(!editable ? { reason: 'This file is available for download or replacement.' } : {}) });
  }
  async function open(filePath: string) {
    if (busy) return;
    opening.current = filePath;
    setError('');
    try {
      if (!documents[filePath]) { const value = await documentFor(filePath); setDocuments(previous => ({ ...previous, [filePath]: value })); }
      if (opening.current === filePath) setActive(filePath);
    } catch (cause) { setError((cause as Error).message); }
  }
  function cancel() {
    for (const value of Object.values(documents)) value.state = value.state.update({ changes: { from: 0, to: value.state.doc.length, insert: value.baseText } }).state;
    setName(detail?.skill.name ?? ''); setExecutable({}); setError(''); setNotice(''); changed();
  }
  async function save() {
    if (busy || !detail) return;
    setBusy(true); setError(''); setNotice('');
    try {
      let next = detail;
      for (const value of Object.values(documents)) {
        const exec = executable[value.path] ?? next.files.find(f => f.path === value.path)?.executable ?? false;
        if (!isDirty(value) && exec === next.files.find(f => f.path === value.path)?.executable) continue;
        next = await request<SkillDetail>('PUT', '/' + id + '/file', { path: value.path, content: value.state.doc.toString(), encoding: 'utf8',
          sha256: value.file.sha256 ?? null, executable: exec }, token);
        value.file = { ...value.file, sha256: next.files.find(f => f.path === value.path)?.sha256 }; value.baseText = value.state.doc;
        setDetail(next); changed();
      }
      if (name !== next.skill.name) next = await request<SkillDetail>('PATCH', '/' + id, { revision: next.skill.revision, name }, token);
      setDetail(next); remembered(next.skill); setExecutable({});
      if (!saveId.current || saveId.current.hash !== next.draftHash || saveId.current.revision !== next.skill.revision) saveId.current = { hash: next.draftHash, revision: next.skill.revision, id: crypto.randomUUID() };
      const result = await request<SkillDetail & { saved: boolean; validation: SkillValidation }>('POST', '/' + id + '/save',
        { revision: next.skill.revision, draftHash: next.draftHash, requestId: saveId.current.id }, token);
      setDetail(result); remembered(result.skill); setValidation(result.validation);
      setNotice(result.saved ? 'Skill saved. A valid revision is active.' : 'Draft saved. Fix validation errors to activate it; the previous valid revision is unchanged.');
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  async function fileAction() {
    if (busy || !detail || !action) return;
    setBusy(true); setError('');
    try {
      let next: SkillDetail;
      if (action === 'rename') {
        if (!doc) throw new Error('Select a file before renaming.');
        next = await request('POST', '/' + id + '/file/rename', { path: active, destination: path, sha256: doc.file.sha256 }, token);
        setDocuments(previous => { const copy = { ...previous }; delete copy[active]; return copy; });
      } else {
        let content = '', encoding = 'utf8';
        if (upload) {
          if (upload.size > 1024 * 1024) throw new Error('Files must be at most 1 MiB.');
          const bytes = new Uint8Array(await upload.arrayBuffer());
          if (path.startsWith('assets/')) { encoding = 'base64'; content = btoa(Array.from(bytes, b => String.fromCharCode(b)).join('')); }
          else content = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
        }
        next = await request('PUT', '/' + id + '/file', { path, content, encoding, sha256: action === 'upload' ? detail.files.find(f => f.path === path)?.sha256 ?? null : null,
          executable: action === 'upload' ? detail.files.find(f => f.path === path)?.executable ?? false : false }, token);
      }
      const value = await documentFor(path); setDocuments(previous => ({ ...previous, [path]: value })); setActive(path); setDetail(next); setAction(null); setDialogDirty(false);
      setNotice('File updated in the draft. Save the skill to activate a valid revision.');
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (!detail || !doc || busy || dirty || !window.confirm(`Remove “${active}” from the draft? The active revision stays intact until Save.`)) return;
    setBusy(true); setError('');
    try {
      const value = await request<SkillDetail>('DELETE', '/' + id + '/file', { path: active, sha256: doc.file.sha256 }, token);
      setDocuments(previous => { const copy = { ...previous }; delete copy[active]; return copy; }); setDetail(value);
      const next = value.files[0]?.path; setActive(next ?? 'SKILL.md');
      if (next && !documents[next]) { const loaded = await documentFor(next); setDocuments(previous => ({ ...previous, [next]: loaded })); }
      setNotice('File removed from the draft. Save to activate the change.');
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  async function download() {
    try {
      const file = await request<SkillFileContent>('GET', '/' + id + '/file?path=' + encodeURIComponent(active));
      const bytes = file.encoding === 'utf8' ? new TextEncoder().encode(file.content) : Uint8Array.from(atob(file.content), c => c.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes])); const link = document.createElement('a'); link.href = url; link.download = active.split('/').at(-1)!; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) { setError((cause as Error).message); }
  }
  async function reload() {
    if (!guard()) return;
    setBusy(true);
    try { await refreshAuth(); setEpoch(n => n + 1); }
    finally { setBusy(false); }
  }
  return <section className="skill-editor" aria-label="View skill">
    <div className="skill-heading"><label htmlFor="skill-display-name">Skill name</label><input id="skill-display-name" value={name} maxLength={120} disabled={busy || !detail} onChange={event => setName(event.target.value)} />
      <p>{detail?.skill.activeRevision ? `Active revision ${detail.skill.activeRevision}` : 'Draft · no active revision'}{detail && detail.draftHash !== detail.skill.activeHash ? ' · draft differs' : ''}</p></div>
    {error && <div className="skill-message error" role="alert">{error}<button type="button" disabled={busy} onClick={() => void reload()}>Reload</button></div>}
    {notice && <p className="skill-message" role="status">{notice}</p>}
    {validation && !validation.valid && <ul className="skill-message error" role="alert">{validation.errors.map((message, i) => <li key={i}>{message}</li>)}</ul>}
    {!detail && !error && <p className="skill-empty">Loading skill…</p>}
    {detail && <><div className="skill-toolbar"><label htmlFor="skill-file">File</label>
      <select id="skill-file" value={active} disabled={busy || !detail.files.length} onChange={event => void open(event.target.value)}>
        {detail.files.map(file => <option key={file.path} value={file.path}>{file.path}{documents[file.path] && isDirty(documents[file.path]) ? ' ●' : ''}</option>)}
      </select>
      <button type="button" disabled={busy} onClick={() => { setPath('scripts/helper.py'); setUpload(null); setAction('new'); }}>New file</button>
      <button type="button" disabled={busy || dirty} onClick={() => { setPath(active); setUpload(null); setAction('upload'); }}>Upload / replace</button>
      <button type="button" disabled={busy || dirty || !doc} onClick={() => { setPath(active); setAction('rename'); }}>Rename</button>
      <button type="button" disabled={busy || dirty || !doc} onClick={() => void remove()}>Remove file</button>
      <button type="button" disabled={busy || !doc} onClick={() => void download()}>Download</button>
      <button type="button" disabled={!doc || !active.endsWith('.md')} aria-pressed={preview} onClick={() => setPreview(v => !v)}>{preview ? 'Edit source' : 'Preview'}</button>
      {doc?.file.editable && active.startsWith('scripts/') && <label className="skill-executable"><input type="checkbox" disabled={busy}
        checked={executable[active] ?? detail.files.find(f => f.path === active)?.executable ?? false}
        onChange={event => setExecutable(previous => ({ ...previous, [active]: event.target.checked }))} />Executable</label>}
    </div>
    {doc ? preview && active.endsWith('.md') ? <div className="skill-preview" onClick={event => {
      const anchor = event.target instanceof Element ? event.target.closest('a') : null;
      const href = anchor?.getAttribute('href');
      if (!href || /^(https?:|mailto:)/i.test(href)) return;
      event.preventDefault();
      try {
        const resource = decodeURIComponent(href.split('#')[0]).replace(/^\.\//, '');
        if (resource && detail.files.some(file => file.path === resource)) void open(resource);
        else if (resource) setError('This resource is not in the skill package.');
      } catch { setError('Invalid resource link.'); }
    }}><MessageText text={doc.state.doc.toString()} markdown /></div>
      : doc.file.editable ? <EditorCore doc={doc} readOnly={busy} save={() => void save()} onState={state => { doc.state = state; changed(); }} navigated={() => {}} />
        : <p className="skill-empty">{doc.file.reason}</p> : <p className="skill-empty">Create or select a package file.</p>}
    <div className="skill-actions"><button type="button" disabled={busy || !dirty} onClick={cancel}>Cancel edits</button>
      <button type="button" disabled={busy || (!dirty && detail.draftHash === detail.skill.activeHash)} onClick={() => void save()}>{busy ? 'Saving…' : 'Save skill'}</button></div>
    </>}
    {action && <EditorDialog label={action === 'rename' ? 'Rename skill file' : action === 'upload' ? 'Upload skill file' : 'New skill file'} busy={busy} close={() => { setAction(null); setDialogDirty(false); }}>
      <form onSubmit={event => { event.preventDefault(); void fileAction(); }}><h2>{action === 'rename' ? 'Rename file' : action === 'upload' ? 'Upload resource' : 'New file'}</h2>
        <label htmlFor="skill-file-path">Package path</label><input id="skill-file-path" value={path} maxLength={240} required disabled={busy} onChange={event => { setPath(event.target.value); setDialogDirty(true); }} />
        <p>Use SKILL.md, scripts/, references/, assets/ or agents/. File operations update the draft.</p>
        {action === 'upload' && <input type="file" aria-label="Resource file" required disabled={busy} onChange={event => { setUpload(event.target.files?.[0] ?? null); setDialogDirty(true); }} />}
        {error && <p role="alert">{error}</p>}
        <div className="editor-dialog-actions"><button type="button" disabled={busy} onClick={() => { setAction(null); setDialogDirty(false); }}>Cancel</button><button type="submit" disabled={busy || !path}>{busy ? 'Updating…' : 'Update draft'}</button></div>
      </form>
    </EditorDialog>}
  </section>;
}
