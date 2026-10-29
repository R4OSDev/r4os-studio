import { useCallback, useEffect, useState } from 'react';
import type { AgentSession } from '../../../../shared/agent-sessions';
import { useSessionApi, sessionPath } from './api';

export function useSessions(projectId: string | null) {
  const { request: projectRequest, scope } = useSessionApi();
  const [state, setState] = useState<{ projectId: string | null; sessions: AgentSession[]; error: string; loading: boolean }>({ projectId: null, sessions: [], error: '', loading: true });
  const [epoch, setEpoch] = useState(0);
  const reload = useCallback(() => setEpoch((v) => v + 1), []);
  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return;
    const channel = new BroadcastChannel('studio-session-lifetimes');
    channel.onmessage = event => { if (event.data?.deleted === true && event.data.scope === scope && event.data.owner === projectId) reload(); };
    return () => channel.close();
  }, [scope, projectId, reload]);
  useEffect(() => {
    if (!projectId) return;
    const controller = new AbortController();
    void projectRequest<{ sessions: AgentSession[] }>(sessionPath(projectId), '', 'GET', undefined, controller.signal)
      .then((r) => { if (!controller.signal.aborted) setState({ projectId, sessions: r.sessions, error: '', loading: false }); })
      .catch((e: Error) => { if (!controller.signal.aborted) setState({ projectId, sessions: [], error: e.message, loading: false }); });
    return () => controller.abort();
  }, [projectId, epoch, projectRequest]);
  return { sessions: state.projectId === projectId ? state.sessions : [], error: state.projectId === projectId ? state.error : '', loading: state.projectId !== projectId || state.loading, reload };
}
