import { useCallback, useEffect, useState } from 'react';
import type { SessionInbox } from '../../../../shared/agent-messages';
import { ProjectRequestError, projectRequestId, sessionPath, useSessionApi } from './api';

type Control = { requestId: string; revision: number; action: 'resume' | 'cancel'; messageId?: string };
export function useMessageInbox(projectId: string, sessionId: string, token: string, refreshAuth: () => Promise<void>) {
  const { request, scope } = useSessionApi(), base = sessionPath(projectId, sessionId) + '/messages';
  const key = `studio.${scope}.queue-control.${sessionId}`;
  const [inbox, setInbox] = useState<SessionInbox | null>(null), [available, setAvailable] = useState(false);
  const [boundWaiting, setBoundWaiting] = useState(false);
  const [error, setError] = useState(''), [posting, setPosting] = useState(false);
  const [pending, setPending] = useState<Control | null>(() => { try { return JSON.parse(sessionStorage.getItem(key) ?? 'null'); } catch { return null; } });
  const refresh = useCallback(async (signal?: AbortSignal) => {
    let value = await request<SessionInbox>(base + '?view=pending', '', 'GET', undefined, signal);
    while (value.nextBefore && value.messages.length < 32) {
      const page = await request<SessionInbox>(base + '?view=pending&before=' + value.nextBefore, '', 'GET', undefined, signal);
      if (page.revision !== value.revision) break;
      value = { ...page, messages: [...page.messages, ...value.messages] };
    }
    if (!signal?.aborted) setInbox(old => old && old.revision > value.revision ? old : value);
  }, [base, request]);
  useEffect(() => {
    const controller = new AbortController(); let timer: number | undefined;
    const poll = async () => {
      try {
        const support = await request<{ messageQueue?: number; claudeBoundMessages?: number }>('/agent-capabilities', '', 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return;
        setAvailable(support.messageQueue === 1);
        setBoundWaiting(support.messageQueue === 1 && support.claudeBoundMessages === 1);
        if (support.messageQueue === 1) await refresh(controller.signal);
      } catch { /* The main session connection handles authentication recovery. */ }
      if (!controller.signal.aborted) timer = window.setTimeout(() => { void poll(); }, 1500);
    };
    void poll();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [request, refresh]);
  const perform = async (action: 'resume' | 'cancel', messageId?: string) => {
    if (!inbox || posting) return;
    const data = pending ?? { requestId: projectRequestId(), revision: inbox.revision, action, ...(messageId ? { messageId } : {}) };
    try { sessionStorage.setItem(key, JSON.stringify(data)); } catch { setError('Enable session storage before changing the queue.'); return; }
    setPending(data); setPosting(true); setError('');
    try {
      await request(base + '/control', token, 'POST', data);
      sessionStorage.removeItem(key); setPending(null); await refresh();
    } catch (failure) {
      if ([400,404,409].includes((failure as ProjectRequestError).status ?? 0)) { sessionStorage.removeItem(key); setPending(null); }
      setError((failure as Error).message); await refreshAuth().catch(() => undefined); await refresh().catch(() => undefined);
    } finally { setPosting(false); }
  };
  return { inbox, available, boundWaiting, error, posting, pending, refresh, perform };
}
