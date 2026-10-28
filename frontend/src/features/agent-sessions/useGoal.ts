import { useCallback, useEffect, useRef, useState } from 'react';
import type { AgentSession } from '../../../../shared/agent-sessions';
import type { GoalAction, GoalCommand, GoalReceipt, SessionGoal } from '../../../../shared/agent-inputs';
import { projectRequestId, ProjectRequestError, sessionPath, useSessionApi } from './api';

const uuid = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;
function stored(key: string): GoalCommand | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) ?? 'null');
    return value && uuid.test(value.requestId) && Number.isSafeInteger(value.revision) && value.revision >= 0
      && ['save', 'play', 'pause', 'stop'].includes(value.action)
      && (value.action !== 'save' || (typeof value.objective === 'string' && value.objective.length <= 16000)) ? value : null;
  } catch { return null; }
}

export function useGoal(projectId: string, sessionId: string, session: AgentSession | null, token: string,
  refreshAuth: () => Promise<void>, refreshSession: () => Promise<void>) {
  const { request, scope } = useSessionApi();
  const base = sessionPath(projectId, sessionId) + '/goal';
  const key = `studio.goal.${scope}.${projectId}.${sessionId}`;
  const [goal, setGoal] = useState<SessionGoal | null>(null);
  const [available, setAvailable] = useState(false), [execution, setExecution] = useState(false);
  const [readback, setReadback] = useState(false), [checking, setChecking] = useState(false);
  const [pending, setPending] = useState<GoalCommand | null>(() => stored(key));
  const [posting, setPosting] = useState(false), [error, setError] = useState('');
  const [checkAgain, setCheckAgain] = useState(false), [refresh, setRefresh] = useState(0);
  const generation = useRef(0), inflight = useRef(false);
  useEffect(() => { const current = ++generation.current; return () => { generation.current = current + 1; }; }, [base]);
  const observe = useCallback((value: SessionGoal) => {
    if (value.sessionId !== sessionId || value.owner.id !== projectId || value.owner.type !== scope)
      throw new Error('This Goal belongs to another session.');
    setGoal((previous) => {
      if (previous && previous.revision > value.revision) return previous;
      if (previous?.revision === value.revision && previous.goal && value.goal
        && (previous.goal.updatedAt > value.goal.updatedAt || previous.goal.tokensUsed > value.goal.tokensUsed
          || previous.goal.timeUsedSeconds > value.goal.timeUsedSeconds)) return previous;
      return value;
    });
  }, [projectId, sessionId, scope]);
  useEffect(() => {
    const controller = new AbortController(), current = generation.current;
    let timer: number | undefined;
    const load = async () => {
      const [state, support] = await Promise.all([
        request<{ goal: SessionGoal }>(base, '', 'GET', undefined, controller.signal),
        request<{ nativeGoals?: number; nativeGoalExecution?: number; nativeGoalReadback?: number; nativeImageInputs?: number; documentInputs?: number; enabled?: boolean }>('/agent-capabilities', '', 'GET', undefined, controller.signal),
      ]);
      if (controller.signal.aborted || current !== generation.current) return;
      observe(state.goal); setAvailable(support.nativeGoals === 1 && support.enabled !== false);
      setExecution(support.nativeGoalExecution === 2 && support.nativeImageInputs === 1 && support.documentInputs === 1 && support.enabled !== false);
      setReadback(support.nativeGoalReadback === 1);
      if (support.nativeGoals === 1 && (support.nativeGoalExecution !== 2 || support.nativeImageInputs !== 1 || support.documentInputs !== 1))
        timer = window.setTimeout(() => setRefresh((value) => value + 1), 3000);
    };
    void load().catch((failure: Error) => { if (!controller.signal.aborted) { setError(failure.message); setAvailable(false); } });
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [base, request, observe, refresh]);

  const accept = useCallback((receipt: GoalReceipt, data: GoalCommand) => {
    if (receipt.requestId !== data.requestId || receipt.action !== data.action) throw new Error('The Goal receipt does not match the original request.');
    observe(receipt.snapshot);
    if (receipt.state === 'pending') return;
    sessionStorage.removeItem(key); setPending(null); setCheckAgain(false);
    if (receipt.state === 'confirmed') {
      if (data.action === 'save') sessionStorage.removeItem(key + '.draft');
      setError('');
    } else setError(receipt.reason ?? 'The original Goal request was not confirmed. Pause before changing it.');
  }, [key, observe]);

  useEffect(() => {
    if (!pending || posting) return;
    const controller = new AbortController(); let timer: number | undefined, attempts = 0;
    const check = async () => {
      try {
        const result = await request<{ receipt: GoalReceipt }>(base + '/requests/' + pending.requestId, '', 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return;
        accept(result.receipt, pending);
        if (result.receipt.state !== 'pending') return;
      } catch (failure) {
        if (controller.signal.aborted) return;
        const issue = failure as ProjectRequestError;
        if (issue.status === 403) await refreshAuth().catch(() => undefined);
        if (++attempts >= 8) { setCheckAgain(true); setError('The original Goal request is unconfirmed. Check its receipt or retry the same request.'); return; }
      }
      if (!controller.signal.aborted) timer = window.setTimeout(() => { void check(); }, 500);
    };
    void check();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [pending, posting, base, request, accept, refreshAuth, refresh]);

  async function submit(data: GoalCommand): Promise<boolean> {
    if (inflight.current) return false;
    try { sessionStorage.setItem(key, JSON.stringify(data)); }
    catch { setError('Enable session storage before changing a Goal.'); return false; }
    const current = generation.current;
    inflight.current = true; setPending(data); setPosting(true); setError(''); setCheckAgain(false);
    try {
      const result = await request<{ receipt: GoalReceipt }>(base, token, 'POST', data);
      if (current !== generation.current) return true;
      accept(result.receipt, data); return result.receipt.state !== 'failed';
    } catch (failure) {
      if (current !== generation.current) return true;
      const issue = failure as ProjectRequestError; setError(issue.message);
      if (issue.status && issue.status < 500) {
        sessionStorage.removeItem(key); setPending(null);
        await refreshSession().catch(() => undefined); setRefresh((value) => value + 1);
        if (issue.status === 403) await refreshAuth().catch(() => undefined);
        return false;
      }
      // Keep exactly this body/ID. Only reads happen automatically after loss.
      return true;
    } finally {
      inflight.current = false;
      if (current === generation.current) setPosting(false);
    }
  }
  async function perform(action: GoalAction, objective?: string, revision?: number) {
    if (!goal || !available || pending || posting || checking || !session) return false;
    return submit({ requestId: projectRequestId(), revision: revision ?? goal.revision, action,
      ...(action === 'save' ? { objective: objective ?? '' } : {}), ...(action === 'play' ? { sessionRevision: session.revision } : {}) });
  }
  async function check() {
    setCheckAgain(false); setRefresh((value) => value + 1);
    // An outstanding mutation is reconciled only through its original receipt.
    if (pending || inflight.current || checking || !readback) return;
    const current = generation.current; setChecking(true);
    try {
      const result = await request<{ goal: SessionGoal }>(base + '/readback', token, 'POST', {});
      if (current === generation.current) observe(result.goal);
    } catch (failure) {
      if (current !== generation.current) return;
      const issue = failure as ProjectRequestError; setError(issue.message);
      if (issue.status === 403) await refreshAuth().catch(() => undefined);
    } finally { if (current === generation.current) setChecking(false); }
  }
  return { goal, available, execution, pending, posting, checking, error, checkAgain, observe, perform,
    changing: checking || posting || !!pending || goal?.phase === 'pending', draftKey: key + '.draft',
    retry: () => pending ? submit(pending) : Promise.resolve(false),
    check };
}
