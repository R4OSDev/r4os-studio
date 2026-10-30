import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentRun, AgentSession } from '../../../../shared/agent-sessions';
import type { AfterResponseTarget, MessageTarget, SessionMessage, SessionMessageInput } from '../../../../shared/agent-messages';
import { ProjectRequestError, projectRequestId, sessionPath, useSessionApi } from './api';

type RunInput = { requestId: string; revision: number; text: string; attachments?: string[] };
type Pending = { input: RunInput | SessionMessageInput; transport: 'run' | 'message'; draftToken: string; submissionError?: string };
function readPending(key: string): Pending | null {
  try {
    const stored = JSON.parse(sessionStorage.getItem(key) ?? 'null');
    const input = stored?.input ?? stored;
    if (!input || typeof input.requestId !== 'string' || typeof input.text !== 'string' || !Number.isInteger(input.revision)) return null;
    return stored.input ? stored : { input, transport: 'run', draftToken: 'legacy' };
  } catch { return null; }
}

export function useMessageComposer(projectId: string, sessionId: string, session: AgentSession | null, token: string,
  refreshAuth: () => Promise<void>, accepted: (ids: string[], run?: AgentRun) => void) {
  const { request, scope } = useSessionApi(), base = sessionPath(projectId, sessionId);
  const prefix = scope === 'skill' ? 'studio.skill.session.' : 'studio.session.';
  const pendingKey = prefix + 'run.' + sessionId, draftKey = prefix + 'draft.' + sessionId, versionKey = draftKey + '.version';
  const [pending, setPending] = useState(() => readPending(pendingKey));
  const pendingRef = useRef(pending);
  const [text, setText] = useState(() => { try { return sessionStorage.getItem(draftKey) ?? pending?.input.text ?? ''; } catch { return ''; } });
  const textRef = useRef(text), inFlight = useRef(false);
  const draftToken = useRef((() => { try { return sessionStorage.getItem(versionKey) ?? 'legacy'; } catch { return 'legacy'; } })());
  const [sending, setSending] = useState(false), [error, setError] = useState('');
  const [receipt, setReceipt] = useState<SessionMessage | null>(null);
  const edit = (value: string) => {
    textRef.current = value; draftToken.current = projectRequestId(); setText(value);
    try { sessionStorage.setItem(draftKey, value); sessionStorage.setItem(versionKey, draftToken.current); } catch { /* Sending reports storage failure. */ }
  };
  const acknowledge = useCallback((data: Pending, run?: AgentRun) => {
    if (pendingRef.current?.input.requestId !== data.input.requestId) return;
    accepted(data.input.attachments ?? [], run);
    if (draftToken.current === data.draftToken) {
      textRef.current = ''; setText(''); sessionStorage.removeItem(draftKey); sessionStorage.removeItem(versionKey);
    }
    pendingRef.current = null; sessionStorage.removeItem(pendingKey); setPending(null); setReceipt(null); setError('');
  }, [accepted, draftKey, pendingKey, versionKey]);
  const observe = useCallback((data: Pending, value: SessionMessage) => {
    if (pendingRef.current?.input.requestId !== data.input.requestId) return;
    if (value.state === 'accepted' || value.mode === 'queue' && ['queued','dispatching'].includes(value.state)) acknowledge(data);
    else { setReceipt(value); setError(value.error ?? 'Checking the original message acceptance…'); }
  }, [acknowledge]);
  const check = useCallback(async (data: Pending, signal?: AbortSignal) => {
    if (data.transport === 'run') {
      try {
        const value = await request<{ run: AgentRun }>(base + '/runs/requests/' + data.input.requestId, '', 'GET', undefined, signal);
        if (!signal?.aborted) acknowledge(data, value.run);
      } catch (failure) {
        if ((failure as ProjectRequestError).status === 404) {
          throw new Error(data.submissionError ?? 'No run receipt is available yet. Your input is preserved. Use Retry same request to submit the original input.', { cause: failure });
        }
        throw failure;
      }
    } else {
      const value = await request<SessionMessage>(base + '/messages/' + data.input.requestId, '', 'GET', undefined, signal);
      if (!signal?.aborted) observe(data, value);
    }
  }, [base, request, acknowledge, observe]);
  useEffect(() => {
    if (!pending || sending) return;
    const controller = new AbortController(); let timer: number | undefined, attempts = 0;
    const poll = async () => {
      try { await check(pending, controller.signal); }
      catch (failure) { if (!controller.signal.aborted && pendingRef.current?.input.requestId === pending.input.requestId) setError((failure as Error).message); }
      if (!controller.signal.aborted && ++attempts < 20) timer = window.setTimeout(() => { void poll(); }, 1000);
    };
    void poll();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [pending, sending, check]);
  const submit = async (mode: 'run' | 'queue' | 'steer', ids: string[], target?: MessageTarget, retry = false, afterRun?: AfterResponseTarget) => {
    if (!session || inFlight.current) return;
    const original = pendingRef.current;
    const data: Pending = original ?? { transport: mode === 'run' ? 'run' : 'message', draftToken: draftToken.current,
      input: { requestId: projectRequestId(), revision: session.revision, text: textRef.current,
        ...(ids.length ? { attachments: ids } : {}), ...(mode === 'run' ? {} : { mode, ...(target ? { target } : {}), ...(afterRun ? { afterRun } : {}) }) } };
    try { sessionStorage.setItem(pendingKey, JSON.stringify(data)); } catch { setError('Enable session storage before sending.'); return; }
    pendingRef.current = data; setPending(data); inFlight.current = true; setSending(true); setError('');
    try {
      if (original && !retry) await check(data);
      else if (data.transport === 'run') {
        const result = await request<{ run: AgentRun }>(base + '/runs', token, 'POST', data.input); acknowledge(data, result.run);
      } else {
        const result = await request<{ message: SessionMessage }>(base + '/messages', token, 'POST', data.input); observe(data, result.message);
      }
    } catch (failure) {
      if (pendingRef.current?.input.requestId === data.input.requestId) {
        const message = (failure as Error).message;
        if (!original || retry) {
          const saved = { ...data, submissionError: message };
          pendingRef.current = saved; setPending(saved);
          try { sessionStorage.setItem(pendingKey, JSON.stringify(saved)); } catch { /* Keep the original input in memory. */ }
        }
        setError(message);
      }
      if ((failure as ProjectRequestError).status === 403) await refreshAuth().catch(() => undefined);
    } finally { inFlight.current = false; setSending(false); }
  };
  const restore = () => {
    if (!pending || sending) return;
    if (textRef.current !== pending.input.text && textRef.current && !window.confirm('Replace the current draft with the preserved original message?')) return;
    edit(pending.input.text);pendingRef.current=null;sessionStorage.removeItem(pendingKey);setPending(null);setReceipt(null);setError('');
  };
  return { text, edit, pending, receipt, sending, error, submit, restore };
}
