import { useCallback, useEffect, useState } from 'react';
import type { AgentSession } from '../../../../shared/agent-sessions';
import { useSessionApi, sessionPath } from './api';

export function useSessions(projectId: string | null) {
  const { request: projectRequest, scope } = useSessionApi();
  const [state, setState] = useState<{ revision:number; sessions: AgentSession[]; error: string }>({ revision:-1,sessions: [], error: '' });
  const [epoch, setEpoch] = useState(0);
  const [cache,setCache]=useState(new Map<string,AgentSession[]>());
  const key=scope+':'+projectId;
  const [selection,setSelection]=useState({key,epoch,revision:0});
  if(selection.key!==key||selection.epoch!==epoch)setSelection({key,epoch,revision:selection.revision+1});
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
      .then((r) => { if (!controller.signal.aborted) {
        setState({ revision:selection.revision, sessions: r.sessions, error: '' });
        setCache(old=>{const next=new Map(old),key=scope+':'+projectId;next.delete(key);next.set(key,r.sessions);while(next.size>8)next.delete(next.keys().next().value!);return next;});
      } })
      .catch((e: Error) => { if (!controller.signal.aborted) setState({ revision:selection.revision, sessions: [], error: e.message }); });
    return () => controller.abort();
  }, [projectId, epoch, projectRequest,scope,selection.revision]);
  const same=state.revision===selection.revision,cached=projectId?cache.get(key):undefined;
  return { sessions: projectId?(same?state.sessions:cached??[]):[],error:same?state.error:'',loading:!!projectId&&!same&&!cached,fresh:!!projectId&&same&&!state.error,reload };
}
