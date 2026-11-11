import { useCallback, useEffect, useState } from 'react';
import { ProjectRequestError, studioRequest } from '../projects/api';
import './styles.css';
import './tool-deadline-settings.css';

type Deadline = {
  id: string;
  seconds: number;
  defaultSeconds: number;
  revision: number;
  overridden: boolean;
};
type Settings = { tools: Deadline[]; minSeconds: number; maxSeconds: number; csrfToken: string };
const BASE = '/api/settings/tool-deadlines';
const read = (signal?: AbortSignal) => studioRequest<Settings>(BASE, '', '', 'GET', undefined, signal);

export function ToolDeadlineSettingsPanel({ setLeaveGuard }: { setLeaveGuard: (guard: () => boolean) => void }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [toolId, setToolId] = useState('studio.exec_command');
  const [draft, setDraft] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [conflict, setConflict] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const tool = settings?.tools.find(entry => entry.id === toolId);
  const text = draft ?? (tool ? String(tool.seconds) : '');
  const dirty = !!tool && text !== String(tool.seconds);
  const guard = useCallback(() => !busy && (!dirty || window.confirm('Discard the unsaved tool deadline?')), [busy, dirty]);

  useEffect(() => {
    setLeaveGuard(guard);
    return () => setLeaveGuard(() => true);
  }, [guard, setLeaveGuard]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (busy || dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [busy, dirty]);
  useEffect(() => {
    const controller = new AbortController();
    void read(controller.signal).then(value => {
      if (controller.signal.aborted) return;
      setSettings(value);
      setDraft(null);
      setError('');
      setConflict(false);
    }).catch((cause: Error) => { if (!controller.signal.aborted) setError(cause.message); });
    return () => controller.abort();
  }, [epoch]);
  function selectTool(id: string) {
    if (!guard()) return;
    setToolId(id);
    setDraft(null);
    setError('');
    setNotice('');
    setConflict(false);
  }

  async function save(reset = false) {
    if (!settings || !tool || busy || conflict) return;
    const seconds = reset ? null : Number(text);
    if (seconds !== null && (!/^\d+$/.test(text) || !Number.isSafeInteger(seconds)
        || seconds < settings.minSeconds || seconds > settings.maxSeconds)) {
      setError(`Enter a whole number from ${settings.minSeconds} to ${settings.maxSeconds} seconds.`);
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const value = await studioRequest<Deadline>(BASE, '', settings.csrfToken, 'POST',
        { tool: tool.id, revision: tool.revision, seconds });
      setSettings({ ...settings, tools: settings.tools.map(entry => entry.id === value.id ? value : entry) });
      setDraft(null);
      setNotice(reset ? 'Default restored.' : 'Deadline saved.');
    } catch (cause) {
      setError((cause as Error).message);
      setConflict([403, 409].includes((cause as ProjectRequestError).status));
    } finally {
      setBusy(false);
    }
  }

  return <form className="system-prompt-panel tool-deadline-settings" aria-label="Tool deadlines"
    onSubmit={event => { event.preventDefault(); void save(); }}>
    <p className="system-prompt-scope">Deadlines apply per call from the next accepted Studio run. Shorter limits specified by a tool still apply.</p>
    {!settings && !error && <p role="status">Loading tool deadlines…</p>}
    {settings && tool && <>
      <label className="system-prompt-label" htmlFor="deadline-tool">Tool</label>
      <select id="deadline-tool" value={tool.id} disabled={busy} onChange={event => selectTool(event.target.value)}>
        {settings.tools.map(entry => <option key={entry.id} value={entry.id}>{entry.id}</option>)}
      </select>
      <label className="system-prompt-label" htmlFor="deadline-seconds">Deadline (seconds)</label>
      <input id="deadline-seconds" inputMode="numeric" value={text} disabled={busy} aria-describedby="deadline-help"
        onChange={event => { setDraft(event.target.value); setNotice(''); }} />
      <p id="deadline-help" className="system-prompt-notice">Default {tool.defaultSeconds.toLocaleString('en-US')} seconds.
        {' '}Allowed range {settings.minSeconds}–{settings.maxSeconds.toLocaleString('en-US')} seconds.</p>
      <div className="system-prompt-actions">
        <button type="button" disabled={busy || conflict || !tool.overridden} onClick={() => void save(true)}>Reset to default</button>
        <div className="system-prompt-save-actions">
          <button type="button" disabled={busy || !dirty} onClick={() => { setDraft(null); setNotice(''); }}>Cancel</button>
          <button className="system-prompt-primary" type="submit" disabled={busy || conflict || !dirty}>{busy ? 'Saving…' : 'Save changes'}</button>
        </div>
      </div>
    </>}
    {error && <p role="alert" className="system-prompt-error">{error}</p>}
    {notice && <p role="status" className="system-prompt-notice">{notice}</p>}
    {(!settings && error || conflict) && <button type="button" disabled={busy} onClick={() => {
      if (guard()) setEpoch(value => value + 1);
    }}>Reload settings</button>}
  </form>;
}
