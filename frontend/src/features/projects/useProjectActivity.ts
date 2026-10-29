import { useEffect, useState } from 'react';
import type { ProjectActivity } from '../../../../shared/projects';
import { projectRequest } from './api';

export function useProjectActivity(ready: boolean) {
  const [active, setActive] = useState<ReadonlySet<string>>(new Set());
  useEffect(() => {
    if (!ready) return;
    let request: AbortController | undefined, disposed = false, expires = 0;
    const clear = () => { expires = 0; setActive(previous => previous.size ? new Set() : previous); };
    const refresh = async () => {
      if (document.hidden || request || disposed) return;
      const controller = new AbortController(); request = controller;
      const started = performance.now();
      const timeout = window.setTimeout(() => controller.abort(), 4000);
      try {
        const value = await projectRequest<ProjectActivity>('/session-activity', '', 'GET', undefined, controller.signal);
        const ttl = Math.min(10000, value.validForMs);
        if (value.schema !== 1 || !Array.isArray(value.activeProjectIds) || !Number.isFinite(ttl) || ttl <= 0
          || value.activeProjectIds.some(id => typeof id !== 'string' || !/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(id))) throw new Error('Invalid activity.');
        if (!disposed && !document.hidden) {
          expires = started + ttl;
          setActive(performance.now() < expires ? new Set(value.activeProjectIds) : new Set());
        }
      } catch { if (!disposed) clear(); }
      finally { window.clearTimeout(timeout); if (request === controller) request = undefined; }
    };
    const visibility = () => { if (document.hidden) { request?.abort(); clear(); } else void refresh(); };
    const update = () => { void refresh(); };
    const initial = window.setTimeout(update, 0);
    const poll = window.setInterval(update, 5000);
    const expiry = window.setInterval(() => { if (expires && performance.now() >= expires) clear(); }, 500);
    window.addEventListener('focus', update); window.addEventListener('online', update);
    window.addEventListener('studio-project-activity', update);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      disposed = true; request?.abort();
      window.clearTimeout(initial); window.clearInterval(poll); window.clearInterval(expiry);
      window.removeEventListener('focus', update); window.removeEventListener('online', update);
      window.removeEventListener('studio-project-activity', update);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [ready]);
  return ready ? active : new Set<string>();
}
