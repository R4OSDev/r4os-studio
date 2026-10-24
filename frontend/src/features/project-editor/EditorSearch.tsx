import { useEffect, useRef, useState } from 'react';
import type { EditorSearchEntry, EditorSearchResult } from '../../../../shared/project-editor';
import { editorRegistry } from './registry';
import { EditorDialog } from './EditorDialog';

export function EditorSearch({ id, mode, close }: { id: string; mode: 'name' | 'content'; close: () => void }) {
  const [query, setQuery] = useState(''), [sensitive, setSensitive] = useState(false);
  const [result, setResult] = useState<{ query: string; sensitive: boolean; value: EditorSearchResult }>();
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [selected, setSelected] = useState(0);
  const current = result?.query === query && result.sensitive === sensitive ? result.value : undefined;
  const entries = current?.entries ?? [];
  const results = useRef<HTMLUListElement>(null);
  useEffect(() => { results.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' }); }, [current, selected]);
  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      setError(''); setSelected(0);
      if (mode === 'content' && !query.trim()) { setBusy(false); return; }
      setBusy(true);
      void editorRegistry.search(id, { mode, query, caseSensitive: sensitive }, () => active)
        .then((value) => { if (active && value) setResult({ query, sensitive, value }); })
        .catch((cause: Error) => { if (active) setError(cause.message); })
        .finally(() => { if (active) setBusy(false); });
    }, 300);
    return () => { active = false; window.clearTimeout(timer); };
  }, [id, mode, query, sensitive]);
  function choose(entry: EditorSearchEntry) { void editorRegistry.open(id, entry.path, entry.line, entry.revision); close(); }
  return <EditorDialog label={mode === 'name' ? 'Quick Open' : 'Search Workspace'} close={close}>
    <form className="editor-search" onSubmit={(event) => { event.preventDefault(); if (entries[selected]) choose(entries[selected]); }} onKeyDown={(event) => {
      if (!['ArrowDown', 'ArrowUp'].includes(event.key) || !entries.length) return;
      event.preventDefault(); setSelected((index) => (index + (event.key === 'ArrowDown' ? 1 : -1) + entries.length) % entries.length);
    }}>
      <h2>{mode === 'name' ? 'Quick Open' : 'Search Workspace'}</h2>
      <label>{mode === 'name' ? 'File name or path' : 'Search text'}<input maxLength={200} value={query} onChange={(event) => setQuery(event.target.value)}
        role="combobox" aria-autocomplete="list" aria-expanded={entries.length > 0} aria-controls="editor-search-results" aria-activedescendant={entries[selected] ? `editor-search-result-${selected}` : undefined} /></label>
      <label className="editor-search-case"><input type="checkbox" checked={sensitive} onChange={(event) => setSensitive(event.target.checked)} />Match case</label>
      {error && <p className="editor-message error" role="alert">{error}</p>}
      <div role="status" className="editor-search-status">{busy || (!current && query && !error) ? 'Searching…' : current ? `${entries.length} results · ${current.scannedFiles} files` : 'Enter text to search.'}
        {current?.incomplete && <p>Results are incomplete: a limit was reached or files changed.</p>}
        {!!current?.skipped && <p>{current.skipped} entries skipped (unsupported, unreadable or changed).</p>}
        {current && <details><summary>Search scope</summary><p>Saved Workspace files. Excluded folders: {current.excludedDirectories.join(', ')}.</p>
          <p>Limits: {current.limits.files} files, {current.limits.entries} entries, {current.limits.bytes / 1048576} MiB, {current.limits.matches} matches, {current.limits.seconds} seconds.</p></details>}
      </div>
      <ul className="editor-search-results" ref={results} id="editor-search-results" role="listbox" aria-label="Matching files">{entries.map((entry, index) => <li role="presentation" key={entry.path + ':' + (entry.line ?? '')}>
        <button type="button" role="option" id={`editor-search-result-${index}`} aria-selected={selected === index} onFocus={() => setSelected(index)} onClick={() => choose(entry)}>
          <span>{entry.path}{entry.line ? ':' + entry.line : ''}</span>{entry.preview !== undefined && <code>{entry.preview}</code>}
        </button></li>)}</ul>
      <div className="editor-dialog-actions"><button type="button" onClick={close}>Cancel</button><button type="submit" disabled={!entries.length}>Open</button></div>
    </form>
  </EditorDialog>;
}
