import {useState} from 'react';
import {ContextInspector} from './ContextInspector';
import type {SessionContext} from '../../../../shared/agent-sessions';
import './context.css';

const percent=new Intl.NumberFormat('en-US',{style:'percent',maximumFractionDigits:4});

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
  const ratio=known?used/capacity:0,fill=Math.min(1,ratio),pulse=known&&ratio>.5;
  const state=context?.state??'unavailable';
  const value=known?Math.round(ratio*100)+'%':'—';
  const label='Context usage: '+(known?percent.format(ratio):state)+'. Show details';
  return <div className="agent-context-control">
    <span className="agent-context-label">Context</span>
    <button type="button" className={'agent-context'+(pulse?' pulse':'')+(!known?' unknown':'')}
      data-state={state} aria-label={label} aria-haspopup="dialog" aria-expanded={open} onClick={()=>setOpen(true)}>
      <svg viewBox="0 0 52 34" aria-hidden="true">
        <path className="context-track" d="M4 26 A22 22 0 0 1 48 26"/>
        {known&&<><path className="context-fill" d="M4 26 A22 22 0 0 1 48 26" pathLength="100" strokeDasharray={`${fill*100} 100`}/>
          <path className="context-needle" d="M26 26 L26 10" transform={`rotate(${-90+fill*180} 26 26)`}/><circle className="context-hub" cx="26" cy="26" r="2.5"/></>}
      </svg><span aria-hidden="true">{value}</span>
    </button>
    {known&&<span className="agent-context-meter" role="meter" aria-label="Context usage" aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={fill*100} aria-valuetext={percent.format(ratio)+(matches?' of the effective input limit':' of the reported effective context window')}/>}
    {open&&<ContextInspector key={projectId+':'+sessionId} projectId={projectId} sessionId={sessionId} context={context} close={()=>setOpen(false)}/>}
  </div>;
}
