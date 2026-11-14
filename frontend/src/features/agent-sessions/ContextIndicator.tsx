import {useState} from 'react';
import {ContextInspector} from './ContextInspector';
import {SessionGauge} from './SessionGauge';
import type {SessionContext} from '../../../../shared/agent-sessions';
import './context.css';

export function ContextIndicator({context,projectId,sessionId,providerId,model}:{
  context?:SessionContext;projectId:string;sessionId:string;providerId:string;model:string;
}) {
  const [open,setOpen]=useState(false);
  const measured=context?.measurement;
  const matches=context?.sessionId===sessionId && measured?.providerId===providerId && measured?.model===model;
  const native=context?.engine==='codex' && context.state==='available'
    && context.providerId===providerId && context.requestedModel===model;
  const used=matches?measured?.inputTokens:native?context.last?.inputTokens:null;
  const capacity=matches?measured?.inputLimit:native?context.capacityTokens:null;
  const known=typeof used==='number' && Number.isFinite(used) && used>=0
    && typeof capacity==='number' && Number.isFinite(capacity) && capacity>0;
  const ratio=known?used/capacity:null;
  return <>
    <SessionGauge label="Context" ratio={ratio} pulse={ratio!==null&&ratio>.5}
      state={context?.state??'unavailable'} open={open} onOpen={()=>setOpen(true)}/>
    {open&&<ContextInspector key={projectId+':'+sessionId} projectId={projectId} sessionId={sessionId} context={context} close={()=>setOpen(false)}/>}
  </>;
}
