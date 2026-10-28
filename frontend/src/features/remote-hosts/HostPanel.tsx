import { useCallback, useEffect, useId, useState } from 'react';
import type { FormEvent } from 'react';
import type { RemoteHost, RemoteHostInput, RemoteHostChange, RemoteHostRemoval } from '../../../../shared/remote-hosts';
import type { RemoteHostsApi } from './useRemoteHosts';
import { getHost, RemoteHostRequestError } from './api';
import { projectRequestId } from '../projects/api';
import './styles.css';
import { HostConnection } from './HostConnection';
import { HostJobs } from './HostJobs';

const statusText = { success: 'R4OS connection confirmed', offline: 'Host is offline or unreachable', authentication_failed: 'Authentication failed', hostkey_changed: 'Host identity changed', not_r4os: 'R4OS was not confirmed', transport_error: 'Connection failed', timeout: 'Connection timed out' };

export function HostPanel({ id, view, api, navigate, setLeaveGuard }: { id: string | null; view: string; api: RemoteHostsApi;
  navigate: (id: string | null, view?: string) => void; setLeaveGuard: (guard: () => boolean) => void }) {
  const [loaded, setLoaded] = useState<{ id: string; host: RemoteHost } | null>(null), [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const changed = useCallback((host: RemoteHost) => setLoaded({ id: host.id, host }), []);
  useEffect(() => {
    if (!id || !api.ready) return;
    const controller = new AbortController();
    void getHost(id, controller.signal).then((host) => { if (!controller.signal.aborted) { setLoaded({ id, host }); setError(''); } })
      .catch((cause: Error) => { if (!controller.signal.aborted) setError(cause.message); });
    return () => controller.abort();
  }, [id, api.ready, attempt]);
  if (id && (loaded?.id !== id || error)) return <section className="remote-host-panel" aria-label="Remote Host">
    <p role={error ? 'alert' : 'status'}>{error || api.error || 'Loading host…'}</p>
    <button type="button" onClick={() => { setError(''); setAttempt((n) => n + 1); void api.refresh().catch(() => {}); }}>Retry</button>
    <button type="button" onClick={() => navigate(null)}>New Host</button>
  </section>;
  const host = id ? loaded?.host : undefined;
  if (host && view === 'Overview') return <section className="remote-host-panel" aria-label="Remote Host overview">
    <h2>{host.name}</h2><p className="remote-description">{host.description || 'No description.'}</p>
    <dl><dt>Host / IP address</dt><dd>{host.address}</dd><dt>SSH port</dt><dd>{host.port}</dd><dt>User</dt><dd>{host.user}</dd>
      <dt>Password</dt><dd>{host.passwordConfigured ? 'Stored privately' : 'Not configured'}</dd>
      <dt>Connection</dt><dd>{host.lastTest ? statusText[host.lastTest.status] : 'Not tested'}</dd>
      {host.lastTest && <><dt>Last checked</dt><dd>{new Date(host.lastTest.checkedAt).toLocaleString()}</dd></>}
      {host.lastTest?.version && <><dt>R4OS release</dt><dd>{host.lastTest.version}</dd><dt>Kernel</dt><dd>{host.lastTest.kernel ?? 'Not reported'}</dd></>}
      <dt>Host key</dt><dd>{host.hostKey.fingerprint ?? 'Not trusted yet'}</dd>
    </dl>
    <p>A saved host is available for explicit tasks. Saving or opening this page does not connect.</p>
    <button type="button" onClick={() => navigate(host.id, 'Settings')}>Edit settings</button>
    <HostConnection host={host} api={api} changed={changed} />
    <HostJobs key={host.id} host={host} api={api} />
  </section>;
  return <HostSettings key={id ?? 'new'} host={host} api={api} navigate={navigate} setLeaveGuard={setLeaveGuard} />;
}

function HostSettings({ host, api, navigate, setLeaveGuard }: { host?: RemoteHost; api: RemoteHostsApi; navigate: (id: string | null, view?: string) => void; setLeaveGuard: (guard: () => boolean) => void }) {
  const [base, setBase] = useState(host);
  const initial = (value = host) => ({ name: value?.name ?? '', description: value?.description ?? '', address: value?.address ?? '', port: String(value?.port ?? 22), user: value?.user ?? 'r4os' });
  const [draft, setDraft] = useState(initial), [password, setPassword] = useState(host ? '' : 'rosebud');
  const [replace, setReplace] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [conflict, setConflict] = useState(false);
  const [pending, setPending] = useState<{ operation: 'save'; input: RemoteHostInput | RemoteHostChange } | { operation: 'remove'; input: RemoteHostRemoval } | null>(null);
  const formId = useId();
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial(base)) || replace || password !== (base ? '' : 'rosebud');
  const guard = useCallback(() => !busy && !pending && (!dirty || window.confirm('Discard unsaved Remote Host changes?')), [busy, pending, dirty]);
  useEffect(() => { setLeaveGuard(guard); return () => setLeaveGuard(() => true); }, [guard, setLeaveGuard]);
  useEffect(() => { const warn = (event: BeforeUnloadEvent) => { if (dirty || busy || pending) event.preventDefault(); }; window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn); }, [dirty, busy, pending]);
  function reset(value = base) { setBase(value); setDraft(initial(value)); setPassword(value ? '' : 'rosebud'); setReplace(false); setError(''); setNotice(''); setConflict(false); setPending(null); }
  async function execute(value: NonNullable<typeof pending>) {
    if (busy || !api.ready) return;
    setBusy(true); setPending(value); setError(''); setNotice('');
    try {
      if (value.operation === 'remove' && base) { await api.remove(base.id, value.input); setPending(null); navigate(null); }
      else if (value.operation === 'save') { const saved = await api.save(value.input, base?.id); reset(saved); setNotice('Host saved.'); navigate(saved.id, 'Settings'); }
    } catch (cause) {
      const failure = cause as RemoteHostRequestError; setError(failure.message);
      if (failure.status >= 400 && failure.status < 500) { setPending(null); setConflict([403, 409].includes(failure.status)); }
    } finally { setBusy(false); }
  }
  async function save(event: FormEvent) {
    event.preventDefault(); if (pending || conflict) return;
    const input = { requestId: projectRequestId(), ...draft, port: Number(draft.port), ...((!base || replace) ? { password } : {}), ...(base ? { revision: base.revision } : {}) };
    await execute({ operation: 'save', input });
  }
  async function reload() {
    if (!guard() || !base) return;
    try { const result = await api.refresh(); const current = result.hosts.find((h) => h.id === base.id); if (!current) { setError('This host was removed.'); return; } reset(current); }
    catch (cause) { setError((cause as Error).message); }
  }
  const field = (name: keyof typeof draft, label: string, type = 'text') => <div className="remote-field"><label htmlFor={formId + name}>{label}</label>
    <input id={formId + name} type={type} value={draft[name]} required={name !== 'description'} min={type === 'number' ? 1 : undefined} max={type === 'number' ? 65535 : undefined}
      maxLength={name === 'name' ? 240 : name === 'user' ? 64 : 253} autoComplete="off" spellCheck={false} onChange={(event) => { setDraft({ ...draft, [name]: event.target.value }); setNotice(''); }} /></div>;
  return <form className="remote-host-panel" aria-label={base ? 'Remote Host settings' : 'New Remote Host'} onSubmit={(event) => void save(event)} autoComplete="off">
    <h2>{base ? 'Host settings' : 'New Remote Host'}</h2>
    <p>Save SSH access to an external R4OS computer. Saving does not connect to it.</p>
    {api.loading && <p role="status">Loading hosts…</p>}{api.error && <p className="remote-error" role="alert">{api.error}</p>}
    {!api.ready && <button type="button" onClick={() => void api.refresh().catch(() => {})}>Retry</button>}
    <fieldset disabled={busy || !api.ready || !!pending}>
      {field('name', 'Name')}<div className="remote-field"><label htmlFor={formId + 'description'}>Description</label>
        <textarea id={formId + 'description'} rows={4} maxLength={4000} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></div>
      {field('address', 'Host / IP address')}{field('port', 'SSH port', 'number')}{field('user', 'User')}
      {base && <><p>{base.passwordConfigured ? 'Password stored. Its value cannot be displayed.' : 'No password is configured.'}</p>
        <label className="remote-check"><input type="checkbox" checked={replace} onChange={(event) => { setReplace(event.target.checked); setPassword(''); }} />Change password</label></>}
      {(!base || replace) && <div className="remote-field"><label htmlFor={formId + 'password'}>{base ? 'New password' : 'Password'}</label>
        <input id={formId + 'password'} type="password" autoComplete="new-password" spellCheck={false} maxLength={4096} required value={password} onChange={(event) => setPassword(event.target.value)} /></div>}
    </fieldset>
    {error && <p className="remote-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {pending && !busy && <p role="status">The original request needs confirmation. Retry it before editing or leaving. Request: {pending.input.requestId}</p>}
    <div className="remote-actions">
      <button type="button" disabled={busy || !!pending} onClick={() => reset()}>Cancel</button>
      {pending ? <button type="button" disabled={busy} onClick={() => void execute(pending)}>Retry original request</button> : <button type="submit" className="remote-primary" disabled={busy || !api.ready || conflict || (!dirty && !!base)}>{busy ? 'Saving…' : base ? 'Save changes' : 'Create host'}</button>}
      {conflict && base && <button type="button" disabled={busy} onClick={() => void reload()}>Reload saved</button>}
      {base && <button type="button" className="remote-remove" disabled={busy || !!pending || conflict} onClick={() => {
        if (window.confirm(`Remove the saved Remote Host “${base.name}” from Studio?`)) void execute({ operation: 'remove', input: { requestId: projectRequestId(), revision: base.revision, confirm: true } });
      }}>Remove host</button>}
    </div>
  </form>;
}
