import type { AgentRun, SessionQuotaWait } from '../../../../shared/agent-sessions';
import type { useQuotaWait } from './useQuotaWait';
import { busyRun } from './api';
import './quota-wait.css';
type Control=ReturnType<typeof useQuotaWait>;
function date(value:string|null|undefined) {
  return value&&Number.isFinite(Date.parse(value))?new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'long'}).format(new Date(value)):null;
}
export function QuotaWaitStatus({wait,run,control}:{wait?:SessionQuotaWait;run?:AgentRun|null;control:Control}) {
  const waiting=!!wait?.active&&wait.state==='waiting'&&!busyRun(run?.state);
  const resets=Array.from(new Set([wait?.resetAt,...(wait?.observation?.windows??[]).map(w=>w.resetAt)].map(date).filter((v):v is string=>!!v)));
  return <>
    {waiting&&<section className="agent-quota-wait" aria-label="Waiting for limit reset">
      <div><strong>Waiting for limit reset</strong><p>{wait.model??'Original model'}</p>
        <p>{resets.length?resets.map(value=><span className="agent-quota-reset" key={value}>Reported reset: {value}</span>):'Reset time unknown'}</p>
        {date(wait.observation?.checkedAt)&&<p>Last observation: {date(wait.observation?.checkedAt)}</p>}
        {date(wait.observation?.nextCheckAt)&&<p>Next check: {date(wait.observation?.nextCheckAt)}</p>}
        {wait.observation?.reason&&<p>{wait.observation.reason}</p>}
      </div>
      <button type="button" className="agent-quota-action" disabled={control.busy} onClick={()=>void control.stop()}>Stop waiting</button>
      {control.busy&&<p role="status">Confirming original cancellation…</p>}
      {control.pending&&!control.busy&&<p role="status">{control.notFound?'Original cancellation not found. Press Stop waiting to retry that exact request.':'Cancellation is unconfirmed. Press Stop waiting to read its original result.'}</p>}
    </section>}
    {control.error&&<p className="agent-error" role="status">{control.error}</p>}
    {control.notice&&<p role="status">{control.notice}</p>}
    {!waiting&&control.pending&&!control.busy&&<button type="button" className="agent-quota-action" onClick={()=>void control.read()}>Check original cancellation</button>}
  </>;
}
