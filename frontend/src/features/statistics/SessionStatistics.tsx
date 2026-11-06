import { watchVisible, watchSessionActivity } from '../agent-sessions/sessionActivity';
import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import type {GoalCommand,SessionGoal} from '../../../../shared/agent-inputs';
import {createPortal} from 'react-dom';
import type {GoalClockSnapshot,GoalTotalSnapshot} from '../../../../shared/statistics';
import {busyRun,sessionPath,useSessionApi} from '../agent-sessions/api';
import type {AgentRun} from '../../../../shared/agent-sessions';
import {StatisticsContent,useStatistics,duration} from './StatisticsPanel';

export function SessionStatistics({ownerId,sessionId,reauth,close,run,stop}:{ownerId:string;sessionId:string;reauth:()=>Promise<void>;close:()=>void;run?:AgentRun|null;stop:()=>Promise<void>}) {
 const api=useSessionApi(),dialog=useRef<HTMLDialogElement>(null),button=useRef<HTMLButtonElement>(null);
 const result=useStatistics(api.base+sessionPath(ownerId,sessionId)+'/statistics',reauth);
 useEffect(()=>{const element=dialog.current!,opener=document.activeElement;element.showModal();button.current?.focus();return()=>{element.close();if(opener instanceof HTMLElement && opener.isConnected)opener.focus();};},[]);
 return createPortal(<dialog ref={dialog} className="project-dialog statistics-dialog" aria-labelledby="session-statistics-title" onCancel={event=>{event.preventDefault();close();}}>
  <header className="project-dialog-header"><h2 id="session-statistics-title">Session statistics</h2></header>
  <div className="statistics-panel"><p>Reported token usage for this session.</p>
   {result.error && <p className="project-dialog-error" role="alert">Statistics unavailable: {result.error}</p>}
   {result.value?<StatisticsContent value={result.value} session/>:!result.error && <p role="status">Loading statistics…</p>}
   {result.value && <TotalGoalRuntime value={result.value.totalGoalRuntime} receivedAt={result.receivedAt} failed={!!result.error} />}
  </div>
  <footer className="project-actions">{busyRun(run?.state) && <button type="button" disabled={run?.state==='stopping'} onClick={()=>void stop()}>Stop current run</button>}<button type="button" onClick={result.refresh}>Refresh</button><button type="button" ref={button} onClick={close}>Close</button></footer>
 </dialog>,document.body);
}
function TotalGoalRuntime({value,receivedAt,failed}:{value?:GoalTotalSnapshot;receivedAt:number;failed:boolean}) {
 const [tick,setTick]=useState(0);
 useEffect(()=>{
  if(!value?.live || failed)return;
  const timer=window.setInterval(()=>{if(!document.hidden)setTick(performance.now());},250);
  return()=>window.clearInterval(timer);
 },[value,failed]);
 const live=value?.live,age=live?live.ageMs+Math.max(0,tick-receivedAt):0;
 const fresh=!!live && !failed && age<=live.staleAfterMs;
 let elapsed=value?.durationMs;
 if(elapsed!=null && fresh)try{elapsed=(BigInt(elapsed)+BigInt(Math.floor(age))).toString();}catch{elapsed=null;}
 const incomplete=failed || (!!live && !fresh) || value?.coverage.state==='partial';
 const unavailable=!value || value.durationMs==null;
 return <section className="statistics-goal-total" aria-label="Total Goal runtime">
  <dl className="statistics-grid"><div><dt>Total Goal runtime</dt><dd role="timer" aria-live="off">{duration(elapsed)}</dd></div></dl>
  <p className="statistics-coverage" role="status">{unavailable?'Goal time is not fully reported for this session.':incomplete?'Partial Goal time coverage. Only confirmed time is retained; unavailable live time is frozen.':fresh?'Recorded Goal time including the current execution.':'Recorded Goal time across original executions and keepalive cycles.'}</p>
  {value && <p className="statistics-help">{value.coverage.measuredExecutions} measured {value.coverage.measuredExecutions===1?'period':'periods'}{value.coverage.missingExecutions?` · ${value.coverage.missingExecutions} without a measurement`:''}. Pause and Stop exclude further keepalive time. Earlier measurements are preserved.</p>}
 </section>;
}
export function GoalRuntime({ownerId,sessionId,reauth,active=false,goal,pending}:{ownerId:string;sessionId:string;reauth:()=>Promise<void>;active?:boolean;goal?:SessionGoal|null;pending?:GoalCommand|null}) {
 const {request,scope}=useSessionApi(),url=sessionPath(ownerId,sessionId)+'/goal/clock',key=scope+url;
 const [sample,setSample]=useState<{key:string;clock:GoalClockSnapshot|null;arrival:number;error:boolean}>({key,clock:null,arrival:0,error:false});
 const [controlSample,setControlSample]=useState<{clock:GoalClockSnapshot|undefined;arrival:number}>(()=>({clock:goal?.keepalive?.clock,arrival:performance.now()}));
 const [held,setHeld]=useState<{key:string;duration:number|null}|null>(null);
 const [tick,setTick]=useState(0),live=useRef(false),latest=useRef({key,revision:goal?.keepalive?goal.revision:-1});
 useLayoutEffect(()=>{latest.current={key,revision:goal?.keepalive?goal.revision:-1};},[key,goal?.keepalive,goal?.revision]);
 useEffect(()=>{
  const clock=goal?.keepalive?.clock;let cancelled=false;
  queueMicrotask(()=>{if(!cancelled)setControlSample({clock,arrival:performance.now()});});
  return()=>{cancelled=true;};
 },[goal?.keepalive?.clock]);
 useEffect(()=>{
  const controller=new AbortController();let loading=false,timer:number|undefined,goalRevision=-1,runMarker='';
  async function load(){
   if(document.hidden || loading || controller.signal.aborted)return;loading=true;window.clearTimeout(timer);
   try{
    const value=await request<{clock:GoalClockSnapshot|null}>(url,'','GET',undefined,controller.signal);
    if(controller.signal.aborted || latest.current.key!==key)return;
    const clock=value.clock;
    if(clock?.mode==='keepalive' && (clock.owner?.type!==scope || clock.owner.id!==ownerId || clock.sessionId!==sessionId))throw new Error('The Goal clock belongs to another session.');
    if(latest.current.revision>=0 && clock && (clock.mode!=='keepalive' || (clock.controlRevision??-1)<latest.current.revision))return;
    const at=performance.now();live.current=clock?.state==='running';
    setSample(old=>{
     if(old.key===key && old.clock?.mode==='keepalive' && clock?.mode==='keepalive'
      && ((old.clock.controlRevision??-1)>(clock.controlRevision??-1)
        || old.clock.cycleId===clock.cycleId && old.clock.controlRevision===clock.controlRevision && old.clock.durationMs>clock.durationMs))return old;
     return {key,clock,arrival:at,error:false};
    });setTick(at);
   }catch(error){if(!controller.signal.aborted){live.current=false;setSample(old=>({...old,error:true}));if((error as {status?:number}).status===403)await reauth().catch(()=>undefined);}}
   finally{loading=false;if(!controller.signal.aborted && !document.hidden && (active || live.current))timer=window.setTimeout(()=>void load(),2000);}
  }
  void load();const frame=window.setInterval(()=>{if(!document.hidden && live.current)setTick(performance.now());},250);
  const stopVisible=watchVisible(()=>void load()),stopActivity=watchSessionActivity(scope,ownerId,sessionId,value=>{
   const event=value.event,payload=event?.payload as Record<string,unknown>|undefined;let changed=!!value.connected;
   if(event?.kind==='goal' && typeof payload?.revision==='number' && payload.revision>goalRevision){goalRevision=payload.revision;changed=true;}
   if(event?.kind==='run'){const next=String(payload?.id)+':'+String(payload?.state);if(next!==runMarker){runMarker=next;changed=true;}}
   if(changed)void load();
  });
  return()=>{controller.abort();window.clearTimeout(timer);window.clearInterval(frame);stopVisible();stopActivity();};
 },[url,key,request,reauth,active,scope,ownerId,sessionId,goal?.revision]);
 const polled=sample.key===key?sample.clock:null,confirmed=goal?.keepalive?.clock;
 const newer=!!confirmed && (!polled || (confirmed.controlRevision??-1)>(polled.controlRevision??-1)
  || confirmed.controlRevision===polled.controlRevision && confirmed.cycleId===polled.cycleId && confirmed.durationMs>=polled.durationMs);
 const clock=newer?confirmed:polled;
 const arrival=newer?(controlSample.clock===confirmed?controlSample.arrival:tick):sample.arrival;
 const age=clock?clock.ageMs+Math.max(0,tick-arrival):0;
 const uncertain=(!newer && sample.error) || clock?.state==='unknown' || (clock?.state==='running' && age>clock.staleAfterMs);
 const measured=clock?clock.durationMs+(clock.state==='running' && !uncertain?age:0):null;
 const holdKey=key+':'+pending?.requestId;
 useEffect(()=>{
  let cancelled=false;
  queueMicrotask(()=>{if(!cancelled)setHeld(old=>pending?(old?.key===holdKey?old:{key:holdKey,duration:measured}):null);});
  return()=>{cancelled=true;};
 },[pending,holdKey,measured]);
 const saving=!!pending && ['play','pause','stop'].includes(pending.action);
 const display=pending?.action==='stop'?0:pending?.action==='pause' && held?.key===holdKey?held.duration:measured;
 const pendingLabel=pending?.action==='stop'?'Reset pending':pending?.action==='pause'?'Pause pending':'Start pending';
 return <span className={`agent-goal-clock ${uncertain?'uncertain':''}`} role="timer" aria-live="off"
  aria-label={saving?`Goal time · ${pendingLabel}`:uncertain?'Goal time unconfirmed':'Goal time'} title={saving?'The control is being saved. This display is pending until its original server receipt confirms it.':uncertain?'Last confirmed Goal time; an unavailable interval is not estimated.':clock?.mode==='keepalive'?'Current Goal time cycle. Pause preserves it; Stop resets the display. Historical runtime and budgets are retained.':clock?'Time in this original Goal execution':'No Goal execution has started.'}>
  {clock||saving?duration(display):'—'}{saving?` · ${pendingLabel}`:uncertain && clock?' ?':''}</span>;
}
