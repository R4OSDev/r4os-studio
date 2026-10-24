import { useEffect, useRef, useState } from 'react';
import type { ProjectBuildCacheCleared, ProjectBuildCacheState } from '../../../../shared/projects';
import { projectRequest, projectRequestId } from './api';

function retained(key: string) {
  try {
    const value = sessionStorage.getItem(key);
    return value && /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(value) ? value : null;
  } catch { return null; }
}

export function ProjectBuildCache({ id, token, disabled, busyChanged }: {
  id: string; token: string; disabled: boolean; busyChanged: (value: boolean) => void;
}) {
  const key = 'studio-build-cache-clear-' + id;
  const [request, setRequest] = useState<string | null>(() => retained(key));
  const [state, setState] = useState<ProjectBuildCacheState | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [loadError, setLoadError] = useState('');
  const clearing = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    async function refresh() {
      if (clearing.current) return;
      try {
        const value = await projectRequest<ProjectBuildCacheState>(`/${id}/build-cache`, '', 'GET', undefined, controller.signal);
        if (!controller.signal.aborted && !clearing.current) { setState(value); setLoadError(''); }
      } catch (cause) {
        if (!controller.signal.aborted && !clearing.current) { setState(null); setLoadError((cause as Error).message); }
      }
    }
    void refresh();
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(); }, 5000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [id]);
  useEffect(() => { busyChanged(busy); return () => busyChanged(false); }, [busy, busyChanged]);
  async function clear() {
    if (busy || disabled || !state?.available) return;
    const requestId = state.pendingRequestId ?? request ?? projectRequestId();
    try { sessionStorage.setItem(key, requestId); }
    catch { setError('The cleanup request could not be retained. Enable browser session storage and retry.'); return; }
    setRequest(requestId);
    clearing.current = true;
    setBusy(true); setError(''); setNotice('');
    try {
      const value = await projectRequest<ProjectBuildCacheCleared>(`/${id}/build-cache/clear`, token, 'POST', { requestId });
      if (value.requestId !== requestId || (!value.cleared && !value.superseded)) throw new Error('The cleanup receipt could not be confirmed. Retry to finish.');
      try { sessionStorage.removeItem(key); } catch { /* The completed host receipt makes future retries harmless. */ }
      setRequest(null);
      setState((current) => current ? { ...current, pendingRequestId: null } : current);
      setNotice(value.superseded ? 'The cache changed before cleanup. Clear it again to start a new request.'
        : value.changed ? 'Build cache cleared.' : 'The build cache is already empty.');
    } catch (cause) { setError((cause as Error).message); }
    finally { clearing.current = false; setBusy(false); }
  }
  return <section className="project-cache-section" aria-label="Build cache">
    <h3>Build cache</h3>
    <p>The next build recreates the cache.</p>
    {state && !state.available && <p role="status">Wait for active agent runs and development jobs to finish.</p>}
    {(error || loadError) && <p className="project-error" role="alert">{error || loadError}</p>}
    {notice && <p className="project-message" role="status">{notice}</p>}
    <button type="button" disabled={disabled || busy || !state?.available} onClick={() => void clear()}>
      {busy ? 'Clearing…' : request || state?.pendingRequestId ? 'Retry cache cleanup' : 'Clear build cache'}
    </button>
  </section>;
}
