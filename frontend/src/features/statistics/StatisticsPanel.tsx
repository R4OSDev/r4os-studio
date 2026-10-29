import {useCallback,useEffect,useState} from 'react';
import type {StatisticsSnapshot} from '../../../../shared/statistics';
import {ProjectRequestError,studioRequest} from '../projects/api';
import './styles.css';
export function duration(ms: number | string | null | undefined) {
 if (typeof ms === 'string') {
  try { if (!/^\d+$/.test(ms)) return 'Not reported'; const seconds=BigInt(ms)/1000n;
   return [seconds/3600n,(seconds/60n)%60n,seconds%60n].map(n=>n.toString().padStart(2,'0')).join(':');
  } catch { return 'Not reported'; }
 }
 if (ms == null || !Number.isFinite(ms) || ms < 0) return 'Not reported';
 const seconds=Math.floor(ms/1000);
 return [Math.floor(seconds/3600),Math.floor(seconds/60)%60,seconds%60].map(n=>n.toString().padStart(2,'0')).join(':');
}
export function useStatistics(url: string,reauth?:()=>Promise<void>) {
 const [state,setState]=useState<{url:string;value:StatisticsSnapshot|null;error:string;receivedAt:number}>({url,value:null,error:'',receivedAt:0});
 const [revision,setRevision]=useState(0);
 const refresh=useCallback(()=>setRevision(n=>n+1),[]);
 useEffect(()=>{
  const controller=new AbortController();let loading=false;
  async function load(){
   if(loading || document.hidden)return;loading=true;
   try{
    let value:StatisticsSnapshot;
    try{value=await studioRequest<StatisticsSnapshot>('',url,'','GET',undefined,controller.signal);}
    catch(error){if((error as ProjectRequestError).status!==403 || !reauth)throw error;await reauth();value=await studioRequest<StatisticsSnapshot>('',url,'','GET',undefined,controller.signal);}
    if(!controller.signal.aborted)setState({url,value,error:'',receivedAt:performance.now()});
   }catch(error){if(!controller.signal.aborted)setState(previous=>({url,value:previous.url===url?previous.value:null,error:(error as Error).message,receivedAt:previous.url===url?previous.receivedAt:0}));}
   finally{loading=false;}
  }
  void load();const timer=window.setInterval(()=>void load(),5000);
  const visible=()=>{if(!document.hidden)void load();};window.addEventListener('focus',visible);window.addEventListener('online',visible);document.addEventListener('visibilitychange',visible);
  return()=>{controller.abort();window.clearInterval(timer);window.removeEventListener('focus',visible);window.removeEventListener('online',visible);document.removeEventListener('visibilitychange',visible);};
 },[url,reauth,revision]);
 return {value:state.url===url?state.value:null,error:state.url===url?state.error:'',receivedAt:state.url===url?state.receivedAt:0,refresh};
}
function tokens(value:string|null|undefined){try{return value==null?'Not reported':new Intl.NumberFormat('en-US').format(BigInt(value));}catch{return 'Not reported';}}
function date(value:string|null){return value && !Number.isNaN(Date.parse(value))?new Date(value).toLocaleString('en-GB'):'Not reported';}
export function StatisticsContent({value,session=false}:{value:StatisticsSnapshot;session?:boolean}) {
 const labels={total:'Total tokens',input:'Input tokens',output:'Output tokens',cachedInput:'Cached input',cacheWrite:'Cache write',reasoningOutput:'Reasoning output'} as const;
 return <><dl className="statistics-grid">{(['total','input','output'] as const).map(key=><div key={key}><dt>{labels[key]}</dt><dd>{tokens(value.tokens[key])}</dd></div>)}
  {!session && <div><dt>Longest Goal run</dt><dd>{duration(value.longestGoalMs)}</dd></div>}</dl>
  {(['cachedInput','cacheWrite','reasoningOutput'] as const).some(key=>value.tokens[key]!=null) && <dl className="statistics-details">{(['cachedInput','cacheWrite','reasoningOutput'] as const).map(key=><div key={key}><dt>{labels[key]}</dt><dd>{tokens(value.tokens[key])}</dd></div>)}</dl>}
  <p className="statistics-help">Cache and reasoning tokens are included in the reported totals.</p>
  <p className="statistics-coverage" role="status">{value.coverage.state==='notReported'?'No qualified measurements yet.':value.coverage.delayed?'Measurements are waiting for reconciliation.':value.coverage.hasGaps?'Partial coverage. Some work has no reported usage.':'Reported Studio usage. Historical coverage may be incomplete.'}</p>
  <div className="statistics-dates"><span>Coverage since: {date(value.coverage.since)}</span><span>Updated: {date(value.coverage.updatedAt)}</span></div>
 </>;
}
export function StatisticsPanel({projectId,reauth}:{projectId?:string;reauth?:()=>Promise<void>}) {
 const result=useStatistics(projectId?`/api/projects/${projectId}/statistics`:'/api/statistics',reauth);
 return <section className="statistics-panel" aria-label={projectId?'Project statistics':'Global statistics'}>
  <header><h2>{projectId?'Project statistics':'Global statistics'}</h2><button type="button" onClick={result.refresh}>Refresh</button></header>
  <p>{projectId?'Reported usage for this project.':'Reported usage across Studio project and Skill Manager sessions.'} Lifetime totals retain recorded work after deletion.</p>
  {result.error && <p className="project-dialog-error" role="alert">Statistics unavailable: {result.error}</p>}
  {result.value?<StatisticsContent value={result.value}/>:!result.error && <p role="status">Loading statistics…</p>}
 </section>;
}
