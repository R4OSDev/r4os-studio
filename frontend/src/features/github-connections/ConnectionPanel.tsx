import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type { GitHubConnection, GitHubTestResult, GitHubTestStatus } from '../../../../shared/github-connections';
import type { ConnectionsApi } from './useConnections';
import { connectionRequestId, GitHubError } from './api';
import './styles.css';
const messages: Record<GitHubTestStatus, string> = {
  success: 'Authentication succeeded', authentication_failed: 'Authentication failed. The token was not accepted.',
  forbidden: 'GitHub restricted access to this request.', rate_limited: 'GitHub rate limit reached. Try again later.',
  network_error: 'The GitHub request failed due to a network or TLS error.', timeout: 'The GitHub request timed out.',
  server_error: 'GitHub is temporarily unavailable.', invalid_response: 'GitHub returned an unexpected or oversized response.',
};

export function ConnectionPanel({ connection, api, select, setLeaveGuard }: {
  connection?: GitHubConnection; api: ConnectionsApi; select: (id: string | null) => void;
  setLeaveGuard: (guard: () => boolean) => void;
}) {
  const [name, setName] = useState(connection?.name ?? ''), [token, setToken] = useState('');
  const [base, setBase] = useState(connection), [id] = useState(connectionRequestId);
  const [replace, setReplace] = useState(false), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [conflict, setConflict] = useState(false);
  const [draftTest, setDraftTest] = useState<GitHubTestResult>(), [testing, setTesting] = useState(false);
  const lastTest = !base || replace ? draftTest : base.lastTest;
  const dirty = name !== (base?.name ?? '') || !!token || replace;
  const guard = useCallback(() => !busy && (!dirty || window.confirm('Discard unsaved connection changes?')), [busy, dirty]);
  useEffect(() => { setLeaveGuard(guard); return () => setLeaveGuard(() => true); }, [guard, setLeaveGuard]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty || busy) event.preventDefault(); };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [dirty, busy]);
  function reset(value = connection) { setBase(value); setName(value?.name ?? ''); setToken(''); setReplace(false); setDraftTest(undefined); setError(''); setNotice(''); setConflict(false); }
  async function test() {
    if (busy || !api.ready) return;
    setBusy(true); setTesting(true); setError(''); setNotice('');
    try {
      if (!base || replace) setDraftTest(await api.testDraft(token));
      else setBase(await api.testStored(base));
    } catch (cause) { setError((cause as Error).message); setConflict([403, 409].includes((cause as GitHubError).status)); }
    finally { setBusy(false); setTesting(false); }
  }
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
    if (!base || busy) return;
    setBusy(true); setError('');
    try {
      const { projects } = await api.references(base);
      if (!window.confirm(`Remove the saved connection “${base.name}” from Studio?${projects.length ? '\nGitHub access will be unavailable for: ' + projects.map((v) => v.name).join(', ') + '. Their local sources and history will be preserved.' : ''}`)) return;
      await api.remove(base, projects.length > 0); setToken(''); setName(''); setReplace(false); select(null);
    }
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
        <label className="github-check"><input type="checkbox" checked={replace} onChange={(event) => { setReplace(event.target.checked); setToken(''); setDraftTest(undefined); }} />Replace token</label></>}
      {(!base || replace) && <><label htmlFor="github-token">{base ? 'New token' : 'Token'}</label>
        <input id="github-token" type="password" autoComplete="new-password" spellCheck={false} autoCapitalize="none"
          value={token} minLength={20} maxLength={4096} required onChange={(event) => { setToken(event.target.value); setDraftTest(undefined); setNotice(''); }} />
        <p>Use a personal access token. Repository permissions will depend on the token you provide.</p></>}
      <section aria-label="Connection test">
        <button type="button" disabled={conflict || ((!base || replace) && !/^[\x21-\x7e]{20,4096}$/.test(token))} onClick={() => void test()}>{testing ? 'Testing…' : 'Test connection'}</button>
        <p role="status">{lastTest ? `${messages[lastTest.status]}${lastTest.status === 'success' ? `: ${lastTest.login} (ID ${lastTest.userId})` : ''}. Last tested ${new Date(lastTest.checkedAt).toLocaleString()}.` : 'Not tested.'}</p>
        <p>A successful test confirms authentication at that time. It does not verify repository or push permissions. Testing an unsaved token does not save it.</p>
        {lastTest?.status === 'success' && <p>Account: @{lastTest.login}. Repository creation, reading contents and pushing require separate permissions. Token or account changes are checked again before repository operations.</p>}
      </section>
      {error && <p className="github-error" role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <div className="github-actions">
        {base && <button type="button" onClick={() => void remove()}>Remove connection</button>}
        <button type="button" disabled={!dirty} onClick={() => reset()}>Cancel</button>
        <button type="submit" className="github-primary" disabled={!dirty || conflict}>{busy && !testing ? 'Saving…' : 'Save connection'}</button>
      </div>
    </fieldset>
    {conflict && <button type="button" disabled={busy} onClick={() => void reload()}>Reload connections</button>}
  </form>;
}
