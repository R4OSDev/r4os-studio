import { useId, useState } from 'react';
import type { ReactNode } from 'react';

export const gaugePercent = new Intl.NumberFormat('en-US',{style:'percent',maximumFractionDigits:1});

export function SessionGauge({label,ratio,details,open,onOpen,pulse=false,state}:{
  label:string;ratio:number|null;details?:ReactNode;open?:boolean;onOpen?:()=>void;pulse?:boolean;state?:string;
}) {
  const tooltip=useId();
  const [dismissed,setDismissed]=useState(false);
  const fill=Math.min(1,ratio??0);
  const dial=<svg viewBox="0 0 52 34" aria-hidden="true">
    <path className="context-track" d="M4 26 A22 22 0 0 1 48 26"/>
    {ratio!==null&&<><path className="context-fill" d="M4 26 A22 22 0 0 1 48 26" pathLength="100" strokeDasharray={`${fill*100} 100`}/>
      <path className="context-needle" strokeWidth="1.6" d="M26 26 L26 10" transform={`rotate(${-90+fill*180} 26 26)`}/>
      <circle className="context-hub" cx="26" cy="26" r="2.5"/></>}
  </svg>;
  const className = 'agent-gauge'+(pulse?' pulse':'')+(ratio===null?' unknown':'');
  return <div className="agent-context-control" data-tooltip-dismissed={dismissed || open === true}
    onMouseEnter={()=>setDismissed(false)} onFocus={()=>setDismissed(false)}
    onKeyDown={event=>{if(event.key==='Escape')setDismissed(true);}}>
    <span className="agent-context-label">{label}</span>
    <div className="agent-gauge-anchor">
      {onOpen?<button type="button" className={className+' agent-context'} data-state={state}
        aria-label="Context usage. Show details" aria-describedby={tooltip} aria-haspopup="dialog"
        aria-expanded={open} onClick={onOpen}>{dial}{ratio===null&&<span aria-hidden="true">—</span>}</button>
        :<div className={className+' agent-usage'} tabIndex={0} role="meter" aria-label="Usage"
          aria-valuemin={0} aria-valuemax={100} aria-valuenow={ratio===null?undefined:fill*100}
          aria-valuetext={ratio===null?'Not reported':gaugePercent.format(ratio)+' used'}
          aria-describedby={tooltip}>{dial}</div>}
      <div id={tooltip} className="agent-gauge-tooltip" role="tooltip">
        {details??(ratio===null?'Context usage unavailable':gaugePercent.format(ratio)+' used')}
      </div>
    </div>
  </div>;
}
