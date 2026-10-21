import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type { VirtualMachine, VmDevelopmentAccess } from '../../../../shared/virtual-machines.js';
import type { VmApi } from './useVms';

export function DevelopmentAccess({ api, vm }: { api: VmApi; vm: VirtualMachine }) {
  const [value, setValue] = useState<VmDevelopmentAccess | null>(null), [enabled, setEnabled] = useState(false);
  const [username, setUsername] = useState(''), [password, setPassword] = useState('');
  const [resetKey, setResetKey] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    void api.request<VmDevelopmentAccess>(`/${vm.id}/development-access`).then((result) => {
      if (!cancelled) { setValue(result); setEnabled(result.enabled); setUsername(result.username); setPassword(''); setError(''); }
    }).catch((cause) => { if (!cancelled) setError(cause.message); });
    return () => { cancelled = true; };
    // Preserve unsaved credentials across ordinary VM polling.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vm.id, vm.revision]);
  async function save(event: FormEvent) {
    event.preventDefault(); if (!value) return;
    setBusy(true); setError('');
    try {
      const result = await api.request<VmDevelopmentAccess>(`/${vm.id}/development-access`, 'PATCH', {
        revision: value.revision, vmRevision: value.vmRevision, enabled, username,
        ...(password ? { password } : {}), resetHostKey: resetKey,
      });
      setValue(result); setPassword(''); setResetKey(false);
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  async function check() {
    setBusy(true); setError('');
    try { setValue(await api.request<VmDevelopmentAccess>(`/${vm.id}/development-access/check`, 'POST')); }
    catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }
  const dirty = value && (enabled !== value.enabled || username !== value.username || password !== '' || resetKey);
  return <section className="vm-release vm-development-access" aria-labelledby="vm-development-title">
    <h2 id="vm-development-title">Development access</h2>
    {error && <p className="vm-alert" role="alert">{error}</p>}
    {value && <>
      <form className="vm-form" onSubmit={(event) => void save(event)}>
        <label className="vm-network"><input type="checkbox" checked={enabled} disabled={busy || (!vm.networkEnabled && !enabled)} onChange={(event) => setEnabled(event.target.checked)} />Enable SSH access</label>
        <label htmlFor="vm-guest-username">Guest username</label>
        <input id="vm-guest-username" value={username} maxLength={32} autoComplete="off" disabled={busy || !enabled} onChange={(event) => setUsername(event.target.value)} />
        <label htmlFor="vm-guest-password">Guest password</label>
        <input id="vm-guest-password" type="password" value={password} maxLength={256} autoComplete="off" disabled={busy || !enabled} placeholder={value.credentialsStored ? 'Saved' : ''} onChange={(event) => setPassword(event.target.value)} />
        {value.hostKeyFingerprint && <>
          <label>Host key</label><code className="vm-access-fingerprint">{value.hostKeyFingerprint}</code>
          <label className="vm-network"><input type="checkbox" checked={resetKey} disabled={busy} onChange={(event) => setResetKey(event.target.checked)} />Verify a new host key</label>
        </>}
        <div className="vm-access-actions">
          <button className="button-primary" disabled={busy || !dirty} type="submit">{busy ? 'Working…' : 'Save access'}</button>
          <button className="button-secondary" disabled={busy || Boolean(dirty) || !value.available || vm.state !== 'running'} type="button" onClick={() => void check()}>Check access</button>
        </div>
      </form>
      <p className="vm-help" role="status">{value.ready ? `Ready · R4OS ${value.guestRelease} · Kernel ${value.guestKernel}` : value.reason}</p>
    </>}
  </section>;
}
