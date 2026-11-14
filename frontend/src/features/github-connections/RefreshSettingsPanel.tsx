import { useCallback, useEffect, useState } from 'react';
import type { GitHubRefreshSettings } from '../../../../shared/github-connections';
import { GitHubError, loadConnections, request } from './api';
import './styles.css';

export function RefreshSettingsPanel({ setLeaveGuard }: { setLeaveGuard: (guard: () => boolean) => void }) {
  const [saved, setSaved] = useState<GitHubRefreshSettings | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [hours, setHours] = useState('1');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [epoch, setEpoch] = useState(0);
  const dirty = !!saved && (enabled !== saved.enabled || hours !== String(saved.intervalHours));
  const guard = useCallback(() => !busy && (!dirty || window.confirm('Discard unsaved GitHub refresh settings?')), [busy, dirty]);

  useEffect(() => {
    setLeaveGuard(guard);
    const warn = (e: BeforeUnloadEvent) => { if (dirty || busy) e.preventDefault(); };
    window.addEventListener('beforeunload', warn);
    return () => { window.removeEventListener('beforeunload', warn); setLeaveGuard(() => true); };
  }, [busy, dirty, guard, setLeaveGuard]);

  useEffect(() => {
    let active = true;
    void loadConnections().then(() => request<GitHubRefreshSettings>('GET', '/settings')).then(value => {
      if (active) { setSaved(value); setEnabled(value.enabled); setHours(String(value.intervalHours)); setError(''); }
    }).catch((cause: Error) => { if (active) setError(cause.message); });
    return () => { active = false; };
  }, [epoch]);

  async function save() {
    if (!saved || busy || !dirty) return;
    const intervalHours = Number(hours);
    if (!Number.isFinite(intervalHours) || intervalHours <= 0) { setError('Enter a positive interval in hours.'); return; }
    setBusy(true); setError('');
    try {
      const { csrfToken } = await loadConnections();
      const value = await request<GitHubRefreshSettings>('PUT', '/settings', { revision: saved.revision, enabled, intervalHours }, csrfToken);
      setSaved(value); setHours(String(value.intervalHours));
    } catch (cause) {
      if (cause instanceof GitHubError && cause.status >= 409) {
        const current = await request<GitHubRefreshSettings>('GET', '/settings').catch(() => null);
        if (current?.enabled === enabled && current.intervalHours === intervalHours) {
          setSaved(current); setHours(String(current.intervalHours)); return;
        }
        if (current) setSaved(current);
      }
      setError((cause as Error).message);
    } finally { setBusy(false); }
  }

  return <form className="github-panel github-refresh-panel" aria-label="GitHub refresh settings" onSubmit={event => { event.preventDefault(); void save(); }}>
    {error && <p className="github-error" role="alert">{error}</p>}
    {saved ? <>
      <fieldset disabled={busy}>
        <label className="github-check"><input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} />Automatic refresh</label>
        <label htmlFor="github-refresh-hours">Refresh interval (hours)</label>
        <input id="github-refresh-hours" required type="number" step="any" value={hours} onChange={event => setHours(event.target.value)} />
      </fieldset>
      <div className="github-actions">
        <button type="button" disabled={busy || !dirty} onClick={() => { setEnabled(saved.enabled); setHours(String(saved.intervalHours)); setError(''); }}>Cancel</button>
        <button type="submit" className="github-primary" disabled={busy || !dirty}>{busy ? 'Saving…' : 'Save'}</button>
      </div>
    </> : error ? <button type="button" onClick={() => setEpoch(n => n + 1)}>Retry</button> : <p role="status">Loading GitHub settings…</p>}
  </form>;
}
