import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type { GitHubConnection } from '../../../../shared/github-connections';
import type { ConnectionsApi } from './useConnections';
import { GitHubError } from './api';
import './styles.css';

export function ConnectionPanel({ connection, api, select, setLeaveGuard }: {
  connection?: GitHubConnection; api: ConnectionsApi; select: (id: string | null) => void;
  setLeaveGuard: (guard: () => boolean) => void;
}) {
  const [name, setName] = useState(connection?.name ?? ''), [token, setToken] = useState('');
  const [base, setBase] = useState(connection), [id] = useState(() => crypto.randomUUID());
  const [replace, setReplace] = useState(false), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [conflict, setConflict] = useState(false);
  const dirty = name !== (base?.name ?? '') || !!token || replace;
  const guard = useCallback(() => !busy && (!dirty || window.confirm('Discard unsaved connection changes?')), [busy, dirty]);
  useEffect(() => { setLeaveGuard(guard); return () => setLeaveGuard(() => true); }, [guard, setLeaveGuard]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty || busy) event.preventDefault(); };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [dirty, busy]);
  function reset(value = connection) { setBase(value); setName(value?.name ?? ''); setToken(''); setReplace(false); setError(''); setNotice(''); setConflict(false); }
  async function save(event: FormEvent) {
    event.preventDefault(); if (busy || !api.ready) return;
    if (!name.trim() || name.length > 120 || ((!base || replace) && !/^[\x21-\x7e]{20,4096}$/.test(token))) {
      setError('Enter a connection name and a token of 20–4096 characters without spaces.'); return;
    }
    setBusy(true); setError(''); setNotice('');
    try {
      const value = await api.save(base ? { revision: base.revision, name, ...(replace ? { token } : {}) } : { id, name, token }, base?.id);
      setToken(''); setReplace(false); setBase(value); setName(value.name); setConflict(false); setNotice('Connection saved.'); select(value.id);
    } catch (cause) { setError((cause as Error).message); setConflict([403, 409].includes((cause as GitHubError).status)); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (!base || busy || !window.confirm(`Remove the saved connection “${base.name}” from Studio?`)) return;
    setBusy(true); setError('');
    try { await api.remove(base); setToken(''); setName(''); setReplace(false); select(null); }
    catch (cause) { setError((cause as Error).message); setConflict([403, 409].includes((cause as GitHubError).status)); }
    finally { setBusy(false); }
  }
  async function reload() {
    if (!guard()) return;
    try { const result = await api.refresh(); const current = result.connections.find((v) => v.id === (base?.id ?? id)); reset(current); select(current?.id ?? null); }
    catch (cause) { setError((cause as Error).message); }
  }
  return <form className="github-panel" aria-label={base ? 'GitHub connection' : 'New GitHub connection'} onSubmit={(event) => void save(event)} autoComplete="off">
    <p>Save a named GitHub access token. Tokens stay private on the Studio host.</p>
    {api.loading && <p role="status">Loading connections…</p>}
    {api.error && <p className="github-error" role="alert">{api.error}</p>}
    {!api.ready && <button type="button" onClick={() => void api.refresh().catch(() => {})}>Retry</button>}
    <fieldset disabled={busy || !api.ready}>
      <label htmlFor="github-name">Connection name</label>
      <input id="github-name" value={name} maxLength={120} required onChange={(event) => { setName(event.target.value); setNotice(''); }} />
      {base && <><p className="github-token-status">Token stored. Its value cannot be displayed.</p>
        <label className="github-check"><input type="checkbox" checked={replace} onChange={(event) => { setReplace(event.target.checked); setToken(''); }} />Replace token</label></>}
      {(!base || replace) && <><label htmlFor="github-token">{base ? 'New token' : 'Token'}</label>
        <input id="github-token" type="password" autoComplete="new-password" spellCheck={false} autoCapitalize="none"
          value={token} minLength={20} maxLength={4096} required onChange={(event) => { setToken(event.target.value); setNotice(''); }} />
        <p>Use a personal access token. Repository permissions will depend on the token you provide.</p></>}
      {error && <p className="github-error" role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <div className="github-actions">
        {base && <button type="button" onClick={() => void remove()}>Remove connection</button>}
        <button type="button" disabled={!dirty} onClick={() => reset()}>Cancel</button>
        <button type="submit" className="github-primary" disabled={!dirty || conflict}>{busy ? 'Saving…' : 'Save connection'}</button>
      </div>
    </fieldset>
    {conflict && <button type="button" disabled={busy} onClick={() => void reload()}>Reload connections</button>}
  </form>;
}
