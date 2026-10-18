import { useEffect, useRef, useState } from 'react';
import type { UpdateStatus } from '../../../../shared/updates';
import { version } from '../../../../shared/version.json';
import './styles.css';

const busyPhases = ['checking', 'downloading', 'building', 'activating', 'recovering'];
function date(value: string | null) { return value ? new Date(value).toLocaleString() : 'Not yet'; }

export function UpdatesPanel() {
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const token = useRef('');
  const installedFromThisTab = useRef(false);
  const [reconnecting, setReconnecting] = useState(false);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    async function refresh() {
      try {
        const response = await fetch('/api/updates', { cache: 'no-store', signal: controller.signal });
        if (!response.ok) throw new Error('The update status could not be loaded.');
        const next = await response.json() as UpdateStatus;
        if (!active) return;
        token.current = next.csrfToken ?? '';
        setStatus(next); setError(null); setReconnecting(false);
        // A new application build must reload its own assets after a successful switch.
        if (installedFromThisTab.current && next.installed.version !== version && ['complete', 'idle'].includes(next.phase)) {
          window.location.hash = 'updates';
          window.location.reload();
        }
        if (['failed', 'rolled_back'].includes(next.phase)) installedFromThisTab.current = false;
      } catch (reason) {
        if (!active) return;
        if (installedFromThisTab.current) setReconnecting(true);
        else setError(reason instanceof Error ? reason.message : 'The update status could not be loaded.');
      }
    }
    void refresh();
    const interval = window.setInterval(() => { if (!document.hidden) void refresh(); }, 3000);
    const visible = () => { if (!document.hidden) void refresh(); };
    document.addEventListener('visibilitychange', visible);
    return () => { active = false; controller.abort(); window.clearInterval(interval); document.removeEventListener('visibilitychange', visible); };
  }, []);

  async function action(kind: 'check' | 'install') {
    if (!status || sending) return;
    setSending(true); setError(null);
    try {
      const response = await fetch(`/api/updates/${kind}`, { method: 'POST', cache: 'no-store', headers: {
        'Content-Type': 'application/json', 'X-CSRF-Token': token.current,
      }, body: JSON.stringify(kind === 'install' && status.latest ? { tag: status.latest.tag, commit: status.latest.commit } : {}) });
      const result = await response.json() as UpdateStatus & { message?: string };
      if (!response.ok) throw new Error(result.message ?? 'The update request failed.');
      if (kind === 'install') installedFromThisTab.current = true;
      setStatus(result);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The update request failed.'); }
    finally { setSending(false); }
  }

  const busy = sending || Boolean(status && busyPhases.includes(status.phase));
  return <section className="updates-content" aria-label="R4OS Studio updates">
    <div className="updates-card">
      <div className="updates-title"><div><span className="updates-eyebrow">APPLICATION UPDATES</span><h2>Keep your studio up to date.</h2></div>
        <span className="updates-version">{status?.installed.version ?? version}</span></div>
      <p className="updates-help">Updates are checked automatically every six hours. Installation starts only when you choose Install update.</p>
      {(error || status?.error) && <div className="updates-alert" role="alert">{error ?? status?.error}</div>}
      {!status ? <p role="status">Loading update status…</p> : <>
        {!status.enabled && <div className="updates-alert">Update host support is not configured. A host administrator must run the update installer before this feature can be used.</div>}
        <div className={`updates-state ${busy ? 'busy' : ''}`} role="status" aria-live="polite">
          <span className="updates-dot" />{reconnecting ? 'Studio is restarting. Reconnecting automatically…' : status.message}
        </div>
        <dl className="updates-properties">
          <div><dt>Installed version</dt><dd>{status.installed.version}{status.installed.commit && <small>{status.installed.commit.slice(0, 12)}</small>}</dd></div>
          <div><dt>Latest release</dt><dd>{status.latest ? status.latest.version : 'No release reported'}{status.latest && <small>{status.latest.commit.slice(0, 12)}</small>}</dd></div>
          <div><dt>Last checked</dt><dd>{date(status.lastChecked)}</dd></div>
          <div><dt>Next automatic check</dt><dd>{date(status.nextCheck)}</dd></div>
          <div><dt>Update source</dt><dd>{status.source}</dd></div>
          <div><dt>Installation</dt><dd>Manual · Automatic installation is off</dd></div>
        </dl>
        <div className="updates-actions">
          <button type="button" disabled={!status.enabled || busy} onClick={() => void action('check')}>Check for updates</button>
          <button type="button" className="updates-primary" disabled={!status.enabled || busy || !status.available} onClick={() => void action('install')}>
            {busy && status.phase !== 'checking' ? 'Updating…' : status.available && status.latest ? `Install update ${status.latest.version}` : 'Install update'}
          </button>
          {status.installed.version !== version && <button type="button" onClick={() => { window.location.hash = 'updates'; window.location.reload(); }}>Reload Studio</button>}
        </div>
        <p className="updates-help">Studio briefly reconnects during installation. Your data stays in place and running virtual machines keep running.</p>
        {status.history.length > 0 && <div className="updates-history"><h3>Recent installations</h3><ul>{[...status.history].reverse().map((entry, index) =>
          <li key={`${entry.time}-${index}`}><div><strong>{entry.version}</strong><span>{entry.outcome.replaceAll('_', ' ')}</span><time>{date(entry.time)}</time></div><p>{entry.message}</p></li>)}</ul></div>}
      </>}
    </div>
  </section>;
}
