import { useSessionOptions } from './useSessionOptions';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { AgentSession } from '../../../../shared/agent-sessions';
import { useSessionApi, ProjectRequestError, projectRequestId,sessionPath,busyRun } from './api';
import {useModelChoice} from './useModelChoice';

import { availableModels, effortLabel, providerAllowed, providerLabel } from './modelChoices';
import {ContextIndicator} from './ContextIndicator';

type Choice = Pick<AgentSession, 'providerId' | 'model' | 'effort' | 'fastMode'>;

export function ComposerSettings({ session, projectId, token, disabled, active=false, saved, busyChanged, unconfirmedChanged, refreshAuth }: {
  session: AgentSession; projectId: string; token: string; disabled: boolean; active?:boolean;
  saved: (session: AgentSession) => void; busyChanged: (value: boolean) => void; refreshAuth: () => Promise<void>;
  unconfirmedChanged?:(value:boolean)=>void;
}) {
  const { request: projectRequest, scope } = useSessionApi();
  const { options, error: optionsError } = useSessionOptions(projectId);
  const [error, setError] = useState('');
  const [pending, setPending] = useState<Choice | null>(null), inflight = useRef(false);
  const focusTarget=useRef<Element|null>(null);
  const modelChoice=useModelChoice(projectId,session.id,token,saved,refreshAuth);
  useEffect(()=>{busyChanged(!!pending||modelChoice.busy);return()=>busyChanged(false);},[pending,modelChoice.busy,busyChanged]);
  useEffect(()=>{unconfirmedChanged?.(!!modelChoice.pending);return()=>unconfirmedChanged?.(false);},[modelChoice.pending,unconfirmedChanged]);

  const choice = pending ?? {...session,...(modelChoice.pending??session.pendingModel?.choice)};
  const account = options?.providers.find((value) => value.id === choice.providerId);
  const model = account?.models.find((value) => value.id === choice.model);
  const deferred=active||!!session.pendingModel;
  const controlsDisabled=disabled||!!pending||modelChoice.busy||!!modelChoice.pending||!options||(deferred&&!session.latestRun);
  useLayoutEffect(()=>{
    if(controlsDisabled||!focusTarget.current)return;
    const control=focusTarget.current;focusTarget.current=null;
    if(control instanceof HTMLElement&&control.isConnected&&document.activeElement===document.body)control.focus({preventScroll:true});
  },[controlsDisabled]);
  async function change(values: Partial<Choice>) {
    if (controlsDisabled || inflight.current) return;
    focusTarget.current = document.activeElement;
    inflight.current = true;
    const next={providerId:choice.providerId,model:choice.model,effort:choice.effort,fastMode:choice.fastMode,...values};
    setError('');
    const path = sessionPath(projectId, session.id);
    try {
      if(deferred&&session.latestRun) {
        await modelChoice.send({requestId:projectRequestId(),revision:session.revision,selectionRevision:session.selectionRevision??0,
          afterRunId:session.latestRun.id,model:next.model,effort:next.effort,fastMode:next.fastMode});
        return;
      }
      setPending(next);
      const result = await projectRequest<{ session: AgentSession }>(path + '/settings', token, 'PATCH', { revision: session.revision,selectionRevision:session.selectionRevision??0, ...values });
      saved(result.session);
    } catch (failure) {
      setError((failure as Error).message);
      if ((failure as ProjectRequestError).status === 403) await refreshAuth().catch(() => undefined);
      // Resolve a conflict/lost save reply by reading; never repeat the mutation.
      try { saved((await projectRequest<{ session: AgentSession }>(path)).session); } catch { /* Retain the original error and last known selection. */ }
    } finally {
      inflight.current = false; setPending(null);

    }
  }

  return <div className="agent-composer-settings">
    <fieldset className="agent-model-controls" aria-label="Run settings" aria-busy={!!pending||modelChoice.busy}>
      <label className="agent-account-choice"><span>Account</span>
        <select aria-label="Account" value={choice.providerId} disabled={controlsDisabled||deferred} onChange={(event) => {
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
      <label className="agent-model-choice"><span>Model</span>
        <select aria-label="Model" value={choice.model} disabled={controlsDisabled||!account?.models.length} onChange={(event) => {
          const nextModel = account?.models.find((value) => value.id === event.target.value);
          void change({ model: event.target.value,
            effort: nextModel?.efforts.includes(choice.effort) ? choice.effort : nextModel?.defaultEffort ?? '',
            fastMode: choice.fastMode && !!nextModel?.fastModeAvailable });
        }}>
          {!model && <option value={choice.model}>{choice.model}</option>}
          {account?.models.map((value) => <option key={value.id} value={value.id} disabled={value.available === false}>{value.name}{value.available === false ? ' · unavailable' : ''}</option>)}
        </select>
      </label>
      <label><span>Reasoning</span>
        <select aria-label="Reasoning" value={choice.effort} disabled={controlsDisabled||!model} onChange={(event) => void change({ effort: event.target.value })}>
          {!model?.efforts.includes(choice.effort) && <option value={choice.effort}>{effortLabel(choice.effort, account)}</option>}
          {model?.efforts.map((value) => <option key={value} value={value}>{effortLabel(value, account)}</option>)}
        </select>
      </label>
      <div className="agent-fast-context">{(model?.fastModeAvailable || choice.fastMode) && <label><span>Fast Mode</span>
        <select aria-label="Fast Mode" value={choice.fastMode ? 'on' : 'off'} disabled={controlsDisabled||!model} onChange={(event) => void change({ fastMode: event.target.value === 'on' })}>
          <option value="off">Off</option><option value="on" disabled={!model?.fastModeAvailable}>On</option>
        </select>
      </label>}<ContextIndicator key={scope+projectId+session.id} projectId={projectId} sessionId={session.id} context={session.context}/></div>
    </fieldset>
    {session.pendingModel&&<div className="agent-pending-model" role="status">
      <p>{busyRun(session.latestRun?.state)?`Current run: ${session.latestRun?.selection?.model??session.model} · `:''}Next run: {session.pendingModel.choice.model} · {session.pendingModel.state==='blocked'?'Blocked':'Pending'}</p>
      {session.pendingModel.reason&&<p>{session.pendingModel.reason}</p>}
      <button type="button" disabled={controlsDisabled} onClick={()=>void change({model:session.model,effort:session.effort,fastMode:session.fastMode})}>Cancel model change</button>
    </div>}
    {!session.pendingModel&&busyRun(session.latestRun?.state)&&session.latestRun?.selection&&session.latestRun.selection.model!==session.model
      &&<p className="agent-terminal-hint" role="status">Current run: {session.latestRun.selection.model} · Following inputs: {session.model}</p>}
    {modelChoice.pending&&<div className="agent-pending-model" role="status">
      <p>{modelChoice.busy?'Checking model choice…':'Model choice unconfirmed.'}</p>
      <button type="button" disabled={modelChoice.busy} onClick={()=>void modelChoice.read()}>Check original choice</button>
      <button type="button" disabled={modelChoice.busy} onClick={()=>void modelChoice.retry()}>Retry same choice</button>
    </div>}
    {session.engine.kind !== 'studio' && <p className="agent-terminal-hint">This conversation uses a native connection. Review a conversion in Session settings → Conversation to use a different direct connection.</p>}
    {model?.available === false && <p className="agent-terminal-hint" role="status">{model.unavailableReasons?.join(' ')}</p>}
    {(error ||modelChoice.error|| optionsError) && <p className="agent-choice-error" role="alert">{error ||modelChoice.error|| optionsError}</p>}
  </div>;
}
