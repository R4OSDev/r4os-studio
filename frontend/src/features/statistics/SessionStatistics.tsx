import {useEffect,useRef,useState} from 'react';
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
  <p className="statistics-coverage" role="status">{unavailable?'Goal time is not fully reported for this session.':incomplete?'Partial Goal time coverage. Only confirmed time is retained; unavailable live time is frozen.':fresh?'Recorded Goal time including the current execution.':'Recorded Goal time across all Play executions.'}</p>
  {value && <p className="statistics-help">{value.coverage.measuredExecutions} measured {value.coverage.measuredExecutions===1?'execution':'executions'}{value.coverage.missingExecutions?` · ${value.coverage.missingExecutions} without a measurement`:''}. Paused and queued time is excluded.</p>}
 </section>;
}
export function GoalRuntime({ownerId,sessionId,reauth}:{ownerId:string;sessionId:string;reauth:()=>Promise<void>}) {
 const {request}=useSessionApi(),url=sessionPath(ownerId,sessionId)+'/goal/clock';
 const [sample,setSample]=useState<{clock:GoalClockSnapshot|null;arrival:number;error:boolean}>({clock:null,arrival:0,error:false});
 const [tick,setTick]=useState(0),live=useRef(false);
 useEffect(()=>{
  const controller=new AbortController();let loading=false;
  async function load(){
   if(document.hidden || loading)return;loading=true;
   try{const value=await request<{clock:GoalClockSnapshot|null}>(url,'','GET',undefined,controller.signal);if(!controller.signal.aborted){const at=performance.now();live.current=value.clock?.state==='running';setSample({clock:value.clock,arrival:at,error:false});setTick(at);}}
   catch(error){if(!controller.signal.aborted){live.current=false;setSample(old=>({...old,error:true}));if((error as {status?:number}).status===403)await reauth().catch(()=>undefined);}}
   finally{loading=false;}
  }
  void load();const timer=window.setInterval(()=>void load(),2000),frame=window.setInterval(()=>{if(!document.hidden && live.current)setTick(performance.now());},250);
  const visible=()=>{if(!document.hidden)void load();};window.addEventListener('focus',visible);window.addEventListener('online',visible);document.addEventListener('visibilitychange',visible);
  return()=>{controller.abort();window.clearInterval(timer);window.clearInterval(frame);window.removeEventListener('focus',visible);window.removeEventListener('online',visible);document.removeEventListener('visibilitychange',visible);};
 },[url,request,reauth]);
 const clock=sample.clock,age=clock?clock.ageMs+Math.max(0,tick-sample.arrival):0;
 const uncertain=sample.error || clock?.state==='unknown' || (clock?.state==='running' && age>clock.staleAfterMs);
 const ms=clock?clock.durationMs+(clock.state==='running' && !uncertain?age:0):null;
 return <span className={`agent-goal-clock ${uncertain?'uncertain':''}`} role="timer" aria-live="off"
  aria-label={uncertain?'Goal runtime unconfirmed':'Goal runtime'} title={uncertain?'Last confirmed Goal time; live measurement is unavailable.':clock?'Time in this Goal execution':'No Goal execution has started.'}>{clock?duration(ms):'—'}{uncertain && clock?' ?':''}</span>;
}
