import { useEffect, useRef, useState } from 'react';
import type { AgentSession, SessionOptions } from '../../../../shared/agent-sessions';
import { useSessionApi, ProjectRequestError, sessionPath } from './api';

type Choice = Pick<AgentSession, 'providerId' | 'model' | 'effort' | 'fastMode'>;

export function ComposerSettings({ session, projectId, token, disabled, saved, busyChanged, refreshAuth }: {
  session: AgentSession; projectId: string; token: string; disabled: boolean;
  saved: (session: AgentSession) => void; busyChanged: (value: boolean) => void; refreshAuth: () => Promise<void>;
}) {
  const { request: projectRequest } = useSessionApi();
  const [options, setOptions] = useState<SessionOptions | null>(null), [error, setError] = useState('');
  const [pending, setPending] = useState<Choice | null>(null), inflight = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    void projectRequest<SessionOptions>(sessionPath(projectId) + '/options', '', 'GET', undefined, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setOptions(value); })
      .catch((failure: Error) => { if (!controller.signal.aborted) setError(failure.message); });
    return () => controller.abort();
  }, [projectId, projectRequest]);
  useEffect(() => () => busyChanged(false), [busyChanged]);

  const choice = pending ?? session;
  const account = options?.providers.find((value) => value.id === choice.providerId);
  const model = account?.models.find((value) => value.id === choice.model);
  async function change(values: Partial<Choice>) {
    if (disabled || inflight.current) return;
    const control = document.activeElement;
    inflight.current = true;
    setPending({ providerId: session.providerId, model: session.model, effort: session.effort, fastMode: session.fastMode, ...values });
    busyChanged(true); setError('');
    const path = sessionPath(projectId, session.id);
    try {
      const result = await projectRequest<{ session: AgentSession }>(path + '/settings', token, 'PATCH', { revision: session.revision, ...values });
      saved(result.session);
    } catch (failure) {
      setError((failure as Error).message);
      if ((failure as ProjectRequestError).status === 403) await refreshAuth().catch(() => undefined);
      // Resolve a conflict/lost save reply by reading; never repeat the mutation.
      try { saved((await projectRequest<{ session: AgentSession }>(path)).session); } catch { /* Retain the original error and last known selection. */ }
    } finally {
      inflight.current = false; setPending(null); busyChanged(false);
      requestAnimationFrame(() => {
        if (control instanceof HTMLElement && control.isConnected && document.activeElement === document.body) control.focus({ preventScroll: true });
      });
    }
  }

  return <div className="agent-composer-settings">
    <fieldset className="agent-model-controls" aria-label="Run settings" aria-busy={!!pending} disabled={disabled || !!pending || !options}>
      <label className="agent-account-choice"><span>Account</span>
        <select aria-label="Account" value={choice.providerId} onChange={(event) => {
          const nextAccount = options?.providers.find((value) => value.id === event.target.value);
          const nextModel = nextAccount?.models.find((value) => value.id === choice.model) ?? nextAccount?.models[0];
          void change({ providerId: event.target.value, model: nextModel?.id ?? '',
            effort: nextModel?.efforts.includes(choice.effort) ? choice.effort : nextModel?.defaultEffort ?? '',
            fastMode: choice.fastMode && !!nextModel?.fastModeAvailable });
        }}>
          {!account && <option value={choice.providerId}>{options ? 'Unavailable account' : 'Loading accounts…'}</option>}
          {options?.providers.map((value) => <option key={value.id} value={value.id} disabled={!value.models.length}>{value.name}</option>)}
        </select>
      </label>
      <label className="agent-model-choice"><span>Model</span>
        <select aria-label="Model" value={choice.model} disabled={!account?.models.length} onChange={(event) => {
          const nextModel = account?.models.find((value) => value.id === event.target.value);
          void change({ model: event.target.value,
            effort: nextModel?.efforts.includes(choice.effort) ? choice.effort : nextModel?.defaultEffort ?? '',
            fastMode: choice.fastMode && !!nextModel?.fastModeAvailable });
        }}>
          {!model && <option value={choice.model}>{choice.model}</option>}
          {account?.models.map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}
        </select>
      </label>
      <label><span>Reasoning</span>
        <select aria-label="Reasoning" value={choice.effort} disabled={!model} onChange={(event) => void change({ effort: event.target.value })}>
          {!model?.efforts.includes(choice.effort) && <option value={choice.effort}>{choice.effort}</option>}
          {model?.efforts.map((value) => <option key={value} value={value}>{value}</option>)}
        </select>
      </label>
      <label><span>Fast Mode</span>
        <select aria-label="Fast Mode" value={choice.fastMode ? 'on' : 'off'} disabled={!model} onChange={(event) => void change({ fastMode: event.target.value === 'on' })}>
          <option value="off">Off</option><option value="on" disabled={!model?.fastModeAvailable}>On</option>
        </select>
      </label>
    </fieldset>
    {error && <p className="agent-choice-error" role="alert">{error}</p>}
  </div>;
}
