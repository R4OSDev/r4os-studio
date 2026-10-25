import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type { SystemPromptResponse } from '../../../../shared/system-prompt';
import './styles.css';

class SettingsError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
type PromptKind = 'system-prompt' | 'skill-manager-prompt';
async function request(kind: PromptKind, method = 'GET', body?: unknown, token = '', reset = false, signal?: AbortSignal) {
  const response = await fetch('/api/settings/' + kind + (reset ? '/reset' : ''), {
    method, cache: 'no-store', signal,
    headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json', 'X-CSRF-Token': token }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const result = await response.json();
  if (!response.ok) throw new SettingsError(result.message ?? 'Prompt settings could not be loaded.', response.status);
  return result as SystemPromptResponse;
}

export function SystemPromptPanel({ setLeaveGuard, kind = 'system-prompt' }: { setLeaveGuard: (guard: () => boolean) => void; kind?: PromptKind }) {
  const label = kind === 'skill-manager-prompt' ? 'Skill Manager Prompt' : 'System Prompt';
  const [saved, setSaved] = useState<SystemPromptResponse | null>(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [conflict, setConflict] = useState(false), [epoch, setEpoch] = useState(0);
  const dirty = !!saved && text !== saved.text;
  const guard = useCallback(() => !busy && (!dirty || window.confirm('Discard unsaved ' + label.toLowerCase() + ' changes?')), [busy, dirty, label]);
  useEffect(() => {
    setLeaveGuard(guard);
    return () => setLeaveGuard(() => true);
  }, [guard, setLeaveGuard]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty || busy) event.preventDefault(); };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty, busy]);
  useEffect(() => {
    const controller = new AbortController();
    void request(kind, 'GET', undefined, '', false, controller.signal).then((next) => {
      if (!controller.signal.aborted) { setSaved(next); setText(next.text); setError(''); setConflict(false); }
    }).catch((cause: Error) => { if (!controller.signal.aborted) setError(cause.message); });
    return () => controller.abort();
  }, [epoch, kind]);

  async function save(event?: FormEvent, reset = false) {
    event?.preventDefault();
    if (!saved || busy) return;
    if (!reset && (!text.trim() || new TextEncoder().encode(text).length > 32768)) {
      setError('Enter a prompt of at most 32 KiB.'); return;
    }
    setBusy(true); setError(''); setNotice('');
    try {
      const next = await request(kind, reset ? 'POST' : 'PATCH', { revision: saved.revision, ...(reset ? {} : { text }) }, saved.csrfToken, reset);
      setSaved(next); setText(next.text); setConflict(false); setNotice(reset ? 'Default restored.' : 'Saved.');
    } catch (cause) {
      setError((cause as Error).message); setConflict([403, 409].includes((cause as SettingsError).status));
    } finally { setBusy(false); }
  }

  return <form className="system-prompt-panel" aria-label={label} onSubmit={(event) => void save(event)}>
    <p className="system-prompt-scope">{kind === 'skill-manager-prompt' ? 'Applies to all Skill Manager sessions from the next run.' : 'Applies to all project sessions from the next run.'}</p>
    {!saved && !error && <p role="status">Loading system prompt…</p>}
    {saved && <>
      <label className="system-prompt-label" htmlFor={'global-' + kind}>Prompt</label>
      <textarea id={'global-' + kind} rows={20} maxLength={32768} required spellCheck={false} disabled={busy}
        value={text} onChange={(event) => { setText(event.target.value); setNotice(''); }} />
    </>}
    {error && <p className="system-prompt-error" role="alert">{error}</p>}
    {notice && <p className="system-prompt-notice" role="status">{notice}</p>}
    {conflict && <button type="button" disabled={busy} onClick={() => { if (guard()) setEpoch((value) => value + 1); }}>Reload settings</button>}
    {!saved && error && <button type="button" onClick={() => setEpoch((value) => value + 1)}>Retry</button>}
    {saved && <div className="system-prompt-actions">
      <button type="button" disabled={busy || conflict || (saved.isDefault && !dirty)} onClick={() => void save(undefined, true)}>Reset to default</button>
      <div className="system-prompt-save-actions">
        <button type="button" disabled={busy || !dirty} onClick={() => { setText(saved.text); setError(''); setNotice(''); }}>Cancel</button>
        <button type="submit" className="system-prompt-primary" disabled={busy || !dirty || conflict}>{busy ? 'Saving…' : 'Save changes'}</button>
      </div>
    </div>}
  </form>;
}
