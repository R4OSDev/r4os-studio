import { useEffect, useRef, useState } from 'react';
import type { AgentSession, SessionOptions } from '../../../../shared/agent-sessions';
import { useSessionApi, ProjectRequestError, sessionPath } from './api';

import { availableModels, effortLabel, providerAllowed, providerLabel } from './modelChoices';
import {ContextIndicator} from './ContextIndicator';

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
  const controlsDisabled=disabled||!!pending||!options;
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
    <fieldset className="agent-model-controls" aria-label="Run settings" aria-busy={!!pending}>
      <label className="agent-account-choice"><span>Account</span>
        <select aria-label="Account" value={choice.providerId} disabled={controlsDisabled} onChange={(event) => {
          const nextAccount = options?.providers.find((value) => value.id === event.target.value);
          const nextModel = availableModels(nextAccount).find((value) => value.id === choice.model) ?? availableModels(nextAccount)[0];
          void change({ providerId: event.target.value, model: nextModel?.id ?? '',
            effort: nextModel?.efforts.includes(choice.effort) ? choice.effort : nextModel?.defaultEffort ?? '',
            fastMode: choice.fastMode && !!nextModel?.fastModeAvailable });
        }}>
          {!account && <option value={choice.providerId}>{options ? 'Unavailable account' : 'Loading accounts…'}</option>}
          {options?.providers.map((value) => <option key={value.id} value={value.id} disabled={!availableModels(value).length || !providerAllowed(session, value)}>{providerLabel(value)}</option>)}
        </select>
      </label>
      <div className="agent-model-context"><label className="agent-model-choice"><span>Model</span>
        <select aria-label="Model" value={choice.model} disabled={controlsDisabled||!account?.models.length} onChange={(event) => {
          const nextModel = account?.models.find((value) => value.id === event.target.value);
          void change({ model: event.target.value,
            effort: nextModel?.efforts.includes(choice.effort) ? choice.effort : nextModel?.defaultEffort ?? '',
            fastMode: choice.fastMode && !!nextModel?.fastModeAvailable });
        }}>
          {!model && <option value={choice.model}>{choice.model}</option>}
          {account?.models.map((value) => <option key={value.id} value={value.id} disabled={value.available === false}>{value.name}{value.available === false ? ' · unavailable' : ''}</option>)}
        </select>
      </label><ContextIndicator context={session.context}/></div>
      <label><span>Reasoning</span>
        <select aria-label="Reasoning" value={choice.effort} disabled={controlsDisabled||!model} onChange={(event) => void change({ effort: event.target.value })}>
          {!model?.efforts.includes(choice.effort) && <option value={choice.effort}>{effortLabel(choice.effort, account)}</option>}
          {model?.efforts.map((value) => <option key={value} value={value}>{effortLabel(value, account)}</option>)}
        </select>
      </label>
      <label><span>Fast Mode</span>
        <select aria-label="Fast Mode" value={choice.fastMode ? 'on' : 'off'} disabled={controlsDisabled||!model} onChange={(event) => void change({ fastMode: event.target.value === 'on' })}>
          <option value="off">Off</option><option value="on" disabled={!model?.fastModeAvailable}>On</option>
        </select>
      </label>
    </fieldset>
    {session.engine.api && <p className="agent-terminal-hint">API connection is fixed for this conversation. Choose another provider in a new session.</p>}
    {model?.available === false && <p className="agent-terminal-hint" role="status">{model.unavailableReasons?.join(' ')}</p>}
    {error && <p className="agent-choice-error" role="alert">{error}</p>}
  </div>;
}
